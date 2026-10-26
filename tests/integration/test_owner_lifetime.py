from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.application.owner_lifetime import OwnerLease
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.run import RunKind, RunStatus, new_run, transition_run
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.persistence.models import list_models
from biocall_studio_train.persistence.runs import create_run, load_run, reconcile_runs
from biocall_studio_train.persistence.settings import ApplicationSettings, SettingsStore
from biocall_studio_train.workflows.dataset_build import DatasetBuildCancelled, build_dataset

pytestmark = pytest.mark.integration


def test_worker_observes_kernel_owned_gui_lease_release(tmp_path: Path):
    """Case: IT-RUN-008; the Worker checks a process-owned cross-platform lease."""
    lease = OwnerLease.create(tmp_path)
    code = """
import sys
from pathlib import Path
from biocall_studio_train.application.owner_lifetime import WorkerOwnerGuard

guard = WorkerOwnerGuard(Path(sys.argv[1]))
print('alive' if guard.owner_alive() else 'lost', flush=True)
sys.stdin.readline()
print('alive' if guard.owner_alive() else 'lost', flush=True)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(lease.path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "alive"
        lease.close()
        assert child.stdin is not None
        child.stdin.write("continue\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "lost"
        assert child.wait(timeout=5) == 0
    finally:
        if child.poll() is None:
            child.kill()


def test_owner_loss_at_publication_guard_leaves_no_dataset(tmp_path: Path, collection_factory):
    """Case: IT-RUN-008; a lost owner cannot commit staged output."""
    root = collection_factory(tmp_path / "collection", source_count=3)
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

    with pytest.raises(DatasetBuildCancelled, match="owner"):
        build_dataset(
            root,
            scan,
            config,
            dataset_id="dataset-owner-lost",
            publication_allowed=lambda: False,
        )

    assert not (root / ".alpaca" / "datasets" / "dataset-owner-lost").exists()
    staging = root / ".alpaca" / ".staging"
    assert not staging.exists() or not any(staging.iterdir())


def test_restart_retains_fully_committed_matching_artifact_without_receipt(
    tmp_path: Path, collection_factory
):
    """Cases: IT-RUN-007, IT-RUN-008; durable publication wins at the receipt boundary."""
    root = collection_factory(tmp_path / "collection", source_count=3)
    scan = publish_collection_metadata(root, scan_collection(root))
    run = new_run(
        run_id="run-committed-before-owner-loss",
        request_id="request-committed-before-owner-loss",
        kind=RunKind.DATASET_BUILD,
        title="Committed at boundary",
        collection_id=scan.collection_id,
        input_dataset_id=None,
        output_kind="dataset",
        output_id="dataset-committed-at-boundary",
        stages=("Validate", "Publish"),
        now="2026-10-26T10:00:00Z",
    )
    run = transition_run(run, RunStatus.STARTING, now="2026-10-26T10:00:01Z")
    run = transition_run(run, RunStatus.RUNNING, now="2026-10-26T10:00:02Z")
    create_run(root, run)
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
    artifact = build_dataset(
        root,
        scan,
        config,
        dataset_id=run.output_id,
        run_id=run.run_id,
        request_id=run.request_id,
    )
    assert not (root / ".alpaca" / "runs" / run.run_id / "result.json").exists()

    reconciled = {item.run_id: item for item in reconcile_runs(root)}[run.run_id]

    assert reconciled.status is RunStatus.COMPLETED
    assert reconciled.published_artifact_id == artifact.dataset_id
    assert artifact.root.is_dir()


def _process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_killing_actual_gui_process_stops_rf_worker_before_publication(
    tmp_path: Path, collection_factory
):
    """Case: IT-RUN-008; actual GUI death drops supervision and prevents RF publication."""
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
    dataset = build_dataset(root, scan, build_config, dataset_id="dataset-owner-rf")
    settings_dir = tmp_path / "settings"
    SettingsStore(settings_dir / "settings.json").save(
        ApplicationSettings(root.resolve(), scan.collection_id, False)
    )
    source_before = {
        path.relative_to(root): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    code = r"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import MainWindow
from biocall_studio_train.persistence.datasets import load_dataset

settings = Path(sys.argv[1])
app = create_application()
controller = WorkspaceController(settings, worker_step_delay_seconds=1.0)
window = MainWindow(controller)
window.show()
dataset = load_dataset(controller.collection_path, 'dataset-owner-rf')
draft = TrainingDraft.defaults('rf')
for key, value in {
    'n_estimators': 10,
    'min_samples_leaf': 1,
    'n_jobs': 1,
    'feature_config.sample_rate_hz': 8000,
    'feature_config.min_duration_s': 0.25,
    'feature_config.n_fft': 256,
    'feature_config.hop_length': 64,
    'feature_config.n_mfcc': 4,
    'feature_config.fmin_hz': 100.0,
    'feature_config.fmax_hz': 3500.0,
}.items():
    draft.set(key, value)
config = freeze_training_config(
    draft,
    TrainingDataset.from_artifact(dataset),
    DeviceCapabilities(cuda=False, mps=False, cpu_count=4),
)
run_id = controller.start_training(
    config,
    model_label='Owner loss RF',
    model_id='model-owner-lost-rf',
)
def report_when_running():
    if controller.active_run is None or controller._run_process is None:
        QTimer.singleShot(20, report_when_running)
        return
    if controller.active_run.status.value != 'running':
        QTimer.singleShot(20, report_when_running)
        return
    print(json.dumps({
        'gui_pid': __import__('os').getpid(),
        'worker_pid': controller._run_process.processId(),
        'run_id': run_id,
    }), flush=True)
QTimer.singleShot(0, report_when_running)
raise SystemExit(app.exec())
"""
    gui = subprocess.Popen(
        [sys.executable, "-c", code, str(settings_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert gui.stdout is not None
        line = gui.stdout.readline()
        assert line, gui.stderr.read() if gui.stderr is not None else "GUI produced no status"
        status = json.loads(line)
        assert status["gui_pid"] == gui.pid
        worker_pid = int(status["worker_pid"])
        run_id = status["run_id"]
        assert _process_exists(worker_pid)

        gui.kill()
        gui.wait(timeout=10)
        deadline = time.monotonic() + 10
        while _process_exists(worker_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _process_exists(worker_pid)

        from biocall_studio_train.application.workspace import WorkspaceController

        reopened = WorkspaceController(settings_dir)
        state = load_run(root, run_id)
        assert state.status is RunStatus.INTERRUPTED
        assert list_models(root) == ()
        assert not (root / ".alpaca" / "models" / "model-owner-lost-rf").exists()
        staging = root / ".alpaca" / ".staging"
        assert not staging.exists() or not any(staging.iterdir())
        assert {
            relative: (root / relative).read_bytes() for relative in source_before
        } == source_before
        assert dataset.root.is_dir()
        reopened.finalize_shutdown()
        assert list(settings_dir.glob("owner-*.lease")) == []
    finally:
        if gui.poll() is None:
            gui.kill()
            gui.wait(timeout=5)
