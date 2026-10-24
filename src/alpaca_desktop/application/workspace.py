"""Workspace bindings stay machine-local and are validated before persistence."""

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal

from alpaca_desktop.persistence.settings import ROOT_LABELS, SettingsStore, WorkspaceSettings


class WorkspaceController(QObject):
    """Coordinate validated settings and notify all dependent views after a save."""

    changed = Signal()

    def __init__(self, settings_dir: Path | None = None):
        super().__init__()
        if settings_dir is None:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
            if not location:
                raise OSError("Qt could not locate Application Settings storage.")
            settings_dir = Path(location)
        self.settings_file = settings_dir.resolve() / "workspace.json"
        self._store = SettingsStore(self.settings_file)
        self.error_message = ""
        try:
            self._settings = self._store.load()
        except (OSError, ValueError) as exc:
            self.error_message = str(exc)
            self._settings = WorkspaceSettings()

    @property
    def roots(self) -> dict[str, Path]:
        return dict(self._settings.roots)

    @property
    def source_bindings(self) -> dict[str, Path]:
        return dict(self._settings.source_bindings)

    def set_roots(self, roots: dict[str, str | Path]) -> None:
        if roots.keys() - ROOT_LABELS.keys():
            raise ValueError("Unknown Workspace root.")
        validated = {key: self._directory(path, writable=True) for key, path in roots.items()}
        self._save(WorkspaceSettings(self.roots | validated, self.source_bindings))

    def add_source_binding(self, root_id: str, directory: str | Path) -> None:
        if not root_id.strip():
            raise ValueError("Enter a source root ID.")
        path = self._directory(directory, writable=False)
        bindings = self.source_bindings
        if root_id in bindings and bindings[root_id] != path:
            raise ValueError(
                f"Source root ID {root_id!r} already points to {bindings[root_id]}. "
                "Verified relinking is unavailable in this version."
            )
        self._save(WorkspaceSettings(self.roots, bindings | {root_id: path}))

    def root_path(self, root_id: str) -> Path:
        if self.error_message:
            raise ValueError(self.error_message)
        if root_id not in self._settings.roots:
            raise ValueError(f"Choose {ROOT_LABELS[root_id]} in Settings.")
        path = self._directory(self._settings.roots[root_id], writable=False)
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Workspace root is not writable: {path}")
        return path

    def _save(self, settings: WorkspaceSettings) -> None:
        if self.error_message:
            raise ValueError(f"Repair Application Settings before saving: {self.error_message}")
        self._store.save(settings)
        self._settings = settings
        self.changed.emit()

    @staticmethod
    def _directory(directory: str | Path, *, writable: bool) -> Path:
        path = Path(directory)
        if not path.is_absolute():
            raise ValueError("Choose an existing folder using an absolute path.")
        if not path.is_dir():
            raise ValueError(f"Folder does not exist or is unavailable: {path}")
        path = path.resolve(strict=True)
        with os.scandir(path) as entries:
            next(entries, None)
        if writable:
            with tempfile.NamedTemporaryFile(dir=path, prefix=".alpaca-write-probe-"):
                pass
        return path
