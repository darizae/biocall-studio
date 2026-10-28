"""Qt-facing Detect workspace and cancellable inventory application state."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from threading import Event
from time import sleep

from PySide6.QtCore import QObject, QThread, Signal

from biocall_studio.detect.discovery import (
    InventoryScanCancelled,
    InventoryScanProgress,
    discover_wavs,
    snapshot_is_quickly_current,
)
from biocall_studio.detect.domain import RootBindingDecision
from biocall_studio.detect.inventory import (
    DecisionRule,
    InclusionDecision,
    InventorySnapshot,
    RecordingStatus,
    clear_decision,
    revise_decision,
)
from biocall_studio.detect.models import (
    VerifiedModelReference,
    inspect_model_directory,
    recheck_model_reference,
)
from biocall_studio.detect.persistence import (
    DetectWorkspaceStore,
    PersistedDetectCollection,
    RootBindingProposal,
    WorkspaceMetadataError,
)


class InventoryState(StrEnum):
    EMPTY = "empty"
    SCANNING = "scanning"
    READY = "ready"
    CANCELLED = "cancelled"
    INVALID = "invalid"
    STALE = "stale"
    MISSING = "missing"


class ModelIntakeState(StrEnum):
    EMPTY = "empty"
    LOADING = "loading"
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    MISSING = "missing"


class _ModelIntakeThread(QThread):
    reference_ready = Signal(object)
    missing = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        root: Path,
        previous: VerifiedModelReference | None,
        step_delay_seconds: float,
    ):
        super().__init__()
        self.root = root
        self.previous = previous
        self.step_delay_seconds = step_delay_seconds

    def run(self) -> None:
        try:
            if self.step_delay_seconds:
                sleep(self.step_delay_seconds)
            reference = (
                inspect_model_directory(self.root)
                if self.previous is None
                else recheck_model_reference(self.previous)
            )
        except FileNotFoundError as exc:
            self.missing.emit(str(exc))
        except Exception as exc:  # compatibility text is rendered without a traceback
            self.failed.emit(str(exc))
        else:
            self.reference_ready.emit(reference)


class _InventoryScanThread(QThread):
    progress_changed = Signal(object)
    snapshot_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        root: Path,
        collection_id: str,
        binding_revision: int,
        previous: InventorySnapshot | None,
        step_delay_seconds: float,
    ):
        super().__init__()
        self.root = root
        self.collection_id = collection_id
        self.binding_revision = binding_revision
        self.previous = previous
        self.step_delay_seconds = step_delay_seconds
        self.cancel_event = Event()

    def run(self) -> None:
        try:
            snapshot = discover_wavs(
                self.root,
                collection_id=self.collection_id,
                binding_revision=self.binding_revision,
                previous=self.previous,
                cancel=self.cancel_event,
                progress=self.progress_changed.emit,
                step_delay_seconds=self.step_delay_seconds,
            )
        except InventoryScanCancelled:
            self.cancelled.emit()
        except Exception as exc:  # actionable text is surfaced by the controller on the UI thread
            self.failed.emit(str(exc))
        else:
            self.snapshot_ready.emit(snapshot)


class DetectWorkspaceController(QObject):
    state_changed = Signal()
    scan_progress_changed = Signal(object)

    def __init__(
        self,
        application_data_root: Path,
        *,
        scan_step_delay_seconds: float = 0.0,
        model_step_delay_seconds: float = 0.0,
    ):
        super().__init__()
        self.store = DetectWorkspaceStore(application_data_root)
        self.active_collection: PersistedDetectCollection | None = None
        self.root_decision: RootBindingDecision | None = None
        self.proposal: RootBindingProposal | None = None
        self.selection_error = ""
        self.metadata_error = ""
        self.inventory_error = ""
        self.snapshot: InventorySnapshot | None = None
        self.inventory_state = InventoryState.EMPTY
        self.model_reference: VerifiedModelReference | None = None
        self.selected_model_root: Path | None = None
        self.model_state = ModelIntakeState.EMPTY
        self.model_reason = "Choose a CNN Model published by Train."
        self.scan_progress = InventoryScanProgress("Idle", 0, 0, 0, 0)
        self._scan_thread: _InventoryScanThread | None = None
        self._model_thread: _ModelIntakeThread | None = None
        self._scan_step_delay_seconds = scan_step_delay_seconds
        self._model_step_delay_seconds = model_step_delay_seconds
        self.refresh(emit=False)

    @property
    def is_scanning(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.isRunning()

    @property
    def is_model_loading(self) -> bool:
        return self._model_thread is not None and self._model_thread.isRunning()

    @property
    def inputs_ready(self) -> bool:
        return (
            self.model_state is ModelIntakeState.COMPATIBLE
            and self.model_reference is not None
            and self.root_decision is RootBindingDecision.VALID
            and self.inventory_state is InventoryState.READY
            and self.snapshot is not None
            and self.snapshot.counts.included > 0
            and not self.is_scanning
            and not self.is_model_loading
        )

    def _state_for_snapshot(self, snapshot: InventorySnapshot) -> InventoryState:
        invalid_included = any(
            row.status is RecordingStatus.INVALID
            and row.decision is InclusionDecision.INCLUDED
            for row in snapshot.recordings
        )
        if invalid_included:
            return InventoryState.INVALID
        if not snapshot.recordings:
            return InventoryState.EMPTY
        return InventoryState.READY

    def _load_inventory(self) -> None:
        self.snapshot = None
        self.inventory_error = ""
        collection = self.active_collection
        if collection is None or collection.ref.inventory_revision is None:
            self.inventory_state = (
                InventoryState.MISSING
                if self.root_decision is RootBindingDecision.MISSING
                else InventoryState.EMPTY
            )
            return
        try:
            self.snapshot = self.store.load_inventory(collection.ref.collection_id)
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.inventory_error = str(exc)
            self.inventory_state = InventoryState.INVALID
            return
        if self.root_decision is RootBindingDecision.MISSING:
            self.inventory_state = InventoryState.MISSING
        elif (
            self.root_decision is not RootBindingDecision.VALID
            or collection.ref.inventory_is_stale
            or not snapshot_is_quickly_current(collection.source_root, self.snapshot)
        ):
            self.inventory_state = InventoryState.STALE
        else:
            self.inventory_state = self._state_for_snapshot(self.snapshot)

    def refresh(self, *, emit: bool = True) -> None:
        self.selection_error = ""
        self.metadata_error = ""
        self.proposal = None
        try:
            self.active_collection = self.store.load_active_collection()
            self.root_decision = (
                None
                if self.active_collection is None
                else self.store.root_decision(self.active_collection)
            )
        except WorkspaceMetadataError as exc:
            self.active_collection = None
            self.root_decision = None
            self.metadata_error = str(exc)
        self._load_inventory()
        self._load_model_selection()
        if emit:
            self.state_changed.emit()

    def _load_model_selection(self) -> None:
        if self.is_model_loading:
            return
        try:
            reference = self.store.load_model_reference()
        except WorkspaceMetadataError as exc:
            self.model_reference = None
            self.selected_model_root = None
            self.model_state = ModelIntakeState.INCOMPATIBLE
            self.model_reason = str(exc)
            return
        if reference is None:
            self.model_reference = None
            self.selected_model_root = None
            self.model_state = ModelIntakeState.EMPTY
            self.model_reason = "Choose a CNN Model published by Train."
            return
        self.model_reference = reference
        self.selected_model_root = reference.root
        self._start_model_inspection(reference.root, previous=reference)

    def _start_model_inspection(
        self,
        root: Path,
        *,
        previous: VerifiedModelReference | None = None,
    ) -> None:
        self.model_state = ModelIntakeState.LOADING
        self.model_reason = "Checking Model information, checksums, and runtime structure."
        thread = _ModelIntakeThread(root, previous, self._model_step_delay_seconds)
        self._model_thread = thread
        thread.reference_ready.connect(self._model_ready)
        thread.missing.connect(self._model_missing)
        thread.failed.connect(self._model_failed)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._model_finished(thread))
        thread.start()

    def choose_model_root(self, value: str) -> None:
        if not value or self.is_model_loading:
            return
        candidate = Path(value).expanduser()
        if (
            self.selected_model_root is not None
            and candidate.resolve(strict=False) == self.selected_model_root.resolve(strict=False)
        ):
            return
        try:
            self.store.clear_model_reference()
        except (OSError, WorkspaceMetadataError) as exc:
            self.model_state = ModelIntakeState.INCOMPATIBLE
            self.model_reason = f"The Model selection could not be updated: {exc}"
            self.state_changed.emit()
            return
        self.model_reference = None
        self.selected_model_root = candidate.resolve(strict=False)
        self._start_model_inspection(candidate)
        self.state_changed.emit()

    def clear_model_selection(self) -> None:
        if self.is_model_loading:
            return
        try:
            self.store.clear_model_reference()
        except (OSError, WorkspaceMetadataError) as exc:
            self.model_state = ModelIntakeState.INCOMPATIBLE
            self.model_reason = f"The Model selection could not be cleared: {exc}"
        else:
            self.model_reference = None
            self.selected_model_root = None
            self.model_state = ModelIntakeState.EMPTY
            self.model_reason = "Choose a CNN Model published by Train."
        self.state_changed.emit()

    def _model_ready(self, reference: VerifiedModelReference) -> None:
        try:
            self.store.save_model_reference(reference)
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.model_reference = None
            self.model_state = ModelIntakeState.INCOMPATIBLE
            self.model_reason = f"Verified Model information could not be saved: {exc}"
        else:
            self.model_reference = reference
            self.selected_model_root = reference.root
            if reference.snapshot.primary_detection_compatible:
                self.model_state = ModelIntakeState.COMPATIBLE
                self.model_reason = (
                    "Model files and runtime structure are verified. Numerical prediction "
                    "behavior is checked again before a detection Run."
                )
            else:
                self.model_state = ModelIntakeState.INCOMPATIBLE
                self.model_reason = (
                    "This Random Forest Model can refine candidate intervals but cannot start "
                    "candidate detection. Choose a CNN Model."
                )
        self.state_changed.emit()

    def _model_missing(self, message: str) -> None:
        self.model_state = ModelIntakeState.MISSING
        self.model_reason = (
            "The selected Model folder or a declared file is missing. Choose the Model again."
        )
        if message and "artifact" in message.casefold():
            self.model_reason = "A declared Model file is missing. Choose a complete Train Model."
        self.state_changed.emit()

    def _model_failed(self, message: str) -> None:
        self.model_state = ModelIntakeState.INCOMPATIBLE
        self.model_reason = message or "The selected Model is not compatible."
        self.state_changed.emit()

    def _model_finished(self, thread: _ModelIntakeThread) -> None:
        if self._model_thread is thread:
            self._model_thread = None
            self.state_changed.emit()

    def choose_source_root(self, value: str) -> None:
        if not value:
            return
        candidate = Path(value)
        self.selection_error = ""
        start_scan = False
        try:
            if self.active_collection is None:
                label = candidate.name.strip() or "Detect Collection"
                self.active_collection = self.store.create_collection(label, candidate)
                self.root_decision = RootBindingDecision.VALID
                self.proposal = None
                self.snapshot = None
                self.inventory_state = InventoryState.EMPTY
                start_scan = True
            else:
                proposal = self.store.prepare_relink(
                    self.active_collection.ref.collection_id, candidate
                )
                if proposal.decision is RootBindingDecision.VALID:
                    self.proposal = None
                    self.root_decision = RootBindingDecision.VALID
                    start_scan = self.snapshot is None
                elif proposal.decision in {
                    RootBindingDecision.AWAITING_CONFIRMATION,
                    RootBindingDecision.CHANGED,
                }:
                    self.proposal = proposal
                elif proposal.decision is RootBindingDecision.MISSING:
                    self.proposal = None
                    self.selection_error = "The selected recordings folder is missing."
                else:
                    self.proposal = None
                    self.selection_error = "The selected recordings folder cannot be read."
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.proposal = None
            self.selection_error = str(exc)
        self.state_changed.emit()
        if start_scan:
            self.start_scan()

    def cancel_relink(self) -> None:
        self.proposal = None
        self.selection_error = ""
        self.state_changed.emit()

    def confirm_relink(self) -> None:
        if self.proposal is None:
            return
        try:
            self.active_collection = self.store.confirm_relink(self.proposal)
            self.root_decision = RootBindingDecision.VALID
            self.proposal = None
            self.selection_error = ""
            self.inventory_state = InventoryState.STALE
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.selection_error = str(exc)
            self.state_changed.emit()
            return
        self.state_changed.emit()
        self.start_scan()

    def create_new_collection(self) -> None:
        if self.proposal is None or self.proposal.decision is not RootBindingDecision.CHANGED:
            return
        candidate = self.proposal.candidate_root
        try:
            self.active_collection = self.store.create_collection(
                candidate.name.strip() or "Detect Collection", candidate
            )
            self.root_decision = RootBindingDecision.VALID
            self.proposal = None
            self.selection_error = ""
            self.snapshot = None
            self.inventory_state = InventoryState.EMPTY
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.selection_error = str(exc)
            self.state_changed.emit()
            return
        self.state_changed.emit()
        self.start_scan()

    def start_scan(self) -> None:
        if self.is_scanning:
            return
        collection = self.active_collection
        if collection is None:
            self.inventory_error = "Choose a recordings folder before scanning."
            self.inventory_state = InventoryState.INVALID
            self.state_changed.emit()
            return
        self.root_decision = self.store.root_decision(collection)
        if self.root_decision is not RootBindingDecision.VALID:
            self.inventory_error = "The recordings folder must be available before scanning."
            self.inventory_state = (
                InventoryState.MISSING
                if self.root_decision is RootBindingDecision.MISSING
                else InventoryState.INVALID
            )
            self.state_changed.emit()
            return
        self.inventory_error = ""
        self.scan_progress = InventoryScanProgress("Listing WAV files", 0, 0, 0, 0)
        self.inventory_state = InventoryState.SCANNING
        thread = _InventoryScanThread(
            collection.source_root,
            collection.ref.collection_id,
            collection.ref.binding_revision,
            self.snapshot,
            self._scan_step_delay_seconds,
        )
        self._scan_thread = thread
        thread.progress_changed.connect(self._scan_progress)
        thread.snapshot_ready.connect(self._scan_complete)
        thread.failed.connect(self._scan_failed)
        thread.cancelled.connect(self._scan_cancelled)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._scan_finished)
        thread.start()
        self.state_changed.emit()

    def rescan(self) -> None:
        self.start_scan()

    def cancel_scan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._scan_thread.cancel_event.set()

    def _scan_progress(self, progress: InventoryScanProgress) -> None:
        self.scan_progress = progress
        self.scan_progress_changed.emit(progress)
        self.state_changed.emit()

    def _scan_complete(self, snapshot: InventorySnapshot) -> None:
        collection = self.active_collection
        if collection is None:
            self._scan_failed("The Detect Collection was closed during the scan.")
            return
        try:
            self.active_collection = self.store.publish_inventory(
                collection.ref.collection_id, snapshot
            )
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self._scan_failed(str(exc))
            return
        self.snapshot = snapshot
        self.inventory_error = ""
        self.inventory_state = self._state_for_snapshot(snapshot)
        self.state_changed.emit()

    def _scan_failed(self, message: str) -> None:
        self.inventory_error = message or "The recording scan failed."
        self.inventory_state = (
            InventoryState.STALE if self.snapshot is not None else InventoryState.INVALID
        )
        self.state_changed.emit()

    def _scan_cancelled(self) -> None:
        self.inventory_error = (
            "Scan cancelled. No inventory was published."
            if self.snapshot is None
            else "Scan cancelled. The last complete inventory was kept."
        )
        self.inventory_state = InventoryState.CANCELLED
        self.state_changed.emit()

    def _scan_finished(self) -> None:
        self._scan_thread = None
        self.state_changed.emit()

    def set_inventory_decision(
        self,
        path: str,
        *,
        is_folder: bool,
        decision: InclusionDecision,
    ) -> None:
        if self.snapshot is None or self.active_collection is None:
            return
        if self.is_scanning:
            self.inventory_error = "Wait for the current scan before changing inclusion."
            self.state_changed.emit()
            return
        if not snapshot_is_quickly_current(
            self.active_collection.source_root, self.snapshot
        ):
            self.inventory_state = InventoryState.STALE
            self.inventory_error = "Recordings changed. Rescan before changing inclusion."
            self.state_changed.emit()
            return
        try:
            rule = (
                DecisionRule.folder(path, decision)
                if is_folder
                else DecisionRule.file(path, decision)
            )
            revised = revise_decision(self.snapshot, rule)
            self.active_collection = self.store.publish_inventory(
                self.active_collection.ref.collection_id, revised
            )
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.inventory_error = str(exc)
        else:
            self.snapshot = revised
            self.inventory_error = ""
            self.inventory_state = self._state_for_snapshot(revised)
        self.state_changed.emit()

    def clear_inventory_decision(self, path: str, *, is_folder: bool) -> None:
        if self.snapshot is None or self.active_collection is None or self.is_scanning:
            return
        try:
            revised = clear_decision(self.snapshot, path, is_folder=is_folder)
            self.active_collection = self.store.publish_inventory(
                self.active_collection.ref.collection_id, revised
            )
        except (OSError, ValueError, WorkspaceMetadataError) as exc:
            self.inventory_error = str(exc)
        else:
            self.snapshot = revised
            self.inventory_error = ""
            self.inventory_state = self._state_for_snapshot(revised)
        self.state_changed.emit()

    def wait_for_scan(self, milliseconds: int = 3_000) -> bool:
        thread = self._scan_thread
        if thread is None:
            return True
        return thread.wait(milliseconds)

    def wait_for_model(self, milliseconds: int = 3_000) -> bool:
        thread = self._model_thread
        if thread is None:
            return True
        return thread.wait(milliseconds)
