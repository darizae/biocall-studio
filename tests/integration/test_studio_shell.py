# ruff: noqa: E501 -- approved interface copy is asserted verbatim.
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from textwrap import dedent

import pytest
from alp_ui.components import Badge, FolderPicker, HelpHint, Text
from alp_ui.theme import ALPACA_LIGHT
from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QWidget,
)

from biocall_studio.review.application.controller import (
    ReviewSessionController,
    default_spectrogram_snapshot,
)
from biocall_studio.review.application.data_location import ReviewDataLocationManager
from biocall_studio.review.application.generation import (
    GenerationCancelled,
    GenerationJob,
    GenerationToken,
)
from biocall_studio.review.application.storage import (
    assess_review_cache_storage,
    plan_review_cache_generation,
)
from biocall_studio.review.domain.cache import CachePriority
from biocall_studio.review.domain.intake import (
    REVIEW_INTAKE_SCHEMA_VERSION,
    EligibleCandidate,
    ReviewIntakeManifest,
    ReviewIntakeProjection,
    ReviewRecording,
    ReviewResultKind,
    projection_digest,
)
from biocall_studio.review.domain.sessions import (
    ReviewLabel,
    ReviewSessionSource,
    ReviewSessionState,
)
from biocall_studio.review.domain.spectrograms import SpectrogramImageTier
from biocall_studio.studio.application.app import (
    create_application as create_studio_application,
)
from biocall_studio.studio.application.app import (
    default_suite_data_root,
)
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.studio.application.storage import SuiteDataPaths
from biocall_studio.studio.gui.shell import WorkspaceCard
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.run import RunStatus
from biocall_studio.train.gui.window import MainWindow
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.persistence.settings import ApplicationSettings, SettingsStore
from biocall_studio.train.workflows.dataset_build import build_dataset

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def _build_config(scan) -> BuildConfig:
    return BuildConfig(
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


def _coordinator(qtbot, controller: WorkspaceController) -> StudioCoordinator:
    create_studio_application()
    coordinator = StudioCoordinator(controller)
    qtbot.addWidget(coordinator.shell_window)
    qtbot.addWidget(coordinator.train_window)
    coordinator.start()
    qtbot.waitUntil(coordinator.shell_window.isVisible)
    return coordinator


def _finish(qtbot, coordinator: StudioCoordinator) -> None:
    if not coordinator.controller._shutdown_finished:
        coordinator.request_application_exit()
        qtbot.waitUntil(lambda: coordinator.controller._shutdown_finished, timeout=10_000)


def _create_open_review_session(coordinator: StudioCoordinator) -> str:
    candidate = EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + "1" * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key="recordings/call.wav",
        source_sha256="3" * 64,
        sample_rate_hz=8_000,
        frame_count=8_000,
        channels=1,
        start_frame=1_000,
        end_frame=2_000,
        start_time_ns=125_000_000,
        end_time_ns=250_000_000,
        cnn_target_score=0.9,
        rf_target_score=None,
        contributing_windows=1,
    )
    recording = ReviewRecording(
        ordinal=0,
        recording_ref=candidate.recording_ref,
        recording_key=candidate.recording_key,
        source_sha256=candidate.source_sha256,
        sample_rate_hz=candidate.sample_rate_hz,
        frame_count=candidate.frame_count,
        channels=candidate.channels,
        failed=False,
        error_code="",
        eligible_candidate_count=1,
    )
    manifest = ReviewIntakeManifest(
        schema_version=REVIEW_INTAKE_SCHEMA_VERSION,
        projection_digest="0" * 64,
        result_kind=ReviewResultKind.CNN,
        collection_id="det_" + "4" * 32,
        result_id="pub_" + "5" * 32,
        result_digest="6" * 64,
        publication_digest="7" * 64,
        parent_result_id=None,
        parent_result_digest=None,
        binding_revision=1,
        inventory_id="inv_" + "8" * 32,
        inventory_digest="9" * 64,
        source_time_semantics=(
            "zero_based_half_open_source_frames_with_integer_nanosecond_projection"
        ),
        recording_count=1,
        failed_recording_count=0,
        eligible_candidate_count=1,
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, (recording,), (candidate,)),
    )
    projection = ReviewIntakeProjection(manifest, (recording,), (candidate,))
    settings = default_spectrogram_snapshot()
    coordinator.review_controller.ensure_default_preset(
        settings, saved_at="2026-11-06T09:00:00.000Z"
    )
    session = coordinator.review_controller.store.create_session(
        name="Retained migration review",
        source=ReviewSessionSource.from_projection(
            projection,
            score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
            eligibility_threshold=0.5,
        ),
        candidates=(candidate,),
        settings=settings,
        owner_id=coordinator.review_controller.owner_id,
        created_at="2026-11-06T09:01:00.000Z",
        session_id="rsn_" + "a" * 32,
    )
    coordinator.shell_window.review_page.open_session(session.session_id)
    return session.session_id


def _start_blocked_review_generation(coordinator: StudioCoordinator) -> str:
    page = coordinator.review_page
    state = page.current_state
    assert state is not None
    snapshot = coordinator.review_controller.store.load_settings(state.session.session_id)
    plan = plan_review_cache_generation(
        missing_count=1,
        existing_file_sizes=(),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest=snapshot.settings_digest,
        calibration=None,
    )
    estimate = assess_review_cache_storage(plan, cache_root=page.cache.root)
    assert estimate.can_start
    started = threading.Event()

    def render(_prepared, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.005)
        raise GenerationCancelled("cancelled by application exit")

    job = GenerationJob(
        content_key="spec_" + "f" * 64,
        tier=SpectrogramImageTier.THUMBNAIL,
        priority=CachePriority.GENERATE_ALL,
        token=GenerationToken(
            session_id=state.session.session_id,
            settings_epoch=state.session.settings_epoch,
            settings_digest=snapshot.settings_digest,
            source_sha256="3" * 64,
        ),
        render=render,
    )
    batch_id = page.supervisor.submit_bulk(
        (job,),
        storage_estimate=estimate,
        confirmed=estimate.requires_confirmation,
    )
    page._generation_batch_id = batch_id
    page._begin_owned_operation("Spectrogram generation")
    page._generation_timer.start()
    assert started.wait(5)
    return batch_id


def _ready_collection(tmp_path: Path, collection_factory, *, source_count: int = 3):
    root = collection_factory(tmp_path / "collection", source_count=source_count)
    scan = publish_collection_metadata(root, scan_collection(root))
    return root, scan


def test_studio_launchpad_uses_one_themed_application_and_accessible_native_cards(
    qapp, qtbot, tmp_path
):
    """Case: IT-STU-001."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    shell = coordinator.shell_window

    assert QApplication.instance() is qapp is coordinator.app
    assert qapp.applicationName() == "biocall-studio"
    assert qapp.applicationDisplayName() == "BioCall Studio"
    assert qapp.property("alp_ui_theme") is not None
    assert not qapp.quitOnLastWindowClosed()
    assert shell.windowTitle() == "BioCall Studio"
    assert not shell.windowIcon().isNull()
    assert shell.current_workspace is WorkspaceRoute.STUDIO

    cards = shell.launchpad.findChildren(WorkspaceCard)
    assert [card.accessibleName() for card in cards] == [
        "Train workspace",
        "Detect workspace",
        "Review workspace",
    ]
    assert all(card.accessibleDescription() for card in cards)
    assert [card.action_button.text() for card in cards] == [
        "Open Train",
        "Open Detect",
        "Open Review",
    ]
    assert {card.action_button.variant for card in cards} == {"outline"}
    assert {card.action_button.component_size for card in cards} == {"large"}
    shell.launchpad.train_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.train_card.action_button, Qt.Key.Key_Space)
    assert coordinator.train_window.isVisible()
    assert not shell.isVisible()

    coordinator.show_studio()
    _finish(qtbot, coordinator)


def test_review_sidebar_routes_active_state_and_responsive_accessibility(qtbot, tmp_path):
    """Case: IT-REVW-013."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    coordinator.open_workspace(WorkspaceRoute.REVIEW)
    page = coordinator.review_page
    assert not coordinator.shell_window.global_header.isVisible()
    assert tuple(page.navigation.buttons) == (
        "sessions",
        "choose_result",
        "review",
        "spectrograms",
        "exports",
        "settings",
    )
    assert page.navigation.active_route == "choose_result"

    for route, expected_page in (
        ("sessions", page.sessions_page),
        ("choose_result", page.landing_page),
        ("exports", page.exports_page),
        ("settings", page.data_settings_page),
    ):
        page.navigation.buttons[route].click()
        assert page.navigation.active_route == route
        assert page.currentWidget() is expected_page

    page.resize(700, 720)
    qtbot.waitUntil(lambda: page.navigation.compact)
    assert all(button.text() for button in page.navigation.buttons.values())
    page.resize(520, 720)
    qtbot.waitUntil(lambda: page.navigation.narrow)
    assert all(not button.text() for button in page.navigation.buttons.values())
    assert all(button.accessibleName() for button in page.navigation.buttons.values())
    coordinator.shell_window.resize(520, 720)
    qtbot.waitUntil(lambda: coordinator.shell_window.width() == 520)
    assert page.navigation.narrow
    _finish(qtbot, coordinator)


def test_review_data_folder_moves_in_app_and_reopens_without_touching_detect(qtbot, tmp_path):
    """Case: IT-REVW-014."""
    create_studio_application()
    suite_root = tmp_path / "application-data"
    train = WorkspaceController(suite_root / "train" / "v1")
    coordinator = StudioCoordinator(train, detect_data_dir=suite_root)
    qtbot.addWidget(coordinator.shell_window)
    qtbot.addWidget(coordinator.train_window)
    coordinator.start()

    session_id = _create_open_review_session(coordinator)
    session = coordinator.review_controller.store.get_session(session_id)
    session = coordinator.review_controller.set_label(
        session_id,
        "cand_" + "1" * 32,
        ReviewLabel.CALL,
        expected_revision=session.revision,
        modified_at="2026-11-06T09:02:00.000Z",
    ).session
    blocked_target = tmp_path / "blocked-while-open"
    coordinator.review_page.show_data_settings()
    coordinator.request_review_data_folder_change(blocked_target)
    assert coordinator.review_controller.store.root == suite_root / "review" / "v1"
    assert coordinator.review_page.data_settings_page.status_label.text() == (
        "Close the open Review session before changing the folder."
    )
    coordinator.review_controller.close_session(
        session_id,
        expected_revision=session.revision,
        closed_at="2026-11-06T09:03:00.000Z",
    )

    detect_marker = suite_root / "detect" / "v1" / "rv09-marker"
    detect_marker.parent.mkdir(parents=True, exist_ok=True)
    detect_marker.write_bytes(b"detect-owned")
    target = tmp_path / "selected-review-data"
    coordinator.open_workspace(WorkspaceRoute.REVIEW)
    coordinator.review_page.show_data_settings()

    def accept_move() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton().text() == "Cancel"
        next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Move existing data"
        ).click()

    QTimer.singleShot(0, accept_move)
    coordinator.review_page.data_settings_page.folder_picker.setFolderPath(str(target))
    qtbot.waitUntil(
        lambda: coordinator.review_controller.store.root == target,
        timeout=20_000,
    )

    assert ReviewDataLocationManager(suite_root).current_root() == target
    assert (target / "sessions.sqlite3").is_file()
    migrated = coordinator.review_controller.store.get_session(session_id)
    assert migrated.state is ReviewSessionState.CLOSED
    assert migrated.call_count == 1
    assert detect_marker.read_bytes() == b"detect-owned"
    assert coordinator.review_page.currentWidget() is coordinator.review_page.data_settings_page
    assert "moved" in coordinator.review_page.data_settings_page.status_label.text().casefold()

    existing = tmp_path / "existing-review-data"
    existing_controller = ReviewSessionController(suite_root, review_data_root=existing)
    settings = default_spectrogram_snapshot()
    existing_controller.ensure_default_preset(settings, saved_at="2026-11-06T09:05:00.000Z")
    existing_controller.create_preset(
        name="Alpaca hum detail",
        effective_settings=settings.effective_settings,
        saved_at="2026-11-06T09:06:00.000Z",
    )
    existing_controller.shutdown()
    existing_database = (existing / "sessions.sqlite3").read_bytes()

    def accept_existing() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton().text() == "Cancel"
        next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Use this data"
        ).click()

    QTimer.singleShot(0, accept_existing)
    coordinator.review_page.data_settings_page.folder_picker.setFolderPath(str(existing))
    qtbot.waitUntil(
        lambda: coordinator.review_controller.store.root == existing,
        timeout=20_000,
    )

    assert ReviewDataLocationManager(suite_root).current_root() == existing
    assert coordinator.review_controller.intake.store.root == existing
    assert (existing / "sessions.sqlite3").read_bytes() == existing_database
    assert target.is_dir()
    assert {preset.preset_name for preset in coordinator.review_controller.list_presets()} == {
        "Default",
        "Alpaca hum detail",
    }
    assert "opened" in coordinator.review_page.data_settings_page.status_label.text().casefold()
    _finish(qtbot, coordinator)


def test_approved_launch_language_and_light_theme_survive_host_dark_appearance(
    qapp, qtbot, tmp_path
):
    """Case: IT-UI-006."""
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    shell = coordinator.shell_window

    assert qapp.property("alp_ui_theme") == ALPACA_LIGHT
    assert qapp.palette().window().color().name().upper() == (
        ALPACA_LIGHT.colors.background.upper()
    )
    assert qapp.palette().windowText().color().name().upper() == (ALPACA_LIGHT.colors.text.upper())
    labels = [label.text() for label in shell.launchpad.findChildren(QLabel)]
    assert labels.count("From raw audio to corpora") == 1
    assert "CHOOSE A WORKSPACE" not in labels
    assert "From recordings to evidence" not in labels
    assert (
        "Train models, detect candidate calls, and review results in one workspace." not in labels
    )
    assert all("theme" not in text.casefold() for text in labels)
    assert not any(
        "theme" in button.text().casefold() for button in shell.launchpad.findChildren(QPushButton)
    )

    for width in (1180, 700):
        shell.resize(width, 790)
        qtbot.waitUntil(lambda width=width: shell.launchpad._compact == (width < 900))
        assert shell.launchpad.findChildren(Text)
        assert shell.launchpad.grab().size().width() > 0
    _finish(qtbot, coordinator)


@pytest.mark.native_cocoa
def test_native_cocoa_light_scheme_survives_host_dark_appearance(qapp, qtbot, tmp_path):
    """Case: IT-UI-006."""
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    assert qapp.styleHints().colorScheme() is Qt.ColorScheme.Light
    _finish(qtbot, coordinator)


def test_train_window_controller_route_draft_binding_and_back_action_are_retained(
    qtbot, tmp_path, collection_factory
):
    """Case: IT-STU-002."""
    root, scan = _ready_collection(tmp_path, collection_factory)
    input_bytes = {path: path.read_bytes() for path in root.rglob("*.wav")}
    dataset = build_dataset(root, scan, _build_config(scan), dataset_id="dataset-studio-draft")
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)
    coordinator = _coordinator(qtbot, controller)
    train = coordinator.train_window
    qtbot.waitUntil(lambda: controller.scan_result is not None, timeout=10_000)

    coordinator.open_workspace(WorkspaceRoute.TRAIN)
    retained_window = train
    retained_controller = train.controller
    train.open_training(dataset.dataset_id)
    retained_draft = train.training_page.draft
    retained_draft.set("training.max_epochs", 3)
    assert train.current_route == "training"
    assert train.training_page.draft_open

    train.resize(700, 780)
    qtbot.waitUntil(lambda: train.is_compact)
    assert train.back_to_studio_button is not None
    assert train.back_to_studio_button.isVisible()
    train.back_to_studio_button.setFocus()
    qtbot.keyClick(train.back_to_studio_button, Qt.Key.Key_Space)
    assert coordinator.shell_window.isVisible()
    assert not train.isVisible()

    coordinator.shell_window.launchpad.train_card.action_button.setFocus()
    qtbot.keyClick(
        coordinator.shell_window.launchpad.train_card.action_button,
        Qt.Key.Key_Space,
    )
    assert coordinator.train_window is retained_window
    assert coordinator.train_window.controller is retained_controller
    assert train.current_route == "training"
    assert train.training_page.draft is retained_draft
    assert retained_draft.value("training.max_epochs") == 3
    assert controller.collection_path == root.resolve()
    assert {path: path.read_bytes() for path in input_bytes} == input_bytes

    _finish(qtbot, coordinator)


def test_real_worker_survives_switch_and_hidden_workspace_quit_uses_train_policy(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-STU-003 (real short QProcess Dataset Build Worker)."""
    root, scan = _ready_collection(tmp_path, collection_factory)
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=0.5,
        cancel_grace_ms=500,
        kill_grace_ms=1_000,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    coordinator = _coordinator(qtbot, controller)
    qtbot.waitUntil(lambda: controller.scan_result is not None, timeout=10_000)
    coordinator.open_workspace(WorkspaceRoute.TRAIN)

    run_id = controller.start_dataset_build(_build_config(scan), dataset_id="dataset-studio-active")
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=10_000,
    )
    process = controller._run_process
    assert process is not None and process.state() is not QProcess.ProcessState.NotRunning

    coordinator.show_studio()
    qtbot.wait(150)
    assert coordinator.shell_window.isVisible()
    assert controller.active_run is not None
    assert controller.active_run.run_id == run_id
    assert controller._run_process is process

    coordinator.shell_window.close()
    dialog = coordinator.exit_dialog
    assert coordinator.shell_window.isVisible()
    assert dialog is not None and dialog.isVisible()
    assert dialog.defaultButton().text() == "Keep app open"
    assert dialog.focusWidget() is dialog.defaultButton()
    assert len([widget for widget in qapp.topLevelWidgets() if widget is dialog]) == 1
    dialog.defaultButton().click()
    assert controller.active_run is not None
    assert controller.active_run.run_id == run_id
    assert controller._run_process is process

    coordinator.show_studio()
    coordinator.shell_window.close()
    dialog = coordinator.exit_dialog
    assert dialog is not None
    stop_button = next(
        button for button in dialog.buttons() if button.text() == "Stop work and Exit"
    )
    stop_button.click()
    qtbot.waitUntil(lambda: controller._shutdown_finished, timeout=15_000)
    qtbot.waitUntil(lambda: coordinator.detect_controller._shutdown_finished, timeout=15_000)
    assert controller._run_process is None
    assert not coordinator.shell_window.isVisible()
    assert not coordinator.train_window.isVisible()


def test_scan_remains_live_on_studio_and_application_close_waits_for_it(
    qtbot, tmp_path, collection_factory
):
    """Case: IT-STU-003 (real Collection Scan)."""
    root, scan = _ready_collection(tmp_path, collection_factory, source_count=6)
    controller = WorkspaceController(
        tmp_path / "settings",
        scan_step_delay_seconds=0.15,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    coordinator = _coordinator(qtbot, controller)
    qtbot.waitUntil(lambda: controller.is_scanning, timeout=5_000)
    assert coordinator.shell_window.isVisible()

    coordinator.shell_window.close()

    assert coordinator.train_window.close_dialog is None
    qtbot.waitUntil(lambda: controller._shutdown_finished, timeout=10_000)
    assert controller._scan_thread is None
    assert not controller.is_scanning


def test_canonical_worker_protocol_and_train_binding_share_one_suite_identity(
    qapp, qtbot, tmp_path, collection_factory
):
    """Case: IT-STU-004."""
    create_studio_application()
    studio_name = qapp.applicationName()
    established_settings = SuiteDataPaths.from_root(default_suite_data_root()).train
    assert qapp.applicationName() == studio_name == "biocall-studio"
    assert established_settings.parts[-2:] == ("train", "v1")
    default_controller = WorkspaceController()
    assert default_controller.settings_file.parent == established_settings
    default_controller.shutdown()

    root, scan = _ready_collection(tmp_path, collection_factory, source_count=1)
    settings_dir = tmp_path / "persisted-settings"
    SettingsStore(settings_dir / "settings.json").save(
        ApplicationSettings(root.resolve(), scan.collection_id)
    )
    controller = WorkspaceController(settings_dir)
    coordinator = _coordinator(qtbot, controller)
    qtbot.waitUntil(lambda: controller.scan_result is not None, timeout=10_000)
    assert controller.collection_path == root.resolve()
    assert controller.collection_id == scan.collection_id
    program, arguments = controller._worker_command(["--worker", "train-dataset-build"])
    assert program == sys.executable
    assert arguments[:3] == ["-m", "biocall_studio", "--worker"]
    _finish(qtbot, coordinator)

    direct = MainWindow(WorkspaceController(tmp_path / "direct-train-settings"))
    qtbot.addWidget(direct)
    assert direct.back_to_studio_button is None
    direct.show()
    direct.close()
    assert not direct.isVisible()

    code = dedent("""
        import sys
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from biocall_studio.cli import main
        from biocall_studio.studio.gui.shell import StudioWindow
        from biocall_studio.train.gui.window import MainWindow

        def inspect_and_quit():
            studio = next(w for w in QApplication.topLevelWidgets() if isinstance(w, StudioWindow))
            train = next(w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow))
            assert studio.isVisible()
            assert not train.isVisible()
            assert train.controller.settings_file == Path(sys.argv[1]) / 'train/v1/settings.json'
            assert QApplication.instance().applicationName() == 'biocall-studio'
            print('canonical Studio entry retained Train settings')
            studio.close()

        QTimer.singleShot(0, inspect_and_quit)
        raise SystemExit(main(['--settings-dir', sys.argv[1]]))
    """)
    child_settings = tmp_path / "child-settings"
    result = subprocess.run(
        [sys.executable, "-c", code, str(child_settings)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "canonical Studio entry retained Train settings" in result.stdout


def test_detect_collection_setup_and_review_workspace_are_keyboard_reachable(qtbot, tmp_path):
    """Case: IT-STU-005."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    shell = coordinator.shell_window

    shell.launchpad.detect_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.detect_card.action_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.DETECT
    assert not shell.global_header.isVisible()
    assert isinstance(shell.detect_page.focusWidget(), QPushButton)
    assert shell.detect_page.focusWidget().accessibleName() == "Choose Train Model folder"
    assert len(shell.detect_page.findChildren(FolderPicker)) == 4
    assert {
        "More about Detection Model",
        "More about Recordings folder",
        "More about Recording inclusion",
        "More about Minimum detection score",
        "More about Window overlap",
        "More about Combine nearby candidates",
    } <= {hint.accessibleName() for hint in shell.detect_page.findChildren(HelpHint)}
    assert len(shell.detect_page.findChildren(QComboBox)) == 3
    assert not shell.detect_page.result_explorer.history_select.isEnabled()
    assert shell.detect_page.result_explorer.history_select.accessibleName() == "Result history"
    assert not shell.detect_page.start_detection_button.isEnabled()
    assert all(not widget.isVisible() for widget in shell.detect_page.findChildren(QProgressBar))
    assert all(not widget.isVisible() for widget in shell.detect_page.findChildren(QTableView))
    detect_text = " ".join(label.text() for label in shell.detect_page.findChildren(QLabel))
    assert "Recordings folder" in detect_text
    assert "Detection Model" in detect_text
    assert shell.detect_page.start_detection_button.text() == "Start detection"
    shell.detect_page.back_button.setFocus()
    qtbot.keyClick(shell.detect_page.back_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.STUDIO
    assert shell.global_header.isVisible()

    shell.launchpad.review_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.review_card.action_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.REVIEW
    qtbot.waitUntil(lambda: shell.focusWidget() is shell.review_page.landing_page.results)
    assert not shell.global_header.isVisible()
    assert shell.review_page.navigation.back_button.isVisible()
    review_text = " ".join(label.text() for label in shell.review_page.findChildren(QLabel))
    assert "Choose Result" in review_text
    assert "Review is coming later" not in review_text
    assert all(
        forbidden not in (detect_text + review_text).lower()
        for forbidden in ("simulated", "demo", "prototype")
    )
    shell.review_page.navigation.back_button.setFocus()
    qtbot.keyClick(shell.review_page.navigation.back_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.STUDIO
    assert not coordinator.controller.settings_file.exists()

    _finish(qtbot, coordinator)


def test_open_review_survives_navigation_and_one_exit_policy_fails_closed(
    qapp, qtbot, tmp_path, monkeypatch
):
    """Case: IT-REVW-011."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    session_id = _create_open_review_session(coordinator)
    page = coordinator.shell_window.review_page
    assert page.current_state is not None
    page.session_page.name_input.control.setCursorPosition(
        len(page.session_page.name_input.control.text())
    )
    page.session_page.render_state(page.current_state)
    assert page.session_page.name_input.control.cursorPosition() == 0
    page.current_state.scroll_offset = 17

    coordinator.open_workspace(WorkspaceRoute.REVIEW)
    assert coordinator.shell_window.current_workspace is WorkspaceRoute.REVIEW
    assert page.current_state.session.session_id == session_id
    coordinator.open_workspace(WorkspaceRoute.DETECT)
    assert coordinator.review_controller.store.open_session().session_id == session_id
    assert coordinator.review_controller.store.load_position(session_id).scroll_offset == 17
    coordinator.open_workspace(WorkspaceRoute.REVIEW)
    assert page.current_state.session.session_id == session_id
    assert page.current_state.scroll_offset == 17

    for route in (WorkspaceRoute.REVIEW, WorkspaceRoute.DETECT, WorkspaceRoute.STUDIO):
        coordinator.open_workspace(route)
        coordinator.shell_window.close()
        route_dialog = coordinator.exit_dialog
        assert route_dialog is not None and route_dialog.isVisible()
        assert route_dialog.text() == "A Review session is still open. Save and exit?"
        route_dialog.defaultButton().click()
        qtbot.waitUntil(lambda: coordinator.exit_dialog is None)
        assert coordinator.review_controller.store.open_session().session_id == session_id

    batch_id = _start_blocked_review_generation(coordinator)

    coordinator.open_workspace(WorkspaceRoute.TRAIN)
    coordinator.train_window.close()
    dialog = coordinator.exit_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.text() == "A Review session is still open. Save and exit?"
    assert {button.text() for button in dialog.buttons()} == {
        "Keep app open",
        "Save and Exit",
    }
    assert dialog.defaultButton().text() == "Keep app open"
    assert dialog.escapeButton().text() == "Keep app open"
    assert dialog.informativeText().count("Spectrogram generation in Review") == 1
    coordinator.request_application_exit()
    assert coordinator.exit_dialog is dialog
    assert (
        len(
            [
                widget
                for widget in qapp.topLevelWidgets()
                if widget.objectName() == "studioExitDialog" and widget.isVisible()
            ]
        )
        == 1
    )
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: coordinator.exit_dialog is None)
    assert coordinator.review_controller.store.open_session().session_id == session_id
    assert coordinator.train_window.isVisible()
    assert page.active_operation is not None
    assert not page.supervisor.progress(batch_id).done

    original_cancel = page.supervisor.cancel
    monkeypatch.setattr(
        page.supervisor,
        "cancel",
        lambda _batch_id: (_ for _ in ()).throw(RuntimeError("injected stop failure")),
    )
    coordinator.request_application_exit()
    dialog = coordinator.exit_dialog
    assert dialog is not None
    next(button for button in dialog.buttons() if button.text() == "Save and Exit").click()
    qtbot.waitUntil(
        lambda: (
            coordinator.exit_failure_dialog is not None
            and coordinator.exit_failure_dialog.isVisible()
        )
    )
    failure = coordinator.exit_failure_dialog
    assert failure is not None
    assert "Review work couldn't be stopped" in failure.text()
    assert coordinator.review_controller.store.open_session().session_id == session_id
    assert page.active_operation is not None
    assert not coordinator._application_exit_complete
    coordinator.request_application_exit()
    assert coordinator.exit_failure_dialog is failure
    assert coordinator.exit_dialog is None
    failure.defaultButton().click()
    monkeypatch.setattr(page.supervisor, "cancel", original_cancel)

    original_checkpoint = page.checkpoint_open_session_for_exit
    monkeypatch.setattr(
        page,
        "checkpoint_open_session_for_exit",
        lambda: (_ for _ in ()).throw(OSError("injected checkpoint failure")),
    )
    coordinator.request_application_exit()
    dialog = coordinator.exit_dialog
    assert dialog is not None
    next(button for button in dialog.buttons() if button.text() == "Save and Exit").click()
    qtbot.waitUntil(
        lambda: (
            coordinator.exit_failure_dialog is not None
            and coordinator.exit_failure_dialog.isVisible()
        )
    )
    failure = coordinator.exit_failure_dialog
    assert failure is not None
    assert "Review session couldn't be saved" in failure.text()
    assert coordinator.review_controller.store.open_session().session_id == session_id
    assert page.supervisor.progress(batch_id).done
    assert page.active_operation is None
    assert not coordinator._application_exit_complete
    failure.defaultButton().click()

    monkeypatch.setattr(page, "checkpoint_open_session_for_exit", original_checkpoint)
    coordinator.request_application_exit()
    dialog = coordinator.exit_dialog
    assert dialog is not None
    next(button for button in dialog.buttons() if button.text() == "Save and Exit").click()
    qtbot.waitUntil(lambda: coordinator._application_exit_complete, timeout=15_000)
    assert (
        coordinator.review_controller.store.get_session(session_id).state
        is ReviewSessionState.CLOSED
    )
    assert not coordinator.shell_window.isVisible()
    assert not coordinator.train_window.isVisible()


def test_restart_recovers_the_same_open_review_session_after_owner_loss(qtbot, tmp_path):
    """Case: IT-REVW-011 (restart and orphan-owner safety)."""
    create_studio_application()
    suite_data = tmp_path / "suite-data"
    first = StudioCoordinator(
        WorkspaceController(tmp_path / "first-settings"),
        detect_data_dir=suite_data,
    )
    qtbot.addWidget(first.shell_window)
    qtbot.addWidget(first.train_window)
    first.start()
    session_id = _create_open_review_session(first)
    assert first.review_page.current_state is not None
    first.review_page.current_state.scroll_offset = 29
    first.review_page.leave_workspace()
    previous_owner = first.review_controller.owner_id

    # Model abrupt owner loss without invoking the orderly Save-and-Exit closure.
    first.review_page.shutdown()
    first.review_controller.shutdown()
    first.detect_controller.shutdown()
    first.controller.shutdown()
    first.shell_window.hide()
    first.train_window.hide()

    second = StudioCoordinator(
        WorkspaceController(tmp_path / "second-settings"),
        detect_data_dir=suite_data,
    )
    qtbot.addWidget(second.shell_window)
    qtbot.addWidget(second.train_window)
    assert second.review_page.current_state is not None
    assert second.review_page.current_state.session.session_id == session_id
    assert second.review_page.current_state.scroll_offset == 29
    recovered = second.review_controller.store.open_session()
    assert recovered is not None
    assert recovered.session_id == session_id
    assert recovered.owner_id == second.review_controller.owner_id
    assert recovered.owner_id != previous_owner

    second.start()
    second.request_application_exit()
    dialog = second.exit_dialog
    assert dialog is not None
    next(button for button in dialog.buttons() if button.text() == "Save and Exit").click()
    qtbot.waitUntil(lambda: second._application_exit_complete, timeout=15_000)
    assert second.review_controller.store.get_session(session_id).state is ReviewSessionState.CLOSED


def test_detect_new_export_entry_is_gone_while_history_reader_and_review_export_remain(
    qtbot, tmp_path
):
    """Case: IT-REVW-012."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    detect = coordinator.detect_controller
    page = coordinator.shell_window.detect_page

    before = tuple(sorted(path for path in tmp_path.rglob("exp_*.json") if path.is_file()))
    with pytest.raises(ValueError, match="Unknown Detect route"):
        page._set_route("export-new")
    assert tuple(sorted(path for path in tmp_path.rglob("exp_*.json") if path.is_file())) == before

    assert not hasattr(page, "export_page")
    assert not hasattr(page.result_explorer, "export_button")
    assert not hasattr(page.export_history_page, "new_button")
    assert not hasattr(detect, "prepare_export_plan")
    assert not hasattr(detect, "start_export")
    assert not hasattr(detect, "retry_save_export_history")
    assert callable(detect.select_export)
    assert hasattr(coordinator.shell_window.review_page, "export_page")
    assert all(
        button.text() not in {"New export", "Plan corpus export", "Export corpus"}
        for button in page.findChildren(QPushButton)
    )
    coordinator.open_workspace(WorkspaceRoute.DETECT)
    page._set_route("exports")
    qtbot.waitUntil(lambda: page.focusWidget() is page.export_history_page.empty)
    assert not page.export_history_page.open_button.isEnabled()

    _finish(qtbot, coordinator)


def test_detect_routes_use_approved_help_plain_language_and_compact_result_states(qtbot, tmp_path):
    """Case: IT-DET-024."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    page = coordinator.shell_window.detect_page
    approved_help = {
        "Minimum detection score": "Only results at or above this score are kept. Higher scores usually return fewer results.",
        "Window overlap": "How much each scan window overlaps the next. More overlap takes longer.",
        "Combine nearby candidates": "Joins nearby results when the gap between them is no larger than this value. Overlapping results are always joined.",
        "Detection Model": "A model trained in BioCall Studio that searches your recordings for possible calls.",
        "Recordings folder": "The folder of WAV files you want to search. BioCall Studio remembers it so you can relink the folder if it moves.",
        "Recording inclusion": "Included recordings are searched. Excluded and undecided recordings are skipped.",
        "RF refinement": "Optionally use a Random Forest model to check the calls found by the detection model. The original results stay unchanged.",
        "Estimated output": "Approximate space the finished files will use.",
        "Space while running": "Includes temporary files. Some are removed when the task finishes.",
    }
    actual_help = {
        hint.accessibleName().removeprefix("More about "): hint.toolTip()
        for hint in page.findChildren(HelpHint)
    }
    assert len(page.findChildren(HelpHint)) == 11
    assert actual_help == approved_help
    approved_ids = {
        "CTX-01": "Minimum detection score",
        "CTX-02": "Window overlap",
        "CTX-03": "Combine nearby candidates",
        "CTX-04": "Detection Model",
        "CTX-05": "Recordings folder",
        "CTX-06": "Recording inclusion",
        "CTX-08": None,
        "CTX-09": "RF refinement",
        "REV05-ESTIMATED-OUTPUT": "Estimated output",
        "REV05-SPACE-WHILE-RUNNING": "Space while running",
    }
    actual_ids = {
        hint.objectName(): hint.accessibleName().removeprefix("More about ")
        for hint in page.findChildren(HelpHint)
    }
    assert actual_ids == {
        copy_id: subject for copy_id, subject in approved_ids.items() if subject is not None
    }
    assert "CTX-08" not in actual_ids
    assert all(
        hint.focusPolicy() != Qt.FocusPolicy.NoFocus
        and hint.accessibleDescription() == hint.toolTip()
        for hint in page.findChildren(HelpHint)
    )

    visible = " ".join(label.text() for label in page.findChildren(QLabel))
    for rejected in (
        "Choose a CNN Model published by Train.",
        "Choose a Train Model folder.",
        "manifest",
        "checksum",
        "runtime structure",
        "Detect Collection",
    ):
        assert rejected.casefold() not in visible.casefold()
    assert "recordings folder" in visible.casefold()

    interface_copy: list[str] = []
    for widget in page.findChildren(QWidget):
        interface_copy.extend(
            text
            for text in (
                widget.accessibleName(),
                widget.accessibleDescription(),
                widget.toolTip(),
                widget.whatsThis(),
            )
            if text
        )
        if isinstance(widget, (QLabel, QPushButton)):
            interface_copy.append(widget.text())
    joined_copy = "\n".join(interface_copy)
    for rejected in (
        "manifest",
        "checksum",
        "runtime structure",
        "schema",
        "digest",
        "publication",
        "immutable",
        "provenance",
        "source-time",
        "inventory",
        "published",
    ):
        assert rejected.casefold() not in joined_copy.casefold()
    assert re.search(r"\bworker\b", joined_copy, flags=re.IGNORECASE) is None

    incompatible = tmp_path / "not-a-model"
    incompatible.mkdir()
    page.model_picker.folderChanged.emit(str(incompatible))
    qtbot.waitUntil(lambda: page.model_status_badge.text() == "Incompatible", timeout=10_000)
    assert page.model_detail.text() == (
        "This folder does not contain a compatible BioCall Studio model. "
        "Choose a different model folder."
    )
    incompatible_copy = " ".join(
        label.text() for label in page.findChildren(QLabel) if label.isVisibleTo(page)
    )
    assert incompatible_copy.count(page.model_detail.text()) == 1

    explorer = page.result_explorer
    assert isinstance(explorer.state_badge, Badge)
    approved_states = {
        "available": (False, "", "", ""),
        "partial": (True, "Some files failed", "warning", "View file errors"),
        "empty": (True, "No calls found", "neutral", ""),
        "stale": (True, "Recordings changed", "warning", "Review recordings"),
        "source-unavailable": (True, "Folder unavailable", "danger", "Relink folder"),
    }
    for key, (visible, status, intent, action) in approved_states.items():
        explorer._set_state(key)
        assert explorer.state_row.isVisibleTo(explorer) is visible
        if visible:
            assert explorer.state_badge.text() == status
            assert explorer.state_badge.intent == intent
            assert explorer.state_action.text() == action
            assert explorer.state_action.isVisibleTo(explorer) is bool(action)

    _finish(qtbot, coordinator)


def test_native_workspace_screens_render_at_normal_and_compact_widths(qtbot, tmp_path):
    """Case: IT-STU-006; pytest grabs are supplemental to committed native evidence."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    captures = []
    for width, label in ((1180, "normal"), (700, "compact")):
        coordinator.show_studio()
        shell = coordinator.shell_window
        shell.resize(width, 790)
        qtbot.wait(50)
        path = tmp_path / f"studio-{label}.png"
        assert shell.grab().save(str(path))
        captures.append(path)

        coordinator.open_workspace(WorkspaceRoute.DETECT)
        path = tmp_path / f"detect-{label}.png"
        assert shell.grab().save(str(path))
        captures.append(path)

        coordinator.open_workspace(WorkspaceRoute.REVIEW)
        path = tmp_path / f"review-{label}.png"
        assert shell.grab().save(str(path))
        captures.append(path)

        coordinator.open_workspace(WorkspaceRoute.TRAIN)
        train = coordinator.train_window
        train.resize(width, 790)
        qtbot.wait(50)
        assert train.back_to_studio_button is not None
        assert train.back_to_studio_button.isVisible()
        path = tmp_path / f"train-{label}.png"
        assert train.grab().save(str(path))
        captures.append(path)

    assert len(captures) == 8
    assert all(path.stat().st_size > 0 for path in captures)
    _finish(qtbot, coordinator)
