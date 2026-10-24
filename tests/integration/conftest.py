"""Qt is loaded only when the integration suite is selected."""

import pytest
from PySide6.QtCore import QStandardPaths

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.app import create_application


@pytest.fixture(scope="session")
def qapp_args():
    QStandardPaths.setTestModeEnabled(True)
    return ["alpaca-desktop-tests"]


@pytest.fixture
def workspace(qapp, tmp_path):
    create_application()
    return WorkspaceController(tmp_path / "application-settings")
