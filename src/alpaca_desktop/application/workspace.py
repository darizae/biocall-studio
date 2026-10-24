"""Collection selection intent and the machine-local verified binding."""

from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal

from alpaca_desktop.persistence.settings import ApplicationSettings, SettingsStore


class WorkspaceController(QObject):
    """Keep unverified folder selection separate from a verified Collection binding."""

    changed = Signal()
    pending_changed = Signal()

    def __init__(self, settings_dir: Path | None = None):
        super().__init__()
        if settings_dir is None:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
            if not location:
                raise OSError("Qt could not locate Application Settings storage.")
            settings_dir = Path(location)
        self.settings_file = settings_dir.resolve() / "settings.json"
        self._store = SettingsStore(self.settings_file)
        self.error_message = ""
        self._pending_collection_path: Path | None = None
        try:
            self._settings = self._store.load()
        except (OSError, ValueError) as exc:
            self.error_message = str(exc)
            self._settings = ApplicationSettings()

    @property
    def collection_path(self) -> Path | None:
        return self._settings.collection_path

    @property
    def pending_collection_path(self) -> Path | None:
        return self._pending_collection_path

    def request_collection(self, directory: str) -> None:
        """Record picker intent only; Collection scanning/validation begins in spec 02."""
        self._pending_collection_path = Path(directory) if directory else None
        self.pending_changed.emit()

    def bind_verified_collection(self, directory: str | Path) -> None:
        """Persist a path only after its caller has established Collection identity."""
        if self.error_message:
            raise ValueError(f"Repair Application Settings before saving: {self.error_message}")
        path = Path(directory)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("A verified Collection must be an existing absolute folder.")
        self._save(ApplicationSettings(path.resolve(strict=True)))
        self._pending_collection_path = None
        self.pending_changed.emit()

    def _save(self, settings: ApplicationSettings) -> None:
        self._store.save(settings)
        self._settings = settings
        self.changed.emit()
