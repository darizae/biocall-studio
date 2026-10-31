# ruff: noqa: E501 -- approved interface copy is asserted verbatim.
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from alp_ui.components import Badge, FolderPicker, HelpHint, Text
from alp_ui.theme import ALPACA_LIGHT
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableView,
    QWidget,
)

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
        "Coming later",
    ]
    shell.launchpad.train_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.train_card.action_button, Qt.Key.Key_Space)
    assert coordinator.train_window.isVisible()
    assert not shell.isVisible()

    coordinator.show_studio()
    _finish(qtbot, coordinator)


def test_approved_launch_language_and_light_theme_survive_host_dark_appearance(
    qapp, qtbot, tmp_path
):
    """Case: IT-UI-006."""
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    shell = coordinator.shell_window

    assert qapp.styleHints().colorScheme() is Qt.ColorScheme.Light
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
    dialog = coordinator.train_window.close_dialog
    assert coordinator.train_window.isVisible()
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
    dialog = coordinator.train_window.close_dialog
    assert dialog is not None
    stop_button = next(
        button for button in dialog.buttons() if button.text() == "Stop Run and Exit"
    )
    stop_button.click()
    qtbot.waitUntil(lambda: controller._shutdown_finished, timeout=15_000)
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


def test_detect_collection_setup_and_review_placeholder_are_keyboard_reachable(qtbot, tmp_path):
    """Case: IT-STU-005."""
    coordinator = _coordinator(qtbot, WorkspaceController(tmp_path / "settings"))
    shell = coordinator.shell_window

    shell.launchpad.detect_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.detect_card.action_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.DETECT
    assert isinstance(shell.detect_page.focusWidget(), QPushButton)
    assert shell.detect_page.focusWidget().accessibleName() == "Choose Train Model folder"
    assert len(shell.detect_page.findChildren(FolderPicker)) == 5
    assert {
        "More about Detection Model",
        "More about Recordings folder",
        "More about Recording inclusion",
        "More about Minimum detection score",
        "More about Window overlap",
        "More about Combine nearby candidates",
        "More about Corpus export formats",
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

    shell.launchpad.review_card.action_button.setFocus()
    qtbot.keyClick(shell.launchpad.review_card.action_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.REVIEW
    qtbot.waitUntil(lambda: shell.focusWidget() is shell.review_page.back_button)
    assert shell.review_page.findChildren(QComboBox) == []
    review_text = " ".join(label.text() for label in shell.review_page.findChildren(QLabel))
    assert "Review is coming later" in review_text
    assert all(
        forbidden not in (detect_text + review_text).lower()
        for forbidden in ("simulated", "demo", "prototype")
    )
    qtbot.keyClick(shell.review_page.back_button, Qt.Key.Key_Space)
    assert shell.current_workspace is WorkspaceRoute.STUDIO
    assert not coordinator.controller.settings_file.exists()

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
        "Corpus export formats": "Individual snippets creates one WAV per selected call. Concatenated creates one WAV and a Raven table, and requires matching audio formats.",
        "RF refinement": "Optionally use a Random Forest model to check the calls found by the detection model. The original results stay unchanged.",
        "Result selection": "Selections are saved separately for each result.",
    }
    actual_help = {
        hint.accessibleName().removeprefix("More about "): hint.toolTip()
        for hint in page.findChildren(HelpHint)
    }
    assert actual_help == approved_help
    approved_ids = {
        "CTX-01": "Minimum detection score",
        "CTX-02": "Window overlap",
        "CTX-03": "Combine nearby candidates",
        "CTX-04": "Detection Model",
        "CTX-05": "Recordings folder",
        "CTX-06": "Recording inclusion",
        "CTX-07": "Corpus export formats",
        "CTX-08": None,
        "CTX-09": "RF refinement",
        "CTX-10": "Result selection",
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
