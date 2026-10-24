"""GUI startup with one application and one Theme installation."""

from pathlib import Path

from alp_ui.theme import install_theme
from PySide6.QtWidgets import QApplication

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    if not app.property("alpaca_desktop_initialized"):
        app.setOrganizationName("Alpaca")
        app.setApplicationName("alpaca Desktop Trainer")
        install_theme(app)
        app.setProperty("alpaca_desktop_initialized", True)
    return app


def run(settings_dir: Path | None = None) -> int:
    app = create_application()
    window = MainWindow(WorkspaceController(settings_dir))
    window.show()
    return app.exec()
