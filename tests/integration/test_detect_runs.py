from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import QPushButton

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.domain.runs import DetectRunRequest, DetectRunStatus
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.detect.persistence.diagnostics import read_diagnostic_records
from biocall_studio.detect.persistence.publication import load_publication_identity
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.workspace import WorkspaceController

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def _ready_controller(qtbot, tmp_path: Path, wav_factory, **kwargs):
    source = tmp_path / "Rainforest_2026"
    wav_factory(source / "recordings" / "dawn-a.wav", frames=3_200)
    wav_factory(source / "recordings" / "dawn-b.wav", frames=4_800)
    source_bytes = {path: path.read_bytes() for path in source.rglob("*.wav")}
    controller = DetectWorkspaceController(tmp_path / "application-data", **kwargs)
    controller.choose_source_root(str(source))
    qtbot.waitUntil(lambda: controller.snapshot is not None, timeout=10_000)
    assert controller.snapshot is not None
    return controller, source_bytes


def _request(controller: DetectWorkspaceController, *, suffix: str = "0"):
    snapshot = controller.snapshot
    collection = controller.active_collection
    assert snapshot is not None and collection is not None
    token = (suffix * 32)[:32]
    if set(token) == {"0"}:
        token = "0123456789abcdef0123456789abcdef"
    return DetectRunRequest.create(
        run_id=f"drun_{token}",
        request_id=f"dreq_{token}",
        launch_id=f"launch_{token}",
        reservation_owner_id=controller.reservation_owner_id,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=snapshot.inventory_id,
        inventory_digest=snapshot.digest,
        selected_recording_keys=snapshot.included_keys,
        model_snapshot_id="mdl_0123456789abcdef0123456789abcdef",
        model_digest="b" * 64,
        settings={"fixture_contract": "lifecycle-v1"},
        artifact_id=f"pub_{token}",
    )


def _source_unchanged(source_bytes: dict[Path, bytes]) -> bool:
    return all(path.read_bytes() == payload for path, payload in source_bytes.items())


def test_real_qprocess_progress_cancel_forced_loss_and_restart(qtbot, tmp_path, wav_factory):
    """Case: IT-DET-009."""
    controller, source_bytes = _ready_controller(
        qtbot,
        tmp_path,
        wav_factory,
        worker_step_delay_seconds=0.04,
        cancel_grace_ms=150,
        kill_grace_ms=600,
    )

    success_id = controller.start_lifecycle_fixture(_request(controller), behavior="success")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.COMPLETED,
        timeout=10_000,
    )
    success = controller.current_run
    assert success is not None and success.run_id == success_id
    assert success.progress == 100
    repository = DetectRunRepository(controller.store.application_data_root, success.collection_id)
    receipt = repository.load_receipt(success)
    identity = load_publication_identity(repository.collection_root, success.artifact_id)
    assert receipt.artifact_digest == identity.artifact_digest
    assert identity.artifact_kind == "lifecycle_fixture"
    assert not any(repository.results_root.iterdir())

    cancel_request = _request(controller, suffix="1")
    controller.start_lifecycle_fixture(cancel_request, behavior="stubborn")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    controller.cancel_active_run()
    assert controller.current_run.status is DetectRunStatus.CANCELLING
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.CANCELLED,
        timeout=10_000,
    )
    assert not repository.publication_path(cancel_request.artifact_id).exists()

    loss_request = _request(controller, suffix="2")
    controller.start_lifecycle_fixture(loss_request, behavior="slow")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    process = controller.run_process
    assert process is not None and process.state() is not QProcess.ProcessState.NotRunning
    process.kill()
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.INTERRUPTED,
        timeout=10_000,
    )
    reopened = DetectWorkspaceController(tmp_path / "application-data")
    assert reopened.current_run is not None
    assert reopened.current_run.run_id == loss_request.run_id
    assert reopened.current_run.status is DetectRunStatus.INTERRUPTED
    assert _source_unchanged(source_bytes)

    shutdown_request = _request(controller, suffix="c")
    controller.start_lifecycle_fixture(shutdown_request, behavior="slow")
    qtbot.waitUntil(lambda: controller.is_run_active, timeout=5_000)
    controller.request_shutdown()
    qtbot.waitUntil(lambda: controller._shutdown_finished, timeout=10_000)
    assert controller.run_process is None
    assert controller.current_run is not None
    assert controller.current_run.status is DetectRunStatus.CANCELLED
    assert not controller._owner_lease.path.exists()
    reopened.shutdown()


def test_native_run_header_keyboard_cancel_responsiveness_and_private_stderr(
    qapp, qtbot, tmp_path, wav_factory
):
    """Case: IT-DET-010."""
    controller, source_bytes = _ready_controller(
        qtbot,
        tmp_path,
        wav_factory,
        worker_step_delay_seconds=0.04,
        cancel_grace_ms=150,
        kill_grace_ms=600,
    )
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()
    assert page.run_status_badge.text() == "Idle"

    ticks: list[bool] = []
    controller.start_lifecycle_fixture(_request(controller, suffix="3"), behavior="stderr_storm")
    assert page.active_run_badge.text() == "Preparing"
    QTimer.singleShot(30, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks), timeout=5_000)
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.COMPLETED,
        timeout=15_000,
    )
    assert page.active_run_label.text() == "Lifecycle boundary check"
    assert page.active_run_badge.text() == "Completed"
    assert page.run_button.isEnabled()
    page.view_run_button.click()
    assert page.current_route == "run"
    assert page.run_status_badge.text() == "Completed"
    assert page.open_run_log_button.isEnabled()

    log_path = controller.safe_run_log_path(controller.current_run.run_id)
    assert log_path is not None
    records, notices = read_diagnostic_records(
        DetectRunRepository(
            controller.store.application_data_root,
            controller.current_run.collection_id,
        ).collection_root,
        log_path,
    )
    serialized = json.dumps(records)
    assert not notices
    assert "/Users/field-biologist" not in serialized
    assert "private-recording.wav" not in serialized
    assert "secret-value" not in serialized
    assert "stderr truncated" in serialized

    controller.start_lifecycle_fixture(_request(controller, suffix="4"), behavior="slow")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    assert page.run_status_badge.text() == "Running"
    page.cancel_run_button.setFocus()
    qtbot.keyClick(page.cancel_run_button, Qt.Key.Key_Space)
    assert controller.current_run.status is DetectRunStatus.CANCELLING
    assert page.run_status_badge.text() == "Cancelling"
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.CANCELLED,
        timeout=10_000,
    )
    assert page.run_status_badge.text() == "Cancelled"
    assert "start a new Run" in page.run_guidance.text()
    assert _source_unchanged(source_bytes)

    controller.start_lifecycle_fixture(_request(controller, suffix="a"), behavior="fail")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.FAILED,
        timeout=10_000,
    )
    assert page.run_status_badge.text() == "Failed"
    assert "controlled lifecycle failure" in page.run_guidance.text()

    controller.start_lifecycle_fixture(_request(controller, suffix="b"), behavior="crash")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.INTERRUPTED,
        timeout=10_000,
    )
    assert page.run_status_badge.text() == "Interrupted"
    assert "start a new Run" in page.run_guidance.text()

    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    assert isinstance(page.cancel_run_button, QPushButton)
    controller.shutdown()


def test_application_close_stops_detect_worker_before_windows_exit(
    qtbot, tmp_path, wav_factory
):
    """Case: IT-DET-010."""
    train = WorkspaceController(tmp_path / "train-settings")
    coordinator = StudioCoordinator(train, detect_data_dir=tmp_path / "application-data")
    qtbot.addWidget(coordinator.shell_window)
    qtbot.addWidget(coordinator.train_window)
    coordinator.start()
    coordinator.open_workspace(WorkspaceRoute.DETECT)
    controller = coordinator.detect_controller
    controller._worker_step_delay_seconds = 0.04
    controller._cancel_grace_ms = 150
    controller._kill_grace_ms = 600
    source = tmp_path / "quit-source"
    wav_factory(source / "recordings" / "dawn.wav", frames=3_200)
    source_bytes = (source / "recordings" / "dawn.wav").read_bytes()
    controller.choose_source_root(str(source))
    qtbot.waitUntil(lambda: controller.snapshot is not None, timeout=10_000)
    controller.start_lifecycle_fixture(_request(controller, suffix="d"), behavior="stubborn")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )

    coordinator.shell_window.close()
    qtbot.waitUntil(lambda: controller._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(lambda: train._shutdown_finished, timeout=10_000)
    qtbot.waitUntil(
        lambda: not coordinator.shell_window.isVisible()
        and not coordinator.train_window.isVisible(),
        timeout=5_000,
    )

    assert controller.run_process is None
    assert controller.current_run is not None
    assert controller.current_run.status is DetectRunStatus.CANCELLED
    assert (source / "recordings" / "dawn.wav").read_bytes() == source_bytes


def test_publication_failures_source_reservation_and_restart_reconciliation(
    qtbot, tmp_path, wav_factory
):
    """Case: IT-DET-011."""
    controller, source_bytes = _ready_controller(
        qtbot,
        tmp_path,
        wav_factory,
        worker_step_delay_seconds=0.04,
        cancel_grace_ms=150,
        kill_grace_ms=600,
    )
    request = _request(controller, suffix="5")
    repository = DetectRunRepository(controller.store.application_data_root, request.collection_id)
    collision = repository.publication_path(request.artifact_id)
    collision.mkdir()
    sentinel = collision / "existing.txt"
    sentinel.write_text("do not replace")
    controller.start_lifecycle_fixture(request, behavior="success")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.FAILED,
        timeout=10_000,
    )
    assert sentinel.read_text() == "do not replace"
    assert repository.staging_directories() == ()

    permission_request = _request(controller, suffix="6")
    original_mode = stat.S_IMODE(repository.publications_root.stat().st_mode)
    repository.publications_root.chmod(0o500)
    try:
        controller.start_lifecycle_fixture(permission_request, behavior="success")
        qtbot.waitUntil(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.FAILED,
            timeout=10_000,
        )
    finally:
        repository.publications_root.chmod(original_mode)
    assert not repository.publication_path(permission_request.artifact_id).exists()

    active_request = _request(controller, suffix="7")
    controller.start_lifecycle_fixture(active_request, behavior="slow")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.RUNNING,
        timeout=5_000,
    )
    snapshot_id = controller.snapshot.inventory_id
    controller.rescan()
    assert controller.inventory_error == "An Active Detect Run reserves these inputs."
    assert controller.snapshot.inventory_id == snapshot_id
    controller.cancel_active_run()
    qtbot.waitUntil(lambda: not controller.is_run_active, timeout=10_000)

    incomplete_request = _request(controller, suffix="8")
    incomplete = repository.create(incomplete_request, title="Interrupted fixture")
    stage = repository.staging_path(incomplete.launch_id)
    stage.mkdir()
    (stage / "partial.tmp").write_text("incomplete")
    repository.save_record(
        incomplete.with_running_process(999_999, now="2026-10-28T09:00:00.000Z")
    )
    repository.reconcile()
    reconciled = repository.load_record(incomplete.run_id)
    assert reconciled.status is DetectRunStatus.INTERRUPTED
    assert not stage.exists()

    committed_request = _request(controller, suffix="9")
    controller.start_lifecycle_fixture(committed_request, behavior="commit_then_crash")
    qtbot.waitUntil(
        lambda: controller.current_run is not None
        and controller.current_run.status is DetectRunStatus.COMPLETED,
        timeout=10_000,
    )
    assert repository.load_receipt(controller.current_run).artifact_id == (
        committed_request.artifact_id
    )
    assert _source_unchanged(source_bytes)
    controller.shutdown()
