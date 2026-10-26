from __future__ import annotations

import json
import math
import subprocess
import sys

import pytest
from alp_ui.components import Plot
from PySide6.QtWidgets import QInputDialog

from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.run import RunState, RunStatus
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import MainWindow
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.persistence.diagnostics import read_diagnostic_records, worker_log_path
from biocall_studio_train.persistence.models import list_models, structurally_reload_cnn_model
from biocall_studio_train.persistence.training_presets import PresetStore
from biocall_studio_train.workflows.dataset_build import build_dataset

pytestmark = pytest.mark.integration


def _dataset(root, wav_factory):
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        wav_factory(root / "recordings" / f"{stem}.wav", frames=32_000, rate=16_000)
        wav_factory(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index}.wav",
            frames=8_000,
            rate=16_000,
        )
    scan = publish_collection_metadata(root, scan_collection(root))
    config = BuildConfig(
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
    return scan, build_dataset(root, scan, config, dataset_id="dataset-cnn-training")


def _fast_draft(*, epochs=1):
    draft = TrainingDraft.defaults("cnn")
    for key, value in {
        "sequence_length_ms": 250,
        "training.max_epochs": epochs,
        "training.batch_size": 2,
        "training.learning_rate": 0.0001,
        "device": "cpu",
        "spectrogram.sample_rate": 16_000,
        "spectrogram.n_fft": 256,
        "spectrogram.hop_length": 64,
        "spectrogram.n_freq_bins": 64,
        "spectrogram.f_min": 100,
        "spectrogram.f_max": 7_000,
        "training.num_workers": 0,
        "training.early_stopping_patience_epochs": 2,
        "training.epochs_per_eval": 1,
        "training.pin_memory": False,
    }.items():
        draft.set(key, value)
    return draft


def _fast_config(artifact, *, epochs=1, preset_origin=None):
    draft = _fast_draft(epochs=epochs)
    return freeze_training_config(
        draft,
        TrainingDataset.from_artifact(artifact),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
        preset_origin=preset_origin,
    )


@pytest.mark.qt
def test_real_cnn_worker_publishes_reloadable_model_and_native_views(
    qapp, qtbot, tmp_path, wav_factory, monkeypatch
):
    """Cases: IT-TRAIN-001, IT-TRAIN-005, IT-TRAIN-007, IT-TRAIN-008, IT-TRAIN-012,
    IT-TRAIN-014, IT-LOG-002.
    """
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    source_bytes = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)
    preset_store = PresetStore(tmp_path / "settings" / "training-presets")
    preset = preset_store.create("Tiny CPU CNN", _fast_draft())
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.open_training(dataset.dataset_id)
    page = window.training_page
    page.load_preset(preset.preset_id)
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Tiny verified CNN", True),
    )
    page.start_button.click()
    assert page.last_frozen_config is not None
    frozen_snapshot = page.last_frozen_config.to_worker_snapshot()
    assert controller.active_run is not None
    run_id = controller.active_run.run_id
    model_id = controller.active_run.output_id
    request = json.loads((root / ".alpaca" / "runs" / run_id / "request.json").read_text())
    assert request["config"] == frozen_snapshot
    assert request["model_label"] == "Tiny verified CNN"
    assert window.current_route == "run-detail"
    preset_store.overwrite(preset.preset_id, TrainingDraft.defaults("cnn"))
    preset_store.delete(preset.preset_id)
    qtbot.waitUntil(
        lambda: any(run.run_id == run_id and run.terminal for run in controller.runs),
        timeout=180_000,
    )
    run = next(run for run in controller.runs if run.run_id == run_id)

    assert run.status is RunStatus.COMPLETED
    assert run.published_artifact_id == model_id
    assert {item["phase"] for item in run.measurements} == {"train", "val"}
    assert all(item["loss"] >= 0 for item in run.measurements)
    worker_records, notices = read_diagnostic_records(worker_log_path(root, run_id))
    assert notices == ()
    assert {record["event"] for record in worker_records} >= {
        "worker_started",
        "training_stage",
        "worker_completed",
    }
    assert not any(record["event"] == "measurement_available" for record in worker_records)
    assert len(run.measurements) == 2
    models = list_models(root)
    assert [model.model_id for model in models] == [model_id]
    model = models[0]
    assert model.manifest["resolved_config"] == frozen_snapshot
    assert model.manifest["resolved_config"]["preset_origin"] == preset.preset_id
    assert model.manifest["resolved_config"]["effective_values"]["training.max_epochs"] == 1
    assert model.manifest["results"]["history"]["train"]
    assert model.manifest["results"]["history"]["val"]
    assert {
        phase: [
            {"epoch": item["epoch"], "loss": item["loss"]}
            for item in run.measurements
            if item["phase"] == phase
        ]
        for phase in ("train", "val")
    } == {
        phase: [
            {"epoch": item["epoch"], "loss": item["loss"]}
            for item in model.manifest["results"]["history"][phase]
        ]
        for phase in ("train", "val")
    }
    assert model.manifest["results"]["split_counts"] == {
        split: {label: dataset.manifest["counts"][split][label] for label in ("noise", "target")}
        for split in ("train", "val")
    }
    assert str(root) not in (model.root / "model.json").read_text()
    assert source_bytes == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }

    structure = structurally_reload_cnn_model(root, model.model_id)
    assert structure.num_classes == 2
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json,sys; "
                "from pathlib import Path; "
                "from biocall_studio_train.persistence.models import "
                "structurally_reload_cnn_model; "
                "print(json.dumps(structurally_reload_cnn_model(Path(sys.argv[1]), "
                "sys.argv[2]).to_dict(), sort_keys=True))"
            ),
            str(root),
            model.model_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["num_classes"] == 2

    window.open_run(run_id)
    assert isinstance(window.run_detail_page.training_plot, Plot)
    expected_lines = tuple(
        (
            f"{phase} loss",
            tuple(
                (float(item["epoch"]), float(item["loss"]))
                for item in run.measurements
                if item["phase"] == phase
            ),
        )
        for phase in ("train", "val")
    )
    assert window.run_detail_page.training_plot_data == expected_lines
    assert window.run_detail_page.training_plot.x_label == "Epoch"
    assert window.run_detail_page.training_plot.y_label == "Loss"
    assert all(
        math.isfinite(value)
        for _label, points in window.run_detail_page.training_plot_data
        for point in points
        for value in point
    )
    assert window.run_detail_page.training_plot.accessibleDescription() == (
        "Line plot with 2 series and 2 points."
    )
    assert "train loss" in window.run_detail_page.training_values.text()
    for item in run.measurements:
        assert f"{item['phase']} loss {item['loss']:.4f}" in (
            window.run_detail_page.training_values.text()
        )
    invalid_state = run.to_dict()
    invalid_state["measurements"][0]["loss"] = float("nan")
    with pytest.raises(ValueError, match="finite numeric data"):
        RunState.from_dict(invalid_state)
    window.navigate("models")
    assert window.model_list_page.model.rowCount() == 1
    window.open_model(model.model_id)
    assert window.current_route == "model-detail"
    assert window.model_detail_page.model_id.text() == model.model_id
    assert "Tiny verified CNN" in window.model_detail_page.accessibleName()


@pytest.mark.qt
def test_info_and_debug_diagnostics_do_not_change_cnn_science(qapp, qtbot, tmp_path, wav_factory):
    """Case: IT-LOG-002."""
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)

    runs = {}
    for detail in ("info", "debug"):
        draft = _fast_draft()
        draft.set("logging_level", detail)
        frozen = freeze_training_config(
            draft,
            TrainingDataset.from_artifact(dataset),
            DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
        )
        run_id = controller.start_training(
            frozen,
            model_label=f"CNN {detail} diagnostics",
            model_id=f"model-cnn-{detail}-diagnostics",
        )
        qtbot.waitUntil(
            lambda current=run_id: any(
                run.run_id == current and run.terminal for run in controller.runs
            ),
            timeout=180_000,
        )
        runs[detail] = next(run for run in controller.runs if run.run_id == run_id)

    assert runs["info"].status is RunStatus.COMPLETED
    assert runs["debug"].status is RunStatus.COMPLETED
    assert runs["info"].measurements == runs["debug"].measurements
    models = {model.model_id: model for model in list_models(root)}
    info_model = models["model-cnn-info-diagnostics"]
    debug_model = models["model-cnn-debug-diagnostics"]
    assert info_model.manifest["results"] == debug_model.manifest["results"]
    assert info_model.manifest["artifact"]["sha256"] == debug_model.manifest["artifact"]["sha256"]
    info_records, _ = read_diagnostic_records(worker_log_path(root, runs["info"].run_id))
    debug_records, _ = read_diagnostic_records(worker_log_path(root, runs["debug"].run_id))
    assert not any(record["event"] == "measurement_available" for record in info_records)
    assert any(record["event"] == "measurement_available" for record in debug_records)
    assert len(runs["info"].measurements) == len(runs["debug"].measurements) == 2


@pytest.mark.qt
def test_cnn_cancellation_and_changed_dataset_never_publish_model(
    qapp, qtbot, tmp_path, wav_factory
):
    """Cases: IT-TRAIN-004, IT-TRAIN-009."""
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)

    run_id = controller.start_training(
        _fast_config(dataset, epochs=20),
        model_label="Cancelled CNN",
        model_id="model-cnn-cancelled",
    )
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=20_000,
    )
    controller.cancel_active_run()
    qtbot.waitUntil(
        lambda: any(run.run_id == run_id and run.terminal for run in controller.runs),
        timeout=60_000,
    )
    cancelled = next(run for run in controller.runs if run.run_id == run_id)
    assert cancelled.status is RunStatus.CANCELLED
    assert not (root / ".alpaca" / "models" / "model-cnn-cancelled").exists()

    broken = dataset.root / dataset.snippets[0]["relative_path"]
    broken.unlink()
    with pytest.raises(ValueError, match="missing|unsafe"):
        controller.start_training(
            _fast_config(dataset),
            model_label="Broken CNN",
            model_id="model-cnn-broken",
        )
    assert not (root / ".alpaca" / "models" / "model-cnn-broken").exists()
