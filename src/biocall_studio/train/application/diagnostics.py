"""Application-owned diagnostic session lifecycle and stable event emission."""

from __future__ import annotations

import logging
import platform
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from biocall_studio.train.persistence.diagnostics import (
    APP_LOG_BACKUP_COUNT,
    APP_LOG_MAX_BYTES,
    BoundedJsonlSink,
    DiagnosticJsonlHandler,
    export_diagnostics_bundle,
    prune_app_logs,
)


def _package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


class DiagnosticSession:
    """One local GUI-process session with isolated loggers and an idempotent close."""

    def __init__(self, settings_dir: Path, *, debug: bool = False):
        self.session_id = uuid.uuid4().hex
        requested_settings_dir = Path(settings_dir)
        settings_symlink = requested_settings_dir.is_symlink()
        self.settings_dir = requested_settings_dir.resolve()
        self.log_dir = self.settings_dir / "logs"
        self.path = self.log_dir / (f"session-{datetime.now(UTC):%Y-%m-%d}-{self.session_id}.jsonl")
        self._closed = False
        self._handler: DiagnosticJsonlHandler | None = None
        self._loggers: dict[str, logging.Logger] = {}
        self.unavailable_reason = ""
        try:
            if settings_symlink:
                raise OSError("Application Settings directory cannot be a symlink.")
            self.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.log_dir.is_symlink() or not self.log_dir.is_dir():
                raise OSError("Application diagnostic directory is unsafe.")
            self._handler = DiagnosticJsonlHandler(
                BoundedJsonlSink(
                    self.path,
                    max_bytes=APP_LOG_MAX_BYTES,
                    backup_count=APP_LOG_BACKUP_COUNT,
                ),
                session_id=self.session_id,
                level=logging.DEBUG if debug else logging.INFO,
            )
            prune_app_logs(self.log_dir, active_path=self.path)
        except (OSError, ValueError) as exc:
            self.unavailable_reason = type(exc).__name__
        self.emit(
            "biocall_studio.train.application",
            "session_started",
            "Application diagnostic session started",
            context={
                "version": _package_version("biocall-studio"),
                "python_version": platform.python_version(),
                "qt_version": _package_version("PySide6-Essentials"),
                "toolbox_version": _package_version("bioacoustics-dl-toolbox"),
                "alp_ui_version": _package_version("alp-ui"),
            },
        )

    @property
    def available(self) -> bool:
        return self._handler is not None and not self._handler.sink.failed and not self._closed

    def _logger(self, component: str) -> logging.Logger | None:
        handler = self._handler
        if handler is None or self._closed:
            return None
        logger = self._loggers.get(component)
        if logger is None:
            logger = logging.Logger(component, logging.DEBUG)
            logger.propagate = False
            logger.addHandler(handler)
            self._loggers[component] = logger
        return logger

    def emit(
        self,
        component: str,
        event: str,
        message: str,
        *,
        level: int = logging.INFO,
        context: Mapping[str, object] | None = None,
    ) -> bool:
        logger = self._logger(component)
        if logger is None:
            return False
        logger.log(
            level,
            message,
            extra={"diagnostic_event": event, "diagnostic_context": dict(context or {})},
        )
        if self._handler is not None and self._handler.sink.failed:
            self.unavailable_reason = self._handler.sink.failure_message or "OSError"
            return False
        return True

    def export(
        self,
        destination: Path,
        *,
        selected_run: tuple[Path, str] | None = None,
        overwrite: bool = False,
    ):
        return export_diagnostics_bundle(
            destination,
            app_log_dir=self.log_dir,
            selected_run=selected_run,
            inventory={
                "session_id": self.session_id,
                "run_id": selected_run[1] if selected_run is not None else None,
                "version": _package_version("biocall-studio"),
                "python_version": platform.python_version(),
                "qt_version": _package_version("PySide6-Essentials"),
                "toolbox_version": _package_version("bioacoustics-dl-toolbox"),
                "alp_ui_version": _package_version("alp-ui"),
            },
            overwrite=overwrite,
        )

    def close(self) -> None:
        if self._closed:
            return
        self.emit(
            "biocall_studio.train.application",
            "session_finished",
            "Application diagnostic session finished",
        )
        self._closed = True
        handler = self._handler
        for logger in self._loggers.values():
            if handler is not None:
                logger.removeHandler(handler)
        self._loggers.clear()
        if handler is not None:
            handler.close()


def diagnostic_context_for_run(run) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "request_id": run.request_id,
        "run_kind": run.kind.value,
        "training_family": run.training_family,
        "status": run.status.value,
        "stage": run.current_stage,
    }
