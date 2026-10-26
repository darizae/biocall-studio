from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer

from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.run import RunStatus
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import MainWindow
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.persistence.models import load_model
from biocall_studio_train.workflows.dataset_build import build_dataset

pytestmark = [pytest.mark.integration, pytest.mark.qt, pytest.mark.soak]


def _cnn_config(dataset, *, epochs: int):
    draft = TrainingDraft.defaults("cnn")
    for key, value in {
        "sequence_length_ms": 250,
        "training.max_epochs": epochs,
        "training.batch_size": 2,
        "training.learning_rate": 0.0001,
        "training.early_stopping_patience_epochs": 100,
        "training.lr_patience_epochs": 100,
        "training.epochs_per_eval": 1,
        "device": "cpu",
        "spectrogram.sample_rate": 16_000,
        "spectrogram.n_fft": 256,
        "spectrogram.hop_length": 64,
        "spectrogram.n_freq_bins": 64,
        "spectrogram.f_min": 100,
        "spectrogram.f_max": 7_000,
        "training.num_workers": 0,
        "training.pin_memory": False,
    }.items():
        draft.set(key, value)
    return freeze_training_config(
        draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=4),
    )


def _rss_kib(pid: int) -> int | None:
    if sys.platform == "win32":
        return None
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _open_handle_count(pid: int) -> int | None:
    if sys.platform == "win32":
        return None
    if sys.platform.startswith("linux"):
        try:
            return len(tuple((Path("/proc") / str(pid) / "fd").iterdir()))
        except OSError:
            return None
    result = subprocess.run(["lsof", "-p", str(pid)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return max(0, len(result.stdout.splitlines()) - 1)


def _write_soak_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def test_ten_minute_real_cnn_run_remains_responsive_reloads_and_reuses(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-RUN-009; explicitly invoked 600-second real-QProcess durability case."""
    create_application()
    assert qapp.styleHints().colorScheme() is Qt.ColorScheme.Light
    root = collection_factory(tmp_path / "collection", source_count=3)
    scan = publish_collection_metadata(root, scan_collection(root))
    build_config = BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=100,
    )
    dataset = build_dataset(root, scan, build_config, dataset_id="dataset-soak-cnn")
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=5.0,
        cancel_grace_ms=2_000,
        kill_grace_ms=4_000,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    run_id = controller.start_training(
        _cnn_config(dataset, epochs=32),
        model_label="Ten-minute durability CNN",
        model_id="model-soak-cnn",
    )
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=20_000,
    )
    assert controller._run_process is not None
    worker_pid = controller._run_process.processId()
    started = time.monotonic()
    started_at_utc = datetime.now(UTC).isoformat()
    heartbeat = 0
    report_path = Path(
        os.environ.get("BIOCALL_STUDIO_TRAIN_SOAK_REPORT", tmp_path / "soak-observations.json")
    )

    def beat() -> None:
        nonlocal heartbeat
        heartbeat += 1

    timer = QTimer()
    timer.timeout.connect(beat)
    timer.start(100)
    samples: list[dict[str, int | float | None]] = []
    last_sample = 0.0
    route_index = 0
    routes = ("runs", "settings", "models")
    while controller.active_run is not None:
        before = heartbeat
        qtbot.wait(1_000)
        assert heartbeat > before
        elapsed = time.monotonic() - started
        if elapsed - last_sample >= 15:
            last_sample = elapsed
            route = routes[route_index % len(routes)]
            route_index += 1
            window.navigate(route)
            qapp.processEvents()
            assert window.current_route == route
            window.open_run(run_id)
            assert window.run_detail_page.cancel_button.isEnabled()
            stage = root / ".alpaca" / ".staging"
            log = root / ".alpaca" / "runs" / run_id / "logs" / "worker.jsonl"
            samples.append(
                {
                    "elapsed_seconds": round(elapsed, 3),
                    "heartbeat": heartbeat,
                    "rss_kib": _rss_kib(worker_pid),
                    "open_handles": _open_handle_count(worker_pid),
                    "supervised_worker_count": int(controller._run_process is not None),
                    "staging_bytes": sum(
                        path.stat().st_size for path in stage.rglob("*") if path.is_file()
                    )
                    if stage.exists()
                    else 0,
                    "worker_log_bytes": log.stat().st_size if log.exists() else 0,
                }
            )
            _write_soak_report(
                report_path,
                {
                    "case": "IT-RUN-009",
                    "status": "running",
                    "run_id": run_id,
                    "started_at_utc": started_at_utc,
                    "samples": samples,
                },
            )
            print("IT-RUN-009 sample " + json.dumps(samples[-1], sort_keys=True), flush=True)
        assert time.monotonic() - started < 900
    timer.stop()
    elapsed = time.monotonic() - started

    state = next(run for run in controller.runs if run.run_id == run_id)
    assert elapsed >= 600
    assert state.status is RunStatus.COMPLETED
    assert controller._run_process is None
    assert samples
    assert len(state.activity) <= 200
    assert samples[-1]["worker_log_bytes"] < 5_000_000
    model = load_model(root, "model-soak-cnn")
    checkpoint = model.root / model.manifest["artifact"]["path"]
    assert (
        hashlib.sha256(checkpoint.read_bytes()).hexdigest() == model.manifest["artifact"]["sha256"]
    )

    reload_code = """
from pathlib import Path
from biocall_studio_train.persistence.models import load_model, structurally_reload_cnn_model
root = Path(__import__('sys').argv[1])
artifact = load_model(root, 'model-soak-cnn')
structurally_reload_cnn_model(root, artifact.model_id)
print(artifact.model_id)
"""
    fresh = subprocess.run(
        [sys.executable, "-c", reload_code, str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert fresh.stdout.strip() == "model-soak-cnn"

    controller._worker_step_delay_seconds = 0.0
    second_id = controller.start_training(
        _cnn_config(dataset, epochs=1),
        model_label="Post-soak reuse CNN",
        model_id="model-post-soak-cnn",
    )
    qtbot.waitUntil(
        lambda: any(run.run_id == second_id and run.terminal for run in controller.runs),
        timeout=180_000,
    )
    second = next(run for run in controller.runs if run.run_id == second_id)
    assert second.status is RunStatus.COMPLETED
    assert load_model(root, "model-post-soak-cnn").root.is_dir()
    observations = {
        "elapsed_seconds": round(elapsed, 3),
        "sample_count": len(samples),
        "peak_rss_kib": max((sample["rss_kib"] or 0 for sample in samples), default=0),
        "peak_open_handles": max((sample["open_handles"] or 0 for sample in samples), default=0),
        "peak_staging_bytes": max(sample["staging_bytes"] for sample in samples),
        "peak_worker_log_bytes": max(sample["worker_log_bytes"] for sample in samples),
        "heartbeats": heartbeat,
    }
    _write_soak_report(
        report_path,
        {
            "case": "IT-RUN-009",
            "status": "passed",
            "run_id": run_id,
            "second_run_id": second_id,
            "started_at_utc": started_at_utc,
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "model_sha256": model.manifest["artifact"]["sha256"],
            "second_model_sha256": load_model(root, "model-post-soak-cnn").manifest["artifact"][
                "sha256"
            ],
            "observations": observations,
            "samples": samples,
        },
    )
    print("IT-RUN-009 observations " + json.dumps(observations, sort_keys=True), flush=True)
