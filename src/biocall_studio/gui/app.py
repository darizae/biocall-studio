"""Canonical Studio startup with one themed application and retained Train state."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from biocall_studio.gui.branding import application_icon
from biocall_studio.gui.coordinator import StudioCoordinator
from biocall_studio_train.application.diagnostics import DiagnosticSession
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.gui.app import DiagnosticHooks, default_settings_dir
from biocall_studio_train.gui.app import create_application as create_train_application


def create_application(argv: list[str] | None = None) -> QApplication:
    app = create_train_application(argv)
    app.setOrganizationName("BioCall Studio")
    app.setApplicationName("biocall-studio")
    app.setApplicationDisplayName("BioCall Studio")
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(False)
    return app


def default_detect_data_dir() -> Path:
    """Return the suite-owned per-user data root used by Detect."""
    app = QApplication.instance()
    if app is None:
        app = create_application()
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    if not location:
        raise OSError("Qt could not locate BioCall Studio application-data storage.")
    return Path(location)


def run(settings_dir: Path | None = None, *, diagnostic_debug: bool = False) -> int:
    app = create_application()
    if settings_dir is None:
        train_settings_dir = default_settings_dir()
        detect_data_dir = default_detect_data_dir()
    else:
        train_settings_dir = settings_dir
        detect_data_dir = settings_dir
    diagnostics = DiagnosticSession(train_settings_dir, debug=diagnostic_debug)
    hooks = DiagnosticHooks(diagnostics)
    try:
        controller = WorkspaceController(train_settings_dir, diagnostics=diagnostics)
        coordinator = StudioCoordinator(controller, detect_data_dir=detect_data_dir)
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
