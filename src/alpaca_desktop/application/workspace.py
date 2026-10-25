"""Collection selection, background Scan, and machine-local verified binding."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QStandardPaths, QThread, Signal

from alpaca_desktop.application.collection_scan import (
    CollectionScanCancelled,
    ScanProgress,
    inputs_match_scan,
    scan_collection,
)
from alpaca_desktop.domain.collection import ScanResult
from alpaca_desktop.persistence.collection_metadata import (
    load_collection_metadata,
    publish_collection_metadata,
)
from alpaca_desktop.persistence.settings import ApplicationSettings, SettingsStore


class _CollectionScanThread(QThread):
    progress_changed = Signal(object)
    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, root: Path, step_delay_seconds: float):
        super().__init__()
        self.root = root
        self.step_delay_seconds = step_delay_seconds
        self.cancel_event = Event()

    def run(self) -> None:
        try:
            try:
                cached = load_collection_metadata(self.root)
            except (FileNotFoundError, OSError, ValueError):
                cached = None
            result = scan_collection(
                self.root,
                cached=cached,
                cancel=self.cancel_event,
                progress=self.progress_changed.emit,
                step_delay_seconds=self.step_delay_seconds,
            )
            if result.valid:
                if self.cancel_event.is_set():
                    raise CollectionScanCancelled()
                result = publish_collection_metadata(self.root, result)
        except CollectionScanCancelled:
            self.cancelled.emit()
        except Exception as exc:  # surfaced as actionable UI feedback on the main thread
            self.failed.emit(str(exc))
        else:
            self.result_ready.emit(result)


class WorkspaceController(QObject):
    """Keep unverified folder selection separate from a verified Collection binding."""

    changed = Signal()
    pending_changed = Signal()
    scan_started = Signal(str)
    scan_progress_changed = Signal(object)
    scan_completed = Signal(object)
    scan_failed = Signal(str)
    scan_cancelled = Signal()

    def __init__(
        self,
        settings_dir: Path | None = None,
        *,
        scan_step_delay_seconds: float = 0.0,
    ):
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
        self._settings_error_message = ""
        self._pending_collection_path: Path | None = None
        self.scan_result: ScanResult | None = None
        self.scan_progress = ScanProgress("Idle", 0, 0, 0, 0, 0)
        self.is_scanning = False
        self._scan_thread: _CollectionScanThread | None = None
        self._scan_root: Path | None = None
        self._scan_step_delay_seconds = scan_step_delay_seconds
        try:
            self._settings = self._store.load()
        except (OSError, ValueError) as exc:
            self.error_message = str(exc)
            self._settings_error_message = self.error_message
            self._settings = ApplicationSettings()

    @property
    def collection_path(self) -> Path | None:
        return self._settings.collection_path

    @property
    def collection_id(self) -> str | None:
        return self._settings.collection_id

    @property
    def pending_collection_path(self) -> Path | None:
        return self._pending_collection_path

    def request_collection(self, directory: str) -> None:
        """Keep picker intent pending until its background Scan validates and publishes."""
        self._pending_collection_path = Path(directory) if directory else None
        self.pending_changed.emit()
        if self._pending_collection_path is not None:
            self._start_scan(self._pending_collection_path)

    def bind_verified_collection(
        self, directory: str | Path, collection_id: str | None = None
    ) -> None:
        """Persist a path only after its caller has established Collection identity."""
        if self._settings_error_message:
            raise ValueError(
                f"Repair Application Settings before saving: {self._settings_error_message}"
            )
        path = Path(directory)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("A verified Collection must be an existing absolute folder.")
        metadata = load_collection_metadata(path)
        expected_id = collection_id or metadata.collection_id
        if metadata.collection_id != expected_id:
            raise ValueError("Collection identity does not match the verified binding.")
        self._save(ApplicationSettings(path.resolve(strict=True), expected_id))
        self._pending_collection_path = None
        self.pending_changed.emit()

    def reopen_bound_collection(self) -> None:
        if self.collection_path is not None and not self.is_scanning:
            self._start_scan(self.collection_path)

    def rescan(self) -> None:
        root = self._scan_root or self.pending_collection_path or self.collection_path
        if root is None:
            raise ValueError("No Collection is available to rescan.")
        self._start_scan(root)

    def cancel_scan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_thread.cancel_event.set()

    def current_inputs_ready(self) -> bool:
        if self.scan_result is None or not self.scan_result.valid or self._scan_root is None:
            return False
        return inputs_match_scan(self._scan_root, self.scan_result)

    def _start_scan(self, root: Path) -> None:
        if self.is_scanning:
            return
        self._scan_root = Path(root)
        if not self._settings_error_message:
            self.error_message = ""
        self.scan_result = None
        self.scan_progress = ScanProgress("Listing files", 0, 0, 0, 0, 0)
        self.is_scanning = True
        thread = _CollectionScanThread(self._scan_root, self._scan_step_delay_seconds)
        self._scan_thread = thread
        thread.progress_changed.connect(self._on_progress)
        thread.result_ready.connect(self._on_result)
        thread.failed.connect(self._on_failure)
        thread.cancelled.connect(self._on_cancelled)
        thread.finished.connect(self._release_thread)
        self.scan_started.emit(str(self._scan_root))
        thread.start()

    def _on_progress(self, progress: ScanProgress) -> None:
        self.scan_progress = progress
        self.scan_progress_changed.emit(progress)

    def _on_result(self, result: ScanResult) -> None:
        self.is_scanning = False
        self.scan_result = result
        if not self._settings_error_message:
            self.error_message = ""
        if result.valid and result.collection_id is not None and self._scan_root is not None:
            try:
                self.bind_verified_collection(self._scan_root, result.collection_id)
            except (OSError, ValueError) as exc:
                self.error_message = str(exc)
                self.scan_failed.emit(self.error_message)
                return
        self.scan_completed.emit(result)

    def _on_failure(self, message: str) -> None:
        self.is_scanning = False
        self.scan_result = None
        self.error_message = message
        self.scan_failed.emit(message)

    def _on_cancelled(self) -> None:
        self.is_scanning = False
        self.scan_result = None
        self.scan_cancelled.emit()

    def _release_thread(self) -> None:
        thread = self.sender()
        if thread is self._scan_thread:
            self._scan_thread = None
        if thread is not None:
            thread.deleteLater()

    def _save(self, settings: ApplicationSettings) -> None:
        self._store.save(settings)
        self._settings = settings
        self.changed.emit()
