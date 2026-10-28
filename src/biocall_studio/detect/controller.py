"""Qt-facing Detect workspace and cancellable inventory application state."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from threading import Event
from time import sleep

from PySide6.QtCore import QObject, QProcess, QThread, QTimer, Signal

from biocall_studio.detect.diagnostics import (
    BoundedJsonlLog,
    BoundedStderrCapture,
    encode_diagnostic_record,
    resolve_run_log_path,
)
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
from biocall_studio.detect.owner_lifetime import DetectOwnerLease
from biocall_studio.detect.persistence import (
    DetectWorkspaceStore,
    PersistedDetectCollection,
    RootBindingProposal,
    WorkspaceMetadataError,
)
from biocall_studio.detect.run_persistence import DetectRunRepository
from biocall_studio.detect.runs import (
    DetectRunRecord,
    DetectRunRequest,
    DetectRunStatus,
    RunConflictError,
    canonical_digest,
    complete_run,
    transition_run,
    update_run_progress,
    utc_now,
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
    run_changed = Signal(object)

    def __init__(
        self,
        application_data_root: Path,
        *,
        scan_step_delay_seconds: float = 0.0,
        model_step_delay_seconds: float = 0.0,
        worker_step_delay_seconds: float = 0.0,
        cancel_grace_ms: int = 1_500,
        kill_grace_ms: int = 3_000,
    ):
        super().__init__()
        self.store = DetectWorkspaceStore(application_data_root)
        self._owner_lease = DetectOwnerLease.create(self.store.application_data_root)
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
        self._worker_step_delay_seconds = worker_step_delay_seconds
        self._cancel_grace_ms = cancel_grace_ms
        self._kill_grace_ms = kill_grace_ms
        self.runs: tuple[DetectRunRecord, ...] = ()
        self.current_run: DetectRunRecord | None = None
        self._run_repository: DetectRunRepository | None = None
        self._run_process: QProcess | None = None
        self._run_stdout_buffer = b""
        self._run_stderr = BoundedStderrCapture()
        self._run_error_code = ""
        self._protocol_error = ""
        self._shutdown_requested = False
        self._shutdown_finished = False
        self.refresh(emit=False)

    @property
    def is_scanning(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.isRunning()

    @property
    def is_model_loading(self) -> bool:
        return self._model_thread is not None and self._model_thread.isRunning()

    @property
    def reservation_owner_id(self) -> str:
        return self._owner_lease.owner_id

    @property
    def is_run_active(self) -> bool:
        return self.current_run is not None and self.current_run.active

    @property
    def run_process(self) -> QProcess | None:
        return self._run_process

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
            and not self.is_run_active
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
        self._load_runs()
        if emit:
            self.state_changed.emit()

    def _load_runs(self) -> None:
        collection = self.active_collection
        if collection is None:
            self._run_repository = None
            self.runs = ()
            self.current_run = None
            return
        try:
            repository = DetectRunRepository(
                self.store.application_data_root, collection.ref.collection_id
            )
            runs = repository.reconcile()
        except (OSError, ValueError) as exc:
            self._run_repository = None
            self.runs = ()
            self.current_run = None
            self.metadata_error = f"Detect Run history could not be opened: {exc}"
            return
        self._run_repository = repository
        self.runs = runs
        self.current_run = next((run for run in runs if run.active), runs[0] if runs else None)

    def _active_run_blocks_input_change(self) -> bool:
        if not self.is_run_active:
            return False
        self.inventory_error = "An Active Detect Run reserves these inputs."
        self.state_changed.emit()
        return True

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
        if not value or self.is_model_loading or self._active_run_blocks_input_change():
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
        if self.is_model_loading or self._active_run_blocks_input_change():
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
            self._maybe_finish_shutdown()

    def choose_source_root(self, value: str) -> None:
        if not value or self._active_run_blocks_input_change():
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
        if self.proposal is None or self._active_run_blocks_input_change():
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
        if (
            self.proposal is None
            or self.proposal.decision is not RootBindingDecision.CHANGED
            or self._active_run_blocks_input_change()
        ):
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
        if self.is_scanning or self._active_run_blocks_input_change():
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
        self._maybe_finish_shutdown()

    def set_inventory_decision(
        self,
        path: str,
        *,
        is_folder: bool,
        decision: InclusionDecision,
    ) -> None:
        if (
            self.snapshot is None
            or self.active_collection is None
            or self._active_run_blocks_input_change()
        ):
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
        if (
            self.snapshot is None
            or self.active_collection is None
            or self.is_scanning
            or self._active_run_blocks_input_change()
        ):
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

    def start_lifecycle_fixture(
        self,
        request: DetectRunRequest,
        *,
        behavior: str,
    ) -> str:
        """Launch the ST-06 non-scientific fixture through the production QProcess seam."""
        if behavior not in {
            "success",
            "slow",
            "stubborn",
            "fail",
            "crash",
            "stderr_storm",
            "commit_then_crash",
        }:
            raise ValueError("Unsupported lifecycle fixture behavior.")
        collection = self.active_collection
        snapshot = self.snapshot
        if collection is None or snapshot is None:
            raise ValueError("A current Detect Collection inventory is required.")
        if self.is_scanning or self.is_model_loading:
            raise RunConflictError("Wait for current input preparation before starting a Run.")
        if self.is_run_active or (
            self._run_process is not None
            and self._run_process.state() is not QProcess.ProcessState.NotRunning
        ):
            raise RunConflictError("Only one Active Detect Run is allowed.")
        if (
            request.reservation_owner_id != self.reservation_owner_id
            or request.collection_id != collection.ref.collection_id
            or request.binding_revision != collection.ref.binding_revision
            or request.inventory_id != snapshot.inventory_id
            or request.inventory_digest != snapshot.digest
            or request.selected_recording_keys != snapshot.included_keys
            or request.setting("fixture_contract") != "lifecycle-v1"
        ):
            raise ValueError("Lifecycle fixture request does not match the frozen Detect inputs.")
        if self.root_decision is not RootBindingDecision.VALID or not snapshot_is_quickly_current(
            collection.source_root, snapshot
        ):
            raise ValueError("Recordings changed; rescan before starting a Detect Run.")

        repository = DetectRunRepository(
            self.store.application_data_root, collection.ref.collection_id
        )
        record = repository.create(request, title="Lifecycle boundary check")
        self._run_repository = repository
        self._cache_run(record, persist=False)
        self._diagnostic(
            "run_reserved",
            "Detect Run inputs frozen and reserved",
            record=record,
            status=record.status.value,
        )

        process = QProcess(self)
        self._run_process = process
        self._run_stdout_buffer = b""
        self._run_stderr = BoundedStderrCapture()
        self._run_error_code = ""
        self._protocol_error = ""
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.started.connect(self._on_run_process_started)
        process.readyReadStandardOutput.connect(self._on_run_stdout)
        process.readyReadStandardError.connect(self._on_run_stderr)
        process.errorOccurred.connect(self._on_run_process_error)
        process.finished.connect(self._on_run_finished)
        program, arguments = self._fixture_worker_command(
            repository.request_path(record.run_id), behavior
        )
        process.setProgram(program)
        process.setArguments(arguments)
        process.start()
        self._diagnostic(
            "worker_launch_requested",
            "Detect Worker launch requested",
            record=record,
            status=record.status.value,
        )
        return record.run_id

    def freeze_run_request(
        self,
        settings: Mapping[str, bool | int | float | str | None],
    ) -> DetectRunRequest:
        """Freeze the accepted ST-04/ST-05 handoffs without launching a Worker."""
        collection = self.active_collection
        snapshot = self.snapshot
        model = self.model_reference
        if not self.inputs_ready or collection is None or snapshot is None or model is None:
            raise ValueError("Verified Model and recording inputs are required for a Detect Run.")
        token = uuid.uuid4().hex
        return DetectRunRequest.create(
            run_id=f"drun_{token}",
            request_id=f"dreq_{uuid.uuid4().hex}",
            launch_id=f"launch_{uuid.uuid4().hex}",
            reservation_owner_id=self.reservation_owner_id,
            collection_id=collection.ref.collection_id,
            binding_revision=collection.ref.binding_revision,
            inventory_id=snapshot.inventory_id,
            inventory_digest=snapshot.digest,
            selected_recording_keys=snapshot.included_keys,
            model_snapshot_id=model.snapshot.snapshot_id,
            model_digest=canonical_digest(model.snapshot.to_dict()),
            settings=settings,
            artifact_id=f"pub_{uuid.uuid4().hex}",
        )

    def _fixture_worker_command(self, request_path: Path, behavior: str) -> tuple[str, list[str]]:
        return (
            sys.executable,
            [
                "-m",
                "biocall_studio.detect.fixture_worker",
                "--request",
                str(request_path),
                "--owner-lease",
                str(self._owner_lease.path),
                "--behavior",
                behavior,
                "--step-delay",
                str(self._worker_step_delay_seconds),
            ],
        )

    def _cache_run(self, record: DetectRunRecord, *, persist: bool = True) -> None:
        repository = self._run_repository
        if repository is None:
            raise ValueError("Detect Run repository is unavailable.")
        if persist:
            repository.save_record(record)
        by_id = {item.run_id: item for item in self.runs}
        by_id[record.run_id] = record
        self.runs = tuple(
            sorted(by_id.values(), key=lambda item: (item.created_at, item.run_id), reverse=True)
        )
        active = [item for item in self.runs if item.active]
        if len(active) > 1:
            raise RunConflictError("Persisted Detect Run history has multiple Active Runs.")
        self.current_run = active[0] if active else record
        self.run_changed.emit(record)
        self.state_changed.emit()

    def _diagnostic(
        self,
        event: str,
        message: str,
        *,
        record: DetectRunRecord,
        level: str = "INFO",
        status: str | None = None,
        **numbers: object,
    ) -> None:
        repository = self._run_repository
        if repository is None:
            return
        try:
            path = resolve_run_log_path(
                repository.collection_root, record.run_id, "supervisor", create=True
            )
            context: dict[str, object] = {
                "run_id": record.run_id,
                "request_id": record.request_id,
                "launch_id": record.launch_id,
                "status": status or record.status.value,
                **numbers,
            }
            BoundedJsonlLog(path).write(
                encode_diagnostic_record(
                    component="detect.supervisor",
                    event=event,
                    message=message,
                    level=level,
                    context=context,
                )
            )
        except (OSError, ValueError):
            return

    def _on_run_process_started(self) -> None:
        process = self._run_process
        record = self.current_run
        if (
            process is None
            or record is None
            or record.status is not DetectRunStatus.PREPARING
        ):
            return
        updated = transition_run(
            record,
            DetectRunStatus.RUNNING,
            now=utc_now(),
            process_id=int(process.processId()),
            message="Worker started",
        )
        self._cache_run(updated)
        self._diagnostic(
            "worker_started",
            "Detect Worker process started",
            record=updated,
            status=updated.status.value,
        )

    def _on_run_stdout(self) -> None:
        process = self._run_process
        if process is None:
            return
        self._run_stdout_buffer += bytes(process.readAllStandardOutput())
        if len(self._run_stdout_buffer) > 1_048_576:
            self._set_protocol_error("worker_protocol_overflow")
            process.kill()
            return
        while b"\n" in self._run_stdout_buffer:
            line, self._run_stdout_buffer = self._run_stdout_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            if len(line) > 4_096:
                self._set_protocol_error("worker_protocol_invalid")
                continue
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._set_protocol_error("worker_protocol_invalid")
                continue
            self._apply_worker_event(event)

    def _apply_worker_event(self, event: object) -> None:
        if not isinstance(event, dict) or event.get("schema_version") != 1:
            self._set_protocol_error("worker_protocol_invalid")
            return
        record = self.current_run
        if record is None:
            return
        name = event.get("event")
        if name == "progress" and record.status is DetectRunStatus.RUNNING:
            messages = {
                "Frozen inputs accepted",
                "Worker lifecycle active",
                "Verifying immutable publication",
            }
            message = event.get("message")
            if message not in messages:
                self._set_protocol_error("worker_protocol_invalid")
                return
            try:
                updated = update_run_progress(
                    record,
                    progress=event["progress"],
                    stage_index=event["stage_index"],
                    now=utc_now(),
                    message=message,
                )
            except (KeyError, TypeError, ValueError):
                self._set_protocol_error("worker_protocol_invalid")
            else:
                self._cache_run(updated)
        elif name == "error":
            code = event.get("error_code")
            if code in {"fixture_failed", "publication_failed"}:
                self._run_error_code = code
            else:
                self._set_protocol_error("worker_protocol_invalid")
        elif name not in {"started", "completed", "cancelled"}:
            self._set_protocol_error("worker_protocol_invalid")

    def _set_protocol_error(self, code: str) -> None:
        if not self._protocol_error and self.current_run is not None:
            self._diagnostic(
                "worker_protocol_failed",
                "Detect Worker progress protocol validation failed",
                record=self.current_run,
                level="ERROR",
            )
        self._protocol_error = code

    def _on_run_stderr(self) -> None:
        process = self._run_process
        if process is not None:
            self._run_stderr.feed(bytes(process.readAllStandardError()))

    def _on_run_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and not self._protocol_error:
            self._protocol_error = "worker_launch_failed"

    def _on_run_finished(self, exit_code: int, exit_status) -> None:
        process = self._run_process
        record = self.current_run
        repository = self._run_repository
        if process is None or record is None or repository is None:
            return
        self._on_run_stdout()
        self._on_run_stderr()
        self._run_stderr.finish()
        if self._run_stderr.lines or self._run_stderr.dropped_bytes:
            self._diagnostic(
                "worker_stderr_observed",
                self._run_stderr.summary,
                record=record,
                level="WARNING",
                dropped_bytes=self._run_stderr.dropped_bytes,
            )

        receipt = repository.verified_receipt(record, recover_missing=True)
        if receipt is not None:
            updated = complete_run(record, receipt, now=utc_now())
            event = "run_completed"
            level = "INFO"
        elif record.status is DetectRunStatus.CANCELLING:
            updated = transition_run(
                record,
                DetectRunStatus.CANCELLED,
                now=utc_now(),
                message="Cancelled · staged output not published",
            )
            event = "run_cancelled"
            level = "WARNING"
        elif exit_status == QProcess.ExitStatus.CrashExit and not self._protocol_error:
            updated = transition_run(
                record,
                DetectRunStatus.INTERRUPTED,
                now=utc_now(),
                message="Worker supervision was interrupted",
                error_code="worker_interrupted",
                error_message="The Worker stopped unexpectedly. Start a new Run.",
            )
            event = "worker_interrupted"
            level = "ERROR"
        else:
            error_code = self._protocol_error or self._run_error_code or "worker_failed"
            guidance = {
                "publication_failed": "The Run artifact could not be published safely.",
                "fixture_failed": "The Worker reported a controlled lifecycle failure.",
                "worker_protocol_invalid": "The Worker returned invalid progress information.",
                "worker_protocol_overflow": "The Worker returned too much progress information.",
                "worker_launch_failed": "The Worker could not be started.",
                "worker_failed": "The Worker failed before publishing a verified artifact.",
            }.get(error_code, "The Worker failed before publishing a verified artifact.")
            updated = transition_run(
                record,
                DetectRunStatus.FAILED,
                now=utc_now(),
                message="Run failed without a published artifact",
                error_code=error_code,
                error_message=guidance,
            )
            event = "run_failed"
            level = "ERROR"
        if updated.status is not DetectRunStatus.COMPLETED:
            repository.cleanup_staging(updated)
        self._cache_run(updated)
        self._diagnostic(
            event,
            "Detect Run reached a verified terminal state",
            record=updated,
            level=level,
            status=updated.status.value,
            exit_code=exit_code,
        )
        self._run_process = None
        process.deleteLater()
        self._run_stdout_buffer = b""
        self._maybe_finish_shutdown()

    def cancel_active_run(self) -> None:
        record = self.current_run
        repository = self._run_repository
        if (
            record is None
            or repository is None
            or not record.active
            or record.status is DetectRunStatus.CANCELLING
        ):
            return
        updated = transition_run(
            record,
            DetectRunStatus.CANCELLING,
            now=utc_now(),
            message="Cancellation requested",
        )
        repository.request_cancellation(record.run_id)
        self._cache_run(updated)
        self._diagnostic(
            "run_cancel_requested",
            "Detect Run cancellation requested",
            record=updated,
            level="WARNING",
        )
        QTimer.singleShot(self._cancel_grace_ms, lambda: self._terminate_run(record.run_id))
        QTimer.singleShot(self._kill_grace_ms, lambda: self._kill_run(record.run_id))

    def _terminate_run(self, run_id: str) -> None:
        if (
            self.current_run is not None
            and self.current_run.run_id == run_id
            and self.current_run.status is DetectRunStatus.CANCELLING
            and self._run_process is not None
            and self._run_process.state() is not QProcess.ProcessState.NotRunning
        ):
            self._run_process.terminate()

    def _kill_run(self, run_id: str) -> None:
        if (
            self.current_run is not None
            and self.current_run.run_id == run_id
            and self.current_run.status is DetectRunStatus.CANCELLING
            and self._run_process is not None
            and self._run_process.state() is not QProcess.ProcessState.NotRunning
        ):
            self._run_process.kill()

    def safe_run_log_path(self, run_id: str) -> Path | None:
        repository = self._run_repository
        if repository is None:
            return None
        try:
            path = resolve_run_log_path(
                repository.collection_root, run_id, "supervisor", create=False
            )
        except (FileNotFoundError, OSError, ValueError):
            return None
        return path if path.is_file() and not path.is_symlink() else None

    @property
    def shutdown_is_ready(self) -> bool:
        process_running = (
            self._run_process is not None
            and self._run_process.state() is not QProcess.ProcessState.NotRunning
        )
        return (
            not process_running
            and not self.is_run_active
            and not self.is_scanning
            and not self.is_model_loading
        )

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        if self.is_scanning:
            self.cancel_scan()
        if self.is_run_active:
            self.cancel_active_run()
        self._maybe_finish_shutdown()

    def _maybe_finish_shutdown(self) -> None:
        if (
            self._shutdown_requested
            and self.shutdown_is_ready
            and not self._shutdown_finished
        ):
            self._owner_lease.close()
            self._shutdown_finished = True

    def shutdown(self) -> None:
        if self._shutdown_finished:
            return
        process = self._run_process
        record = self.current_run
        repository = self._run_repository
        if process is not None and process.state() is not QProcess.ProcessState.NotRunning:
            process.blockSignals(True)
            if record is not None and repository is not None and record.active:
                repository.request_cancellation(record.run_id)
            process.terminate()
            if not process.waitForFinished(500):
                process.kill()
                process.waitForFinished(500)
            self._run_process = None
            process.deleteLater()
            if record is not None and repository is not None and record.active:
                receipt = repository.verified_receipt(record, recover_missing=True)
                if receipt is not None:
                    updated = complete_run(record, receipt, now=utc_now())
                else:
                    status = (
                        DetectRunStatus.CANCELLED
                        if record.status is DetectRunStatus.CANCELLING
                        else DetectRunStatus.INTERRUPTED
                    )
                    updated = transition_run(
                        record,
                        status,
                        now=utc_now(),
                        message="Worker stopped during application shutdown",
                        error_code=(
                            "" if status is DetectRunStatus.CANCELLED else "worker_interrupted"
                        ),
                        error_message=(
                            ""
                            if status is DetectRunStatus.CANCELLED
                            else "The application stopped before publication completed."
                        ),
                    )
                    repository.cleanup_staging(updated)
                self._cache_run(updated)
        self._owner_lease.close()
        self._shutdown_finished = True
