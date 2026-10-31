import subprocess
import sys
from textwrap import dedent

import pytest
from alp_ui.components import DataTable, FolderPicker, HelpHint
from PySide6.QtCore import QAbstractItemModel, Qt
from PySide6.QtWidgets import QApplication, QLabel

from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.gui.window import MainWindow
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def test_native_shell_routes_between_select_and_wiki(qapp, qtbot, workspace):
    """Case: IT-UI-001."""
    app = create_application()
    assert create_application() is app is qapp is QApplication.instance()
    assert app.styleHints().colorScheme() is Qt.ColorScheme.Light
    assert app.organizationName() == "BioCall Studio"
    assert app.applicationName() == "biocall-studio"
    assert app.applicationDisplayName() == "BioCall Studio"
    assert not app.windowIcon().isNull()
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    assert window.windowTitle() == "BioCall Studio Train"
    assert not window.windowIcon().isNull()
    assert window.brand_icon.accessibleName() == "BioCall Studio Train logo"
    assert window.brand_title.text() == "BioCall Studio"
    assert window.brand_subtitle.text() == "TRAIN"
    assert window.current_route == "select"
    assert all(not button.icon().isNull() for button in window._navigation.values())
    assert window._navigation["select"].isChecked()
    assert window._navigation["select"].accessibleDescription() == "Current page"
    window.navigate("wiki")
    assert window.current_route == "wiki"
    assert window._navigation["wiki"].isChecked()
    assert not window._navigation["select"].isChecked()
    assert window.wiki_select_button.focusPolicy() != Qt.FocusPolicy.NoFocus
    window.wiki_select_button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert window.focusWidget() is window.wiki_select_button
    window.wiki_select_button.click()
    assert window.current_route == "select"
    picker_button = window.select_page.folder_picker.choose_button
    assert picker_button.focusPolicy() != Qt.FocusPolicy.NoFocus
    qapp.processEvents()
    assert window.focusWidget() is picker_button


def test_folder_picker_keeps_pending_selection_when_native_dialog_is_cancelled(
    qtbot, workspace, tmp_path, monkeypatch
):
    """Case: IT-UI-003."""
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    picker = window.select_page.folder_picker
    assert isinstance(picker, FolderPicker)
    selected = tmp_path / "chosen-collection"
    selected.mkdir()
    picker.setFolderPath(str(selected))
    assert workspace.pending_collection_path == selected
    assert picker.control.accessibleDescription() == str(selected)

    monkeypatch.setattr(
        "alp_ui.components.inputs.QFileDialog.getExistingDirectory", lambda *args: ""
    )
    picker.choose_button.click()
    assert picker.folderPath() == str(selected)
    assert workspace.pending_collection_path == selected
    assert workspace.collection_path is None
    assert not workspace.settings_file.exists()


def test_verified_collection_binding_reopens_and_explicitly_rebinds_without_touching_wavs(
    workspace, qtbot, tmp_path, collection_factory
):
    """Case: IT-UI-002."""
    first = collection_factory(tmp_path / "first-collection", source_count=1)
    second = collection_factory(tmp_path / "second-collection", source_count=1)
    first_metadata = publish_collection_metadata(first, scan_collection(first))
    second_metadata = publish_collection_metadata(second, scan_collection(second))
    wav = first / "recordings" / "REC_A.wav"
    before = wav.read_bytes()

    workspace.bind_verified_collection(first, first_metadata.collection_id)
    reopened = WorkspaceController(workspace.settings_file.parent)
    assert reopened.collection_path == first
    reopened.bind_verified_collection(second, second_metadata.collection_id)
    assert WorkspaceController(workspace.settings_file.parent).collection_path == second
    assert wav.read_bytes() == before

    window = MainWindow(reopened)
    qtbot.addWidget(window)
    window.show()
    window.navigate("settings")
    assert str(second) in window.settings_page.binding_value.text()


def test_empty_routes_help_and_qt_screenshot_are_real_native_widgets(qtbot, workspace, tmp_path):
    """Case: IT-UI-004."""
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    picker = window.select_page.folder_picker
    assert picker.choose_button.text() == "Select folder"
    assert picker.choose_button.variant == "primary"
    assert window.select_page.wiki_button.accessibleName() == "How should my folder look?"
    assert window.select_page.structure_title.text() == "One folder, two subfolders"
    assert window.select_page.card.width() >= 700
    window.select_page.wiki_button.setFocus()
    qtbot.keyClick(window.select_page.wiki_button, Qt.Key.Key_Space)
    assert window.current_route == "wiki"
    window.wiki_select_button.click()
    assert window.current_route == "select"
    select_image = tmp_path / "select.png"
    assert window.grab().save(str(select_image))
    for route in ("collections", "datasets", "models", "runs"):
        window.navigate(route)
        assert window.empty_pages[route].isVisible()
        assert "No " in window.empty_pages[route].title_widget.text()
        table = window._pages[route].findChild(DataTable)
        assert isinstance(table.model(), QAbstractItemModel)
        assert table.model().rowCount() == 0
        window.empty_pages[route].action_widget.click()
        assert window.current_route == ("datasets" if route == "models" else "select")
    window.navigate("wiki")
    hint = window.wiki_page.findChild(HelpHint)
    assert hint is not None
    hint.setFocus()
    qtbot.keyClick(hint, Qt.Key.Key_Space)
    assert "Use whole milliseconds" in hint.accessibleDescription()
    screenshot = window.grab()
    image_path = tmp_path / "wiki.png"
    assert screenshot.save(str(image_path))
    assert select_image.stat().st_size > 0
    assert image_path.stat().st_size > 0
    assert all("demo" not in label.text().lower() for label in window.findChildren(QLabel))

    window.navigate("runs")
    window.resize(700, 780)
    qtbot.waitUntil(lambda: window.is_compact)
    window.navigate("select")
    qtbot.waitUntil(lambda: window.select_page.horizontalScrollBar().maximum() == 0)
    assert window.select_page.horizontalScrollBar().maximum() == 0
    assert window.select_page.card.width() >= window.select_page.viewport().width() - 80
    assert window.select_page.card.geometry().right() < window.select_page.viewport().width()
    assert window.select_page.folder_picker.choose_button.isVisible()


def test_corrupt_application_settings_are_actionable_in_settings(qtbot, tmp_path):
    """Case: IT-UI-002."""
    settings_dir = tmp_path / "application-settings"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text('{"schema_version":')
    window = MainWindow(WorkspaceController(settings_dir))
    qtbot.addWidget(window)
    window.show()
    window.navigate("settings")
    assert window.settings_page.error_alert.isVisible()
    assert "Application Settings" in window.settings_page.error_alert.accessibleName()


def test_console_startup_passes_isolated_suite_data_to_the_real_gui(tmp_path):
    """Case: IT-UI-001."""
    code = dedent("""
        import sys
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from biocall_studio.studio.application.app import create_application
        from biocall_studio.studio.gui.shell import StudioWindow
        from biocall_studio.train.gui.window import MainWindow
        from biocall_studio.cli import main

        app = create_application()
        def inspect_and_quit():
            try:
                window = next(w for w in app.topLevelWidgets() if isinstance(w, MainWindow))
                studio = next(w for w in app.topLevelWidgets() if isinstance(w, StudioWindow))
                assert studio.isVisible()
                assert not window.isVisible()
                expected_settings = Path(sys.argv[1]) / 'train/v1/settings.json'
                assert window.controller.settings_file == expected_settings
                assert QApplication.instance() is app
                print('GUI startup uses isolated Application Settings')
            finally:
                app.quit()
        QTimer.singleShot(0, inspect_and_quit)
        raise SystemExit(main(['--settings-dir', sys.argv[1]]))
    """)
    settings_dir = tmp_path / "child-application-settings"
    result = subprocess.run(
        [sys.executable, "-c", code, str(settings_dir)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "GUI startup uses isolated Application Settings" in result.stdout
    assert not (settings_dir / "settings.json").exists()
    isolated_logs = list((settings_dir / "train/v1/logs").glob("session-*.jsonl"))
    assert len(isolated_logs) == 1
    assert str(settings_dir) not in isolated_logs[0].read_text()
