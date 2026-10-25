"""Collection selection, background Scan, and machine-local verified binding."""

import sys
import uuid
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QThread, QTimer, Signal

from alpaca_desktop.application.collection_scan import (
    CollectionScanCancelled,
    ScanProgress,
    inputs_match_scan,
    scan_collection,
)
from alpaca_desktop.domain.collection import ScanResult
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.domain.run import (
    RunConflictError,
    RunKind,
    RunReservation,
    RunState,
    RunStatus,
    append_run_measurement,
    assert_collection_rebind_allowed,
    assert_dataset_mutable,
    assert_run_start_allowed,
    new_run,
    transition_run,
    update_run_progress,
)
from alpaca_desktop.domain.training import FrozenTrainingConfig, TrainingDataset
from alpaca_desktop.persistence.collection_metadata import (
    load_collection_metadata,
    publish_collection_metadata,
)
from alpaca_desktop.persistence.datasets import (
    DatasetArtifact,
    DatasetDeletion,
    delete_dataset,
    load_dataset,
)
from alpaca_desktop.persistence.models import (
    ModelArtifact,
    discard_uncommitted_model,
    load_model,
)
from alpaca_desktop.persistence.runs import (
    create_run,
    load_completion_receipt,
    reconcile_runs,
    request_cancellation,
    save_run,
    utc_now,
    write_run_request,
)
from alpaca_desktop.persistence.settings import ApplicationSettings, SettingsStore
from alpaca_desktop.workflows.cnn_training import CnnTrainingRequest
from alpaca_desktop.workflows.dataset_build import DatasetBuildRequest


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
    build_started = Signal()
    build_completed = Signal(object)
    build_failed = Signal(str)
    build_cancelled = Signal()
    training_started = Signal()
    training_completed = Signal(object)
    training_failed = Signal(str)
    training_cancelled = Signal()
    run_changed = Signal(object)
    runs_changed = Signal()
    run_conflict = Signal(str)

    def __init__(
        self,
        settings_dir: Path | None = None,
        *,
        scan_step_delay_seconds: float = 0.0,
        worker_step_delay_seconds: float = 0.0,
        cancel_grace_ms: int = 1_500,
        kill_grace_ms: int = 3_000,
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
        self._replacement_scan_root: Path | None = None
        self._scan_step_delay_seconds = scan_step_delay_seconds
        self._runs: tuple[RunState, ...] = ()
        self._active_run: RunState | None = None
        self._run_process: QProcess | None = None
        self._current_run_id: str | None = None
        self._run_stdout_buffer = b""
        self._worker_error = ""
        self._protocol_error = ""
        self._worker_step_delay_seconds = worker_step_delay_seconds
        self._cancel_grace_ms = cancel_grace_ms
        self._kill_grace_ms = kill_grace_ms
        self._build_request_path: Path | None = None
        try:
            self._settings = self._store.load()
        except (OSError, ValueError) as exc:
            self.error_message = str(exc)
            self._settings_error_message = self.error_message
            self._settings = ApplicationSettings()
        if self.collection_path is not None:
            self._load_runs(self.collection_path)

    @property
    def collection_path(self) -> Path | None:
        return self._settings.collection_path

    @property
    def collection_id(self) -> str | None:
        return self._settings.collection_id

    @property
    def pending_collection_path(self) -> Path | None:
        return self._pending_collection_path

    @property
    def runs(self) -> tuple[RunState, ...]:
        return self._runs

    @property
    def active_run(self) -> RunState | None:
        return self._active_run

    @property
    def is_building(self) -> bool:
        return self._active_run is not None and self._active_run.kind is RunKind.DATASET_BUILD

    @property
    def reserved_dataset_ids(self) -> frozenset[str]:
        if self._active_run is None:
            return frozenset()
        reserved = {
            identifier
            for identifier in (
                self._active_run.input_dataset_id,
                self._active_run.output_id if self._active_run.output_kind == "dataset" else None,
            )
            if identifier is not None
        }
        return frozenset(reserved)

    def request_collection(self, directory: str) -> None:
        """Keep picker intent pending until its background Scan validates and publishes."""
        requested = Path(directory) if directory else None
        if (
            requested is not None
            and self._active_run is not None
            and (self.collection_path is None or requested.resolve() != self.collection_path)
        ):
            self.error_message = "Cannot rebind the Collection while an Active Run reserves it."
            self.run_conflict.emit(self.error_message)
            return
        self._pending_collection_path = requested
        self.pending_changed.emit()
        if self._pending_collection_path is not None:
            if self.is_scanning:
                if self._pending_collection_path != self._scan_root:
                    self._replacement_scan_root = self._pending_collection_path
                    self.cancel_scan()
                return
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
        resolved_path = path.resolve(strict=True)
        if (
            self._active_run is not None
            and self.collection_path is not None
            and resolved_path != self.collection_path
        ):
            raise RunConflictError(
                "Cannot rebind the Collection path while an Active Run reserves it."
            )
        metadata = load_collection_metadata(path)
        expected_id = collection_id or metadata.collection_id
        if metadata.collection_id != expected_id:
            raise ValueError("Collection identity does not match the verified binding.")
        assert_collection_rebind_allowed(self._runs, expected_id)
        self._save(ApplicationSettings(resolved_path, expected_id))
        # A same-identity refresh may finish while this Controller still owns a
        # live Worker. Startup reconciliation is only valid without a supervisor.
        if self._active_run is None:
            self._load_runs(path)
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

    def start_dataset_build(self, config: BuildConfig, *, dataset_id: str | None = None) -> str:
        """Persist and supervise one Dataset Build in the current app environment."""
        if (
            self.scan_result is None
            or self.collection_path is None
            or self.collection_id is None
            or not self.current_inputs_ready()
        ):
            raise ValueError("Rescan the Collection before Dataset Build.")
        run_id = f"run-{uuid.uuid4()}"
        request_id = f"request-{uuid.uuid4()}"
        dataset_id = dataset_id or f"dataset-{uuid.uuid4()}"
        reservation = RunReservation(
            RunKind.DATASET_BUILD,
            self.collection_id,
            None,
            "dataset",
            dataset_id,
        )
        assert_run_start_allowed(self._runs, reservation)
        state = new_run(
            run_id=run_id,
            request_id=request_id,
            kind=RunKind.DATASET_BUILD,
            title=f"Build · {self.scan_result.root_name}",
            collection_id=self.collection_id,
            input_dataset_id=None,
            output_kind="dataset",
            output_id=dataset_id,
            stages=(
                "Validate inputs",
                "Mine negative Snippets",
                "Write train / val Splits",
                "Verify and publish Dataset",
            ),
            now=utc_now(),
        )
        create_run(self.collection_path, state)
        self._set_run(state)
        request = DatasetBuildRequest(
            run_id,
            request_id,
            str(self.collection_path),
            self.collection_id,
            config,
            dataset_id,
        )
        try:
            self._build_request_path = write_run_request(
                self.collection_path, run_id, request.to_dict()
            )
            state = transition_run(
                state,
                RunStatus.STARTING,
                now=utc_now(),
                message="Starting Dataset Build Worker",
            )
            self._set_run(state)
        except Exception as exc:
            failed = transition_run(
                state,
                RunStatus.FAILED,
                now=utc_now(),
                error=self._portable_error(str(exc)),
                message="Worker request could not be prepared",
            )
            self._set_run(failed)
            self.build_failed.emit(failed.error)
            raise

        self._start_worker("dataset-build", self._build_request_path)
        return run_id

    def start_training(
        self,
        config: FrozenTrainingConfig,
        *,
        model_label: str,
        model_id: str | None = None,
    ) -> str:
        """Persist and supervise one genuine CNN Training Run."""
        if self.collection_path is None or self.collection_id is None:
            raise ValueError("Select a validated Collection before Training.")
        if config.family != "cnn":
            raise ValueError("Spec 05b starts genuine CNN Training only.")
        try:
            dataset = load_dataset(self.collection_path, config.dataset_id)
            TrainingDataset.from_artifact(dataset)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Selected Dataset is missing or unsafe: {exc}") from exc
        run_id = f"run-{uuid.uuid4()}"
        request_id = f"request-{uuid.uuid4()}"
        model_id = model_id or f"model-{uuid.uuid4()}"
        reservation = RunReservation(
            RunKind.TRAINING,
            self.collection_id,
            dataset.dataset_id,
            "model",
            model_id,
        )
        assert_run_start_allowed(self._runs, reservation)
        candidate = CnnTrainingRequest(
            run_id,
            request_id,
            str(self.collection_path),
            self.collection_id,
            config,
            model_id,
            model_label,
        )
        request = CnnTrainingRequest.from_dict(candidate.to_dict())
        final = self.collection_path / ".alpaca" / "models" / request.model_id
        if final.exists():
            raise RunConflictError(f"The prospective model output already exists: {model_id}")
        run_name = str(config.effective_values["run_name"]).strip()
        state = new_run(
            run_id=run_id,
            request_id=request_id,
            kind=RunKind.TRAINING,
            title=run_name or f"Train CNN · {dataset.label}",
            collection_id=self.collection_id,
            input_dataset_id=dataset.dataset_id,
            output_kind="model",
            output_id=model_id,
            stages=(
                "Validate immutable Dataset",
                "Prepare spectrogram batches",
                "Train and validate CNN",
                "Verify and publish Model",
            ),
            now=utc_now(),
        )
        create_run(self.collection_path, state)
        self._set_run(state)
        try:
            self._build_request_path = write_run_request(
                self.collection_path, run_id, request.to_dict()
            )
            state = transition_run(
                state,
                RunStatus.STARTING,
                now=utc_now(),
                message="Starting CNN Training Worker",
            )
            self._set_run(state)
        except Exception as exc:
            failed = transition_run(
                state,
                RunStatus.FAILED,
                now=utc_now(),
                error=self._portable_error(str(exc)),
                message="CNN Worker request could not be prepared",
            )
            self._set_run(failed)
            self.training_failed.emit(failed.error)
            raise
        self._start_worker("cnn-training", self._build_request_path)
        return run_id

    def _start_worker(self, worker: str, request_path: Path) -> None:
        process = QProcess(self)
        self._run_process = process
        self._current_run_id = self._active_run.run_id if self._active_run is not None else None
        self._run_stdout_buffer = b""
        self._worker_error = ""
        self._protocol_error = ""
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.started.connect(self._on_run_process_started)
        process.readyReadStandardOutput.connect(self._on_run_stdout)
        process.finished.connect(self._on_run_finished)
        process.errorOccurred.connect(self._on_run_process_error)
        arguments = [
            "--worker",
            worker,
            "--request",
            str(request_path),
            "--worker-step-delay",
            str(self._worker_step_delay_seconds),
        ]
        process.setProgram(sys.executable)
        process.setArguments(
            arguments if getattr(sys, "frozen", False) else ["-m", "alpaca_desktop", *arguments]
        )
        if worker == "dataset-build":
            self.build_started.emit()
        else:
            self.training_started.emit()
        process.start()

    def cancel_active_run(self) -> None:
        state = self._active_run
        root = self.collection_path
        if state is None or root is None or state.status is RunStatus.CANCELLING:
            return
        state = transition_run(
            state,
            RunStatus.CANCELLING,
            now=utc_now(),
            message="Cancellation requested",
        )
        request_cancellation(root, state.run_id)
        self._set_run(state)
        run_id = state.run_id
        QTimer.singleShot(self._cancel_grace_ms, lambda: self._terminate_run(run_id))
        QTimer.singleShot(self._kill_grace_ms, lambda: self._kill_run(run_id))

    def delete_dataset(self, dataset_id: str) -> DatasetDeletion:
        if self.collection_path is None:
            raise ValueError("No Collection is bound.")
        assert_dataset_mutable(self._runs, dataset_id)
        return delete_dataset(
            self.collection_path,
            dataset_id,
            reserved_dataset_ids=self.reserved_dataset_ids,
        )

    def shutdown(self) -> None:
        """Stop a supervised Worker before the GUI process exits."""
        process = self._run_process
        state = self._active_run
        root = self.collection_path
        if process is None or state is None or root is None:
            return
        process.blockSignals(True)
        request_cancellation(root, state.run_id)
        if process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(500):
                process.kill()
                process.waitForFinished(500)
        self._run_process = None
        self._current_run_id = None
        self._build_request_path = None
        process.deleteLater()
        self._load_runs(root)
        self.runs_changed.emit()

    def _set_run(self, state: RunState) -> None:
        if self.collection_path is None:
            raise ValueError("No Collection is bound for Run State.")
        save_run(self.collection_path, state)
        by_id = {run.run_id: run for run in self._runs}
        by_id[state.run_id] = state
        self._runs = tuple(
            sorted(by_id.values(), key=lambda run: (run.created_at, run.run_id), reverse=True)
        )
        active = [run for run in self._runs if run.active]
        if len(active) > 1:
            raise RunConflictError("Persisted Run State contains more than one Active Run.")
        self._active_run = active[0] if active else None
        self.run_changed.emit(state)
        self.runs_changed.emit()

    def _load_runs(self, root: Path) -> None:
        try:
            self._runs = reconcile_runs(root)
        except (OSError, ValueError) as exc:
            self._runs = ()
            self._active_run = None
            self.error_message = f"Run history could not be loaded: {exc}"
            return
        active = [run for run in self._runs if run.active]
        if active:
            self.error_message = "Run reconciliation left an unexpected Active Run."
            self._active_run = None
        else:
            self._active_run = None

    def _on_run_process_started(self) -> None:
        state = self._active_run
        if state is None or state.status is not RunStatus.STARTING:
            return
        self._set_run(
            transition_run(
                state,
                RunStatus.RUNNING,
                now=utc_now(),
                message=(
                    "Dataset Build Worker started"
                    if state.kind is RunKind.DATASET_BUILD
                    else "CNN Training Worker started"
                ),
            )
        )

    def _on_run_stdout(self) -> None:
        import json

        process = self._run_process
        if process is None:
            return
        self._run_stdout_buffer += bytes(process.readAllStandardOutput())
        if len(self._run_stdout_buffer) > 1_000_000:
            self._protocol_error = "Worker progress exceeded its 1 MiB bound."
            process.kill()
            return
        while b"\n" in self._run_stdout_buffer:
            line, self._run_stdout_buffer = self._run_stdout_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._protocol_error = "Worker sent invalid structured progress."
                continue
            self._apply_worker_event(event)

    def _apply_worker_event(self, event: object) -> None:
        if not isinstance(event, dict) or event.get("schema_version") != 1:
            self._protocol_error = "Worker sent an unsupported progress event."
            return
        state = self._active_run
        if state is None:
            return
        event_name = event.get("event")
        message = self._portable_error(event.get("message", ""))
        if event_name == "progress" and state.status is RunStatus.RUNNING:
            try:
                updated = update_run_progress(
                    state,
                    progress=event["progress"],
                    stage_index=event["stage_index"],
                    message=message,
                    now=utc_now(),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._protocol_error = f"Worker progress was invalid: {exc}"
            else:
                self._set_run(updated)
        elif event_name == "measurement" and state.status is RunStatus.RUNNING:
            try:
                measurement = {
                    key: value
                    for key, value in event.items()
                    if key not in {"schema_version", "event", "message"}
                }
                self._set_run(append_run_measurement(state, measurement, now=utc_now()))
            except (TypeError, ValueError) as exc:
                self._protocol_error = f"Worker measurement was invalid: {exc}"
        elif event_name == "error":
            self._worker_error = message or "Worker failed."
        elif event_name not in {"started", "completed", "cancelled"}:
            self._protocol_error = "Worker sent an unknown progress event."

    def _on_run_finished(self, exit_code: int, exit_status) -> None:
        process = self._run_process
        state = self._active_run
        root = self.collection_path
        if process is None or state is None or root is None:
            return
        self._on_run_stdout()
        stderr = bytes(process.readAllStandardError()).decode(errors="replace").strip()
        artifact: DatasetArtifact | ModelArtifact | None = None
        result_error = ""
        try:
            load_completion_receipt(root, state)
            artifact = (
                load_dataset(root, state.output_id)
                if state.output_kind == "dataset"
                else load_model(root, state.output_id)
            )
        except (OSError, ValueError) as exc:
            result_error = str(exc)

        if exit_code == 0 and not self._protocol_error and artifact is not None:
            state = transition_run(
                state,
                RunStatus.COMPLETED,
                now=utc_now(),
                message="Completed · output verified and published",
                published_artifact_id=state.output_id,
            )
            self.error_message = ""
            self._set_run(state)
            if state.kind is RunKind.DATASET_BUILD:
                self.build_completed.emit(artifact)
            else:
                self.training_completed.emit(artifact)
        elif state.status is RunStatus.CANCELLING:
            state = transition_run(
                state,
                RunStatus.CANCELLED,
                now=utc_now(),
                message="Cancelled · staged output not published",
            )
            self._set_run(state)
            if state.kind is RunKind.DATASET_BUILD:
                self.build_cancelled.emit()
            else:
                self.training_cancelled.emit()
        elif exit_status == QProcess.ExitStatus.CrashExit:
            message = (
                "The Dataset Build Worker stopped unexpectedly."
                if state.kind is RunKind.DATASET_BUILD
                else "The CNN Training Worker stopped unexpectedly."
            )
            state = transition_run(
                state,
                RunStatus.INTERRUPTED,
                now=utc_now(),
                message="Worker process was interrupted",
                error=message,
            )
            self.error_message = message
            self._set_run(state)
            if state.kind is RunKind.DATASET_BUILD:
                self.build_failed.emit(message)
            else:
                self.training_failed.emit(message)
        else:
            message = self._protocol_error or self._worker_error
            if not message and stderr:
                message = stderr.rsplitlines()[-1]
            if not message:
                message = (
                    f"Worker returned an invalid published output: {result_error}"
                    if result_error
                    else "Worker failed."
                )
            message = self._portable_error(message)
            state = transition_run(
                state,
                RunStatus.FAILED,
                now=utc_now(),
                message=(
                    "Dataset Build failed"
                    if state.kind is RunKind.DATASET_BUILD
                    else "CNN Training failed"
                ),
                error=message,
            )
            self.error_message = message
            self._set_run(state)
            if state.kind is RunKind.DATASET_BUILD:
                self.build_failed.emit(message)
            else:
                self.training_failed.emit(message)
        if state.status is not RunStatus.COMPLETED and state.output_kind == "model":
            try:
                discard_uncommitted_model(
                    root,
                    state.output_id,
                    run_id=state.run_id,
                    request_id=state.request_id,
                )
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                self.error_message = (
                    f"{self.error_message} Uncommitted Model cleanup needs attention: "
                    f"{self._portable_error(str(exc))}"
                ).strip()
        self._load_runs(root)
        self.runs_changed.emit()
        self._run_process = None
        self._current_run_id = None
        self._build_request_path = None
        process.deleteLater()

    def _on_run_process_error(self, error) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._active_run is None:
            return
        state = self._active_run
        message = (
            "Dataset Build Worker could not start from the current application environment."
            if state.kind is RunKind.DATASET_BUILD
            else "CNN Training Worker could not start from the current application environment."
        )
        state = transition_run(
            state,
            RunStatus.FAILED,
            now=utc_now(),
            message="Worker could not start",
            error=message,
        )
        self.error_message = message
        self._set_run(state)
        process = self._run_process
        self._run_process = None
        self._current_run_id = None
        if process is not None:
            process.deleteLater()
        if state.kind is RunKind.DATASET_BUILD:
            self.build_failed.emit(message)
        else:
            self.training_failed.emit(message)

    def _terminate_run(self, run_id: str) -> None:
        if (
            self._active_run is not None
            and self._active_run.run_id == run_id
            and self._active_run.status is RunStatus.CANCELLING
            and self._run_process is not None
            and self._run_process.state() != QProcess.ProcessState.NotRunning
        ):
            self._run_process.terminate()

    def _kill_run(self, run_id: str) -> None:
        if (
            self._active_run is not None
            and self._active_run.run_id == run_id
            and self._active_run.status is RunStatus.CANCELLING
            and self._run_process is not None
            and self._run_process.state() != QProcess.ProcessState.NotRunning
        ):
            self._run_process.kill()

    def _portable_error(self, message: object) -> str:
        text = str(message)
        if self.collection_path is not None:
            text = text.replace(str(self.collection_path), "<Collection>")
        return text[:2_000]

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
        if self._restart_replacement_scan():
            return
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
        if self._restart_replacement_scan():
            return
        self.error_message = message
        self.scan_failed.emit(message)

    def _on_cancelled(self) -> None:
        self.is_scanning = False
        self.scan_result = None
        if self._restart_replacement_scan():
            return
        self.scan_cancelled.emit()

    def _restart_replacement_scan(self) -> bool:
        root = self._replacement_scan_root
        if root is None:
            return False
        self._replacement_scan_root = None
        self._start_scan(root)
        return True

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
