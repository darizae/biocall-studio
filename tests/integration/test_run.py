from __future__ import annotations

from pathlib import Path

import pytest
from alp_ui.components import Alert, Badge, Button, DataTable, ProgressBar
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.domain.run import (
    RunConflictError,
    RunKind,
    RunStatus,
    new_run,
    transition_run,
)
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.run import RunDetailPage, RunListPage
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.persistence.datasets import list_datasets
from alpaca_desktop.persistence.runs import create_run, load_run, reconcile_runs
from alpaca_desktop.workflows.dataset_build import build_dataset

pytestmark = pytest.mark.integration


def _config(result) -> BuildConfig:
    return BuildConfig(
        selected_recording_ids=tuple(record.id for record in result.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=250,
    )


def _published_collection(root: Path, collection_factory):
    collection_factory(root, source_count=3)
    result = scan_collection(root)
    assert result.valid
    return publish_collection_metadata(root, result)


def _ready_controller(
    qtbot,
    tmp_path,
    collection_factory,
    *,
    worker_step_delay_seconds: float = 0.0,
):
    root = tmp_path / "collection"
    result = _published_collection(root, collection_factory)
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=worker_step_delay_seconds,
        cancel_grace_ms=100,
        kill_grace_ms=200,
    )
    controller.bind_verified_collection(root, result.collection_id)
    controller.reopen_bound_collection()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )
    return root, result, controller


@pytest.mark.qt
def test_real_qprocess_persists_progress_and_verified_dataset(qtbot, tmp_path, collection_factory):
    """Cases: IT-RUN-001, IT-AUDIO-004."""
    root, result, controller = _ready_controller(
        qtbot, tmp_path, collection_factory, worker_step_delay_seconds=0.04
    )
    source_before = {path: path.read_bytes() for path in root.glob("*/*.wav")}
    observed: list[RunStatus] = []
    controller.run_changed.connect(lambda run: observed.append(run.status))

    run_id = controller.start_dataset_build(_config(result), dataset_id="dataset-run-success")
    assert controller.active_run is not None
    assert controller.active_run.run_id == run_id
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)

    state = load_run(root, run_id)
    artifact = list_datasets(root)[0]
    assert state.status is RunStatus.COMPLETED
    assert state.published_artifact_id == "dataset-run-success"
    assert artifact.dataset_id == state.published_artifact_id
    assert artifact.root.joinpath("dataset.json").is_file()
    extraction = artifact.manifest["source_policy"]["audio_extraction"]
    assert extraction == {
        "distribution": "bioacoustics-dl-toolbox",
        "version": "0.1.1",
        "revision": "0fce0d4fa3d0931c5731e8b868f705e0a2120835",
        "api": "bioacoustics_dl_toolbox.audio.extract_pcm_wav_segment",
    }
    assert str(root) not in artifact.root.joinpath("dataset.json").read_text()
    assert {path: path.read_bytes() for path in source_before} == source_before
    assert RunStatus.CREATED in observed
    assert RunStatus.STARTING in observed
    assert RunStatus.RUNNING in observed
    assert RunStatus.COMPLETED in observed
    assert state.progress == 100
    assert any("verified" in entry.lower() for entry in state.activity)


@pytest.mark.qt
def test_active_run_conflicts_but_read_only_browsing_and_terminal_release_work(
    qtbot, tmp_path, collection_factory
):
    """Case: IT-RUN-002. Exclusivity is scoped to one WorkspaceController/app process."""
    root, result, controller = _ready_controller(
        qtbot, tmp_path, collection_factory, worker_step_delay_seconds=0.18
    )
    other_root = tmp_path / "other-collection"
    other = _published_collection(other_root, collection_factory)

    controller.start_dataset_build(_config(result), dataset_id="dataset-reserved")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    active_run_id = controller.active_run.run_id
    controller.bind_verified_collection(root, result.collection_id)
    assert controller.active_run is not None
    assert controller.active_run.run_id == active_run_id
    with pytest.raises(RunConflictError, match="Only one Active Run"):
        controller.start_dataset_build(_config(result), dataset_id="dataset-second")
    with pytest.raises(RunConflictError, match="rebind.*Active Run"):
        controller.bind_verified_collection(other_root, other.collection_id)
    with pytest.raises(RunConflictError, match="reserved.*Active Run"):
        controller.delete_dataset("dataset-reserved")
    assert list_datasets(root) == ()  # read-only browsing remains available during the Run

    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    deletion = controller.delete_dataset("dataset-reserved")
    assert deletion.dataset_id == "dataset-reserved"
    controller.bind_verified_collection(other_root, other.collection_id)
    assert controller.collection_path == other_root


@pytest.mark.qt
def test_cancel_and_forced_worker_loss_reconcile_without_false_artifacts(
    qtbot, tmp_path, collection_factory
):
    """Case: IT-RUN-003."""
    root, result, controller = _ready_controller(
        qtbot, tmp_path, collection_factory, worker_step_delay_seconds=0.3
    )
    cancelled_id = controller.start_dataset_build(
        _config(result), dataset_id="dataset-cancelled-run"
    )
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    controller.cancel_active_run()
    assert controller.active_run is not None
    assert controller.active_run.status is RunStatus.CANCELLING
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=10_000)
    assert load_run(root, cancelled_id).status is RunStatus.CANCELLED
    assert not (root / ".alpaca" / "datasets" / "dataset-cancelled-run").exists()

    lost_id = controller.start_dataset_build(_config(result), dataset_id="dataset-lost-run")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    assert controller._run_process is not None
    controller._run_process.kill()
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=10_000)
    assert load_run(root, lost_id).status is RunStatus.INTERRUPTED
    assert not (root / ".alpaca" / "datasets" / "dataset-lost-run").exists()

    shutdown_id = controller.start_dataset_build(_config(result), dataset_id="dataset-shutdown-run")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    controller.shutdown()
    assert controller.active_run is None
    assert controller._run_process is None
    assert load_run(root, shutdown_id).status is RunStatus.INTERRUPTED
    assert not (root / ".alpaca" / "datasets" / "dataset-shutdown-run").exists()

    orphan = new_run(
        run_id="run-orphaned-at-restart",
        request_id="request-orphaned-at-restart",
        kind=RunKind.DATASET_BUILD,
        title="Build · orphaned",
        collection_id=result.collection_id,
        input_dataset_id=None,
        output_kind="dataset",
        output_id="dataset-orphaned-at-restart",
        stages=("Validate inputs", "Publish output"),
        now="2026-10-25T08:00:00Z",
    )
    orphan = transition_run(orphan, RunStatus.STARTING, now="2026-10-25T08:00:01Z")
    orphan = transition_run(orphan, RunStatus.RUNNING, now="2026-10-25T08:00:02Z")
    create_run(root, orphan)
    abandoned_stage = root / ".alpaca" / ".staging" / "dataset-orphaned-at-restart-deadbeef"
    abandoned_stage.mkdir(parents=True)
    abandoned_stage.joinpath("partial.bin").write_bytes(b"partial")

    reopened = WorkspaceController(tmp_path / "settings")
    assert reopened.active_run is None
    assert {run.status for run in reopened.runs} >= {
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    }
    assert load_run(root, orphan.run_id).status is RunStatus.INTERRUPTED
    staging = root / ".alpaca" / ".staging"
    assert not staging.exists() or not any(staging.iterdir())


@pytest.mark.qt
def test_collision_nonzero_exit_and_corrupt_completed_output_never_overwrite(
    qtbot, tmp_path, collection_factory
):
    """Case: IT-RUN-004."""
    root, result, controller = _ready_controller(qtbot, tmp_path, collection_factory)
    existing = build_dataset(
        root,
        result,
        _config(result),
        dataset_id="dataset-collision",
    )
    existing_bytes = {
        path.relative_to(existing.root): path.read_bytes()
        for path in existing.root.rglob("*")
        if path.is_file()
    }
    failed_id = controller.start_dataset_build(_config(result), dataset_id="dataset-collision")
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    failed = load_run(root, failed_id)
    assert failed.status is RunStatus.FAILED
    assert failed.published_artifact_id is None
    assert "already exists" in failed.error
    assert {
        path.relative_to(existing.root): path.read_bytes()
        for path in existing.root.rglob("*")
        if path.is_file()
    } == existing_bytes

    completed_id = controller.start_dataset_build(
        _config(result), dataset_id="dataset-corrupt-after-completion"
    )
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    completed = load_run(root, completed_id)
    assert completed.status is RunStatus.COMPLETED
    (root / ".alpaca" / "datasets" / completed.output_id / "dataset.json").write_text("{}")
    states = reconcile_runs(root)
    corrupt = next(run for run in states if run.run_id == completed_id)
    assert corrupt.status is RunStatus.FAILED
    assert corrupt.published_artifact_id is None


@pytest.mark.qt
def test_native_run_detail_cancellation_failure_completion_and_history(
    qapp, qtbot, tmp_path, collection_factory, monkeypatch
):
    """Case: IT-RUN-005."""
    create_application()
    root = tmp_path / "collection"
    result = _published_collection(root, collection_factory)
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=0.25,
        cancel_grace_ms=100,
        kill_grace_ms=200,
    )
    controller.bind_verified_collection(root, result.collection_id)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: controller.scan_result is not None and not controller.is_scanning,
        timeout=10_000,
    )
    window.open_builder()
    window.builder_page.negative_amount.setValue(1)
    assert window.builder_page.build_button.isEnabled()
    window.builder_page.build_button.click()
    qtbot.waitUntil(lambda: window.current_route == "run-detail", timeout=10_000)

    detail = window.run_detail_page
    assert isinstance(detail, RunDetailPage)
    assert isinstance(window.run_list_page, RunListPage)
    assert isinstance(detail.status_badge, Badge)
    assert isinstance(detail.progress, ProgressBar)
    assert isinstance(detail.cancel_button, Button)
    assert isinstance(detail.output_alert, Alert)
    assert detail.cancel_button.text() == "Cancel Run"
    assert detail.section_order == (
        "progress",
        "measurements",
        "activity",
        "output",
        "details",
    )
    assert window._navigation["runs"].isChecked()
    assert window.active_run_label.text().startswith("Build ·")
    assert window.active_run_progress.isVisible()
    assert window.view_run_button.isVisible()
    assert "Not yet published" in detail.output_alert.title_widget.text()
    window.open_builder()
    assert window.current_route == "builder"
    assert not window.builder_page.build_button.isEnabled()
    assert "Another Run is active" in window.builder_page.preview_alert.title_widget.text()
    window.view_run_button.click()
    assert window.current_route == "run-detail"
    detail.cancel_button.setFocus()
    assert detail.cancel_button.focusPolicy() != Qt.FocusPolicy.NoFocus

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    detail.cancel_button.click()
    assert controller.active_run is not None
    assert controller.active_run.status is RunStatus.CANCELLING
    assert detail.status_badge.text() == "cancelling"
    assert "Cancellation requested" in detail.output_alert.title_widget.text()
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=10_000)
    assert detail.status_badge.text() == "cancelled"
    assert detail.status_badge.intent == "warning"
    assert "No published artifact" in detail.output_alert.title_widget.text()

    collision = build_dataset(root, result, _config(result), dataset_id="dataset-ui-collision")
    before = (
        collision.joinpath("dataset.json").read_bytes()
        if isinstance(collision, Path)
        else (collision.root / "dataset.json").read_bytes()
    )
    controller.start_dataset_build(_config(result), dataset_id="dataset-ui-collision")
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    assert detail.status_badge.text() == "failed"
    assert "Run failed" in detail.output_alert.title_widget.text()
    assert (collision.root / "dataset.json").read_bytes() == before

    controller.start_dataset_build(_config(result), dataset_id="dataset-ui-completed")
    qtbot.waitUntil(lambda: controller.active_run is None, timeout=20_000)
    assert detail.status_badge.text() == "completed"
    assert detail.progress.value() == 100
    assert detail.open_output_button.isVisible()
    detail.open_output_button.click()
    assert window.current_route == "dataset-detail"

    window.navigate("runs")
    assert isinstance(window.run_list_page.table, DataTable)
    assert window.run_list_page.model.rowCount() == 3
    assert window._navigation["runs"].isChecked()
    statuses = {
        window.run_list_page.model.data(window.run_list_page.model.index(row, 2))
        for row in range(window.run_list_page.model.rowCount())
    }
    status_backgrounds = {
        window.run_list_page.model.data(
            window.run_list_page.model.index(row, 2), Qt.ItemDataRole.BackgroundRole
        ).name()
        for row in range(window.run_list_page.model.rowCount())
    }
    assert statuses == {"●  cancelled", "●  completed", "●  failed"}
    assert len(status_backgrounds) == 3
    assert window.run_list_page.table.focusPolicy() != Qt.FocusPolicy.NoFocus
    index = window.run_list_page.model.index(0, 0)
    window.run_list_page.table.clicked.emit(index)
    assert window.current_route == "run-detail"

    window.resize(700, 780)
    qtbot.waitUntil(lambda: window.is_compact and detail.is_compact)
    assert detail.horizontalScrollBar().maximum() == 0
