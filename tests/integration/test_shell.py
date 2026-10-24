import subprocess
import sys
from importlib.metadata import version
from textwrap import dedent

import pytest
from alp_ui.components import Alert, Badge, Button, Card, DataTable, Divider, EmptyState, Text
from alp_ui.theme import ALPACA_LIGHT
from PySide6.QtCore import QAbstractItemModel, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.models import DirectoryPageModel
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.settings import ROOT_LABELS

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def test_local_theme_navigation_and_caller_owned_model(qapp, qtbot, workspace):
    """Scaffold boundary smoke; not an indexed Trainer acceptance case."""
    app = create_application()
    assert create_application() is app is qapp is QApplication.instance()
    assert version("alp-ui") == "0.1.0a0"
    assert app.palette().color(QPalette.ColorRole.Window) == QColor(ALPACA_LIGHT.colors.background)
    assert app.font().family() == ALPACA_LIGHT.typography.body_family
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.show()
    for component in (Text, Button, Card, Divider, Badge, Alert, EmptyState, DataTable):
        assert window.findChildren(component)
    tree = window.navigation
    assert tree.accessibleName() == "Artifact navigation"
    assert tree.topLevelItem(0).text(0) == "Data"
    assert [tree.topLevelItem(0).child(i).text(0) for i in range(2)] == ["Collections", "Datasets"]
    tree.setFocus()
    qtbot.waitUntil(tree.hasFocus)
    qtbot.keyClick(tree, Qt.Key.Key_Down)
    assert window.pages.currentWidget().accessibleName() == "Datasets"
    for index, name in enumerate(("Models", "Corpora", "Runs", "Settings"), start=1):
        tree.setCurrentItem(tree.topLevelItem(index))
        assert window.pages.currentWidget().accessibleName() == name
    for root_id, label in ROOT_LABELS.items():
        field = window.settings_page.root_fields[root_id]
        assert field.control.accessibleName() == label
        field.setFocus()
        qtbot.waitUntil(field.control.hasFocus)
    table = window.artifact_pages["Collections"].findChild(DataTable)
    assert isinstance(table.model(), QAbstractItemModel)
    assert isinstance(table.model(), DirectoryPageModel)
    assert type(table.model()).__module__ == "alpaca_desktop.gui.models"
    assert table.accessibleName() == "Collections table"
    assert table.model().rowCount() == 0
    for page in window.artifact_pages.values():
        for button in page.findChildren(Button):
            assert not button.isEnabled()
            assert button.accessibleName()
            assert "unavailable" in button.accessibleDescription()
    assert QApplication.instance() is app


def test_console_startup_passes_isolated_settings_to_the_real_gui(tmp_path):
    code = dedent("""
        import sys
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from alpaca_desktop.gui.app import create_application
        from alpaca_desktop.gui.window import MainWindow
        from alpaca_desktop.cli import main

        app = create_application()
        def inspect_and_quit():
            try:
                window = next(w for w in app.topLevelWidgets() if isinstance(w, MainWindow))
                assert window.isVisible()
                assert window.controller.settings_file == Path(sys.argv[1]) / 'workspace.json'
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
    assert not settings_dir.exists()
