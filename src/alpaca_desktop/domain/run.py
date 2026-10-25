"""Pure Run lifecycle, recovery, and reservation rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from alpaca_desktop.domain.paths import validate_relative_path

RUN_STATE_SCHEMA_VERSION = 1
MAX_ACTIVITY_ENTRIES = 200
MAX_ACTIVITY_MESSAGE_LENGTH = 1_000


class RunKind(StrEnum):
    DATASET_BUILD = "dataset_build"
    TRAINING = "training"


class RunStatus(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE_RUN_STATUSES = frozenset(
    {
        RunStatus.CREATED,
        RunStatus.STARTING,
        RunStatus.RUNNING,
        RunStatus.CANCELLING,
    }
)
TERMINAL_RUN_STATUSES = frozenset(set(RunStatus) - ACTIVE_RUN_STATUSES)

_TRANSITIONS = {
    RunStatus.CREATED: frozenset(
        {
            RunStatus.STARTING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }
    ),
    RunStatus.STARTING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.CANCELLING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
        }
    ),
    RunStatus.CANCELLING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.INTERRUPTED: frozenset(),
}


class RunTransitionError(ValueError):
    pass


class RunConflictError(ValueError):
    pass


@dataclass(frozen=True)
class RunReservation:
    kind: RunKind
    collection_id: str
    input_dataset_id: str | None
    output_kind: str
    output_id: str


@dataclass(frozen=True)
class RunState:
    run_id: str
    request_id: str
    kind: RunKind
    title: str
    status: RunStatus
    collection_id: str
    input_dataset_id: str | None
    output_kind: str
    output_id: str
    stages: tuple[str, ...]
    stage_index: int
    progress: int
    created_at: str
    updated_at: str
    activity: tuple[str, ...]
    error: str
    published_artifact_id: str | None

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_RUN_STATUSES

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES

    @property
    def reservation(self) -> RunReservation:
        return RunReservation(
            self.kind,
            self.collection_id,
            self.input_dataset_id,
            self.output_kind,
            self.output_id,
        )

    @property
    def current_stage(self) -> str:
        if self.status is RunStatus.COMPLETED:
            return "Finished"
        return self.stages[min(self.stage_index, len(self.stages) - 1)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_STATE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "kind": self.kind.value,
            "title": self.title,
            "status": self.status.value,
            "collection_id": self.collection_id,
            "input_dataset_id": self.input_dataset_id,
            "output_kind": self.output_kind,
            "output_id": self.output_id,
            "stages": list(self.stages),
            "stage_index": self.stage_index,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "activity": list(self.activity),
            "error": self.error,
            "published_artifact_id": self.published_artifact_id,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RunState:
        if not isinstance(raw, dict) or raw.get("schema_version") != RUN_STATE_SCHEMA_VERSION:
            raise ValueError("Unsupported Run State schema.")
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "kind",
            "title",
            "status",
            "collection_id",
            "input_dataset_id",
            "output_kind",
            "output_id",
            "stages",
            "stage_index",
            "progress",
            "created_at",
            "updated_at",
            "activity",
            "error",
            "published_artifact_id",
        }
        if set(raw) != expected:
            raise ValueError("Run State fields do not match its schema.")
        try:
            state = cls(
                run_id=_portable_id(raw["run_id"], "Run ID"),
                request_id=_portable_id(raw["request_id"], "request ID"),
                kind=RunKind(raw["kind"]),
                title=_required_text(raw["title"], "Run title"),
                status=RunStatus(raw["status"]),
                collection_id=_portable_id(raw["collection_id"], "Collection ID"),
                input_dataset_id=_optional_id(raw["input_dataset_id"], "input Dataset ID"),
                output_kind=_output_kind(raw["output_kind"]),
                output_id=_portable_id(raw["output_id"], "output ID"),
                stages=_stages(raw["stages"]),
                stage_index=_integer(raw["stage_index"], "Run stage index"),
                progress=_integer(raw["progress"], "Run progress"),
                created_at=_required_text(raw["created_at"], "Run creation time"),
                updated_at=_required_text(raw["updated_at"], "Run update time"),
                activity=_activity(raw["activity"]),
                error=_text(raw["error"], "Run error"),
                published_artifact_id=_optional_id(
                    raw["published_artifact_id"], "published artifact ID"
                ),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("Run State contains invalid values.") from exc
        _validate_state(state)
        return state


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    return value


def _required_text(value: object, label: str) -> str:
    value = _text(value, label)
    if not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return value


def _portable_id(value: object, label: str) -> str:
    value = _required_text(value, label)
    safe = validate_relative_path(value)
    if "/" in safe:
        raise ValueError(f"{label} must be one portable path segment.")
    return safe


def _optional_id(value: object, label: str) -> str | None:
    return None if value is None else _portable_id(value, label)


def _output_kind(value: object) -> str:
    if value not in {"dataset", "model"}:
        raise ValueError("Run output kind must be dataset or model.")
    return str(value)


def _stages(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("A Run requires at least one stage.")
    return tuple(_required_text(item, "Run stage") for item in value)


def _activity(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Run activity must be a list.")
    entries = tuple(_required_text(item, "Run activity entry") for item in value)
    if len(entries) > MAX_ACTIVITY_ENTRIES or any(
        len(item) > MAX_ACTIVITY_MESSAGE_LENGTH for item in entries
    ):
        raise ValueError("Run activity exceeds its bounded storage limit.")
    return entries


def _validate_state(state: RunState) -> None:
    if not 0 <= state.progress <= 100:
        raise ValueError("Run progress must be between 0 and 100.")
    maximum_stage = (
        len(state.stages) if state.status is RunStatus.COMPLETED else len(state.stages) - 1
    )
    if not 0 <= state.stage_index <= maximum_stage:
        raise ValueError("Run stage index is outside its stage list.")
    if state.kind is RunKind.DATASET_BUILD and state.output_kind != "dataset":
        raise ValueError("Dataset Build must reserve a Dataset output.")
    if state.kind is RunKind.TRAINING and state.output_kind != "model":
        raise ValueError("Training must reserve a Model output.")
    if state.status is RunStatus.COMPLETED:
        if state.progress != 100 or state.stage_index != len(state.stages):
            raise ValueError("A completed Run must finish every stage at 100 percent.")
        if state.published_artifact_id != state.output_id:
            raise ValueError("A completed Run must reference its verified prospective output.")
    elif state.published_artifact_id is not None:
        raise ValueError("Only a completed Run may reference a published artifact.")


def _append_activity(activity: tuple[str, ...], message: str | None) -> tuple[str, ...]:
    if message is None:
        return activity
    message = _required_text(message, "Run activity entry")
    if len(message) > MAX_ACTIVITY_MESSAGE_LENGTH:
        raise ValueError("Run activity entry exceeds its bounded storage limit.")
    return (*activity, message)[-MAX_ACTIVITY_ENTRIES:]


def new_run(
    *,
    run_id: str,
    request_id: str,
    kind: RunKind,
    title: str,
    collection_id: str,
    input_dataset_id: str | None,
    output_kind: str,
    output_id: str,
    stages: tuple[str, ...],
    now: str,
) -> RunState:
    state = RunState(
        run_id=_portable_id(run_id, "Run ID"),
        request_id=_portable_id(request_id, "request ID"),
        kind=RunKind(kind),
        title=_required_text(title, "Run title"),
        status=RunStatus.CREATED,
        collection_id=_portable_id(collection_id, "Collection ID"),
        input_dataset_id=_optional_id(input_dataset_id, "input Dataset ID"),
        output_kind=_output_kind(output_kind),
        output_id=_portable_id(output_id, "output ID"),
        stages=_stages(stages),
        stage_index=0,
        progress=0,
        created_at=_required_text(now, "Run creation time"),
        updated_at=now,
        activity=("Run created",),
        error="",
        published_artifact_id=None,
    )
    _validate_state(state)
    return state


def transition_run(
    state: RunState,
    status: RunStatus,
    *,
    now: str,
    message: str | None = None,
    error: str = "",
    published_artifact_id: str | None = None,
) -> RunState:
    status = RunStatus(status)
    if status not in _TRANSITIONS[state.status]:
        raise RunTransitionError(
            f"Run status cannot transition from {state.status.value} to {status.value}."
        )
    if status is RunStatus.COMPLETED:
        if published_artifact_id != state.output_id:
            raise RunTransitionError(
                "Completed Run output must match its prospective output reservation."
            )
        progress = 100
        stage_index = len(state.stages)
    else:
        if published_artifact_id is not None:
            raise RunTransitionError("Only a completed Run may publish an artifact pointer.")
        progress = state.progress
        stage_index = state.stage_index
    updated = replace(
        state,
        status=status,
        progress=progress,
        stage_index=stage_index,
        updated_at=_required_text(now, "Run update time"),
        activity=_append_activity(state.activity, message),
        error=_text(error, "Run error"),
        published_artifact_id=published_artifact_id,
    )
    _validate_state(updated)
    return updated


def update_run_progress(
    state: RunState,
    *,
    progress: int,
    stage_index: int,
    now: str,
    message: str | None = None,
) -> RunState:
    progress = _integer(progress, "Run progress")
    stage_index = _integer(stage_index, "Run stage index")
    if not state.active:
        raise RunTransitionError("Terminal Run progress cannot be updated.")
    if progress < state.progress or stage_index < state.stage_index:
        raise RunTransitionError("Run progress and stage updates must be monotonic.")
    if progress > 99:
        progress = 99
    updated = replace(
        state,
        progress=progress,
        stage_index=stage_index,
        updated_at=_required_text(now, "Run update time"),
        activity=_append_activity(state.activity, message),
    )
    _validate_state(updated)
    return updated


def assert_run_start_allowed(
    existing_runs: tuple[RunState, ...] | list[RunState], candidate: RunReservation
) -> None:
    if any(run.active for run in existing_runs):
        raise RunConflictError("Only one Active Run is allowed; wait for it to finish.")
    if any(
        run.output_kind == candidate.output_kind and run.output_id == candidate.output_id
        for run in existing_runs
    ):
        raise RunConflictError(
            f"The prospective {candidate.output_kind} output is already reserved: "
            f"{candidate.output_id}"
        )


def assert_collection_rebind_allowed(
    runs: tuple[RunState, ...] | list[RunState], new_collection_id: str | None
) -> None:
    active = next((run for run in runs if run.active), None)
    if active is not None and new_collection_id != active.collection_id:
        raise RunConflictError("Cannot rebind the Collection while an Active Run reserves it.")


def assert_dataset_mutable(runs: tuple[RunState, ...] | list[RunState], dataset_id: str) -> None:
    for run in runs:
        if run.active and (
            run.input_dataset_id == dataset_id
            or (run.output_kind == "dataset" and run.output_id == dataset_id)
        ):
            raise RunConflictError(f"Dataset {dataset_id} is reserved by the Active Run.")


def reconcile_run(
    state: RunState,
    *,
    now: str,
    completion_receipt: bool,
    published_output_valid: bool,
) -> RunState:
    """Choose a conservative restart state from durable evidence only."""
    if state.status is RunStatus.COMPLETED:
        if completion_receipt and published_output_valid:
            return state
        return replace(
            state,
            status=RunStatus.FAILED,
            progress=min(state.progress, 99),
            stage_index=min(state.stage_index, len(state.stages) - 1),
            updated_at=now,
            activity=_append_activity(state.activity, "Completed output no longer validates"),
            error="The completed Run output no longer validates.",
            published_artifact_id=None,
        )
    if state.terminal:
        return state
    if completion_receipt and published_output_valid:
        return replace(
            state,
            status=RunStatus.COMPLETED,
            progress=100,
            stage_index=len(state.stages),
            updated_at=now,
            activity=_append_activity(
                state.activity, "Recovered verified output after application restart"
            ),
            error="",
            published_artifact_id=state.output_id,
        )
    if state.status is RunStatus.CANCELLING:
        return transition_run(
            state,
            RunStatus.CANCELLED,
            now=now,
            message="Cancellation finalized after application restart",
        )
    return transition_run(
        state,
        RunStatus.INTERRUPTED,
        now=now,
        message="Worker was no longer supervised after application restart",
        error="The Worker was interrupted before verified completion.",
    )
