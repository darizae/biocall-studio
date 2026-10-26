"""GUI startup with one application and one Theme installation."""

import logging
import sys
from pathlib import Path

from alp_ui.theme import install_theme
from PySide6.QtCore import QStandardPaths, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from alpaca_desktop.application.diagnostics import DiagnosticSession
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.diagnostics import sanitize_diagnostic_text


def _base_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    app.setOrganizationName("Alpaca")
    app.setApplicationName("alpaca Desktop Trainer")
    return app


def create_application(argv: list[str] | None = None) -> QApplication:
    app = _base_application(argv)
    if not app.property("alpaca_desktop_initialized"):
        install_theme(app)
        app.setProperty("alpaca_desktop_initialized", True)
    return app


class _DiagnosticHooks:
    def __init__(self, diagnostics: DiagnosticSession):
        self.diagnostics = diagnostics
        self._previous_excepthook = sys.excepthook
        self._previous_qt_handler = qInstallMessageHandler(self._qt_message)
        self._closed = False
        sys.excepthook = self._python_exception

    def _python_exception(self, exception_type, exception, traceback) -> None:
        self.diagnostics.emit(
            "alpaca_desktop.application",
            "unhandled_exception",
            "Unhandled application exception",
            level=logging.CRITICAL,
            context={"exception_type": getattr(exception_type, "__name__", "Exception")},
        )
        self._previous_excepthook(exception_type, exception, traceback)

    def _qt_message(self, message_type, context, message) -> None:
        level = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }.get(message_type, logging.WARNING)
        self.diagnostics.emit(
            "alpaca_desktop.qt",
            "qt_message",
            sanitize_diagnostic_text(message),
            level=level,
        )
        if self._previous_qt_handler is not None:
            self._previous_qt_handler(message_type, context, message)
        elif level >= logging.WARNING:
            print(sanitize_diagnostic_text(message), file=sys.stderr)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sys.excepthook = self._previous_excepthook
        qInstallMessageHandler(self._previous_qt_handler)


def run(settings_dir: Path | None = None, *, diagnostic_debug: bool = False) -> int:
    app = _base_application()
    if settings_dir is None:
        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        if not location:
            raise OSError("Qt could not locate Application Settings storage.")
        settings_dir = Path(location)
    diagnostics = DiagnosticSession(settings_dir, debug=diagnostic_debug)
    hooks = _DiagnosticHooks(diagnostics)
    try:
        if not app.property("alpaca_desktop_initialized"):
            install_theme(app)
            app.setProperty("alpaca_desktop_initialized", True)
        window = MainWindow(WorkspaceController(settings_dir, diagnostics=diagnostics))
        window.show()
        return app.exec()
    except Exception as exc:
        diagnostics.emit(
            "alpaca_desktop.application",
            "application_start_failed",
            "Application startup failed",
            level=logging.CRITICAL,
            context={"exception_type": type(exc).__name__},
        )
        raise
    finally:
        hooks.close()
        diagnostics.close()
