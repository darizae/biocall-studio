"""Canonical BioCall Studio bootstrap with one identity, theme, and data root."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alp_ui.theme import install_theme
from PySide6.QtCore import QStandardPaths, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.storage import SuiteDataPaths
from biocall_studio.studio.gui.branding import application_icon
from biocall_studio.train.application.diagnostics import DiagnosticSession
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.persistence.diagnostics import sanitize_diagnostic_text


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    app.setOrganizationName("BioCall Studio")
    app.setApplicationName("biocall-studio")
    app.setApplicationDisplayName("BioCall Studio")
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(False)
    if not app.property("biocall_studio_initialized"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
        install_theme(app)
        app.setProperty("biocall_studio_initialized", True)
    return app


def default_suite_data_root() -> Path:
    app = QApplication.instance()
    if app is None:
        app = create_application()
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    if not location:
        raise OSError("Qt could not locate BioCall Studio application-data storage.")
    return Path(location)


class DiagnosticHooks:
    def __init__(self, diagnostics: DiagnosticSession):
        self.diagnostics = diagnostics
        self._previous_excepthook = sys.excepthook
        self._previous_qt_handler = qInstallMessageHandler(self._qt_message)
        self._closed = False
        sys.excepthook = self._python_exception

    def _python_exception(self, exception_type, exception, traceback) -> None:
        self.diagnostics.emit(
            "biocall_studio.application",
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
            "biocall_studio.qt",
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
    app = create_application()
    paths = SuiteDataPaths.from_root(settings_dir or default_suite_data_root())
    diagnostics = DiagnosticSession(paths.train, debug=diagnostic_debug)
    hooks = DiagnosticHooks(diagnostics)
    controller: WorkspaceController | None = None
    try:
        controller = WorkspaceController(paths.train, diagnostics=diagnostics)
        coordinator = StudioCoordinator(controller, detect_data_dir=paths.root)
        coordinator.start()
        return app.exec()
    except Exception as exc:
        diagnostics.emit(
            "biocall_studio.application",
            "application_start_failed",
            "Application startup failed",
            level=logging.CRITICAL,
            context={"exception_type": type(exc).__name__},
        )
        raise
    finally:
        hooks.close()
        diagnostics.close()
