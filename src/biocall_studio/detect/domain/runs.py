"""Pure Detect Run, immutable request, receipt, and recovery contracts."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from biocall_studio.detect.domain import (
    validate_collection_id,
    validate_relative_reference,
)

DETECT_RUN_REQUEST_SCHEMA_VERSION = 1
DETECT_RUN_RECORD_SCHEMA_VERSION = 1
PUBLICATION_RECEIPT_SCHEMA_VERSION = 1
MAX_SELECTED_RECORDINGS = 100_000
MAX_RUN_ACTIVITY = 64
MAX_RUN_MESSAGE = 500

_RUN_ID = re.compile(r"drun_[0-9a-f]{32}")
_REQUEST_ID = re.compile(r"dreq_[0-9a-f]{32}")
_LAUNCH_ID = re.compile(r"launch_[0-9a-f]{32}")
_OWNER_ID = re.compile(r"owner_[0-9a-f]{32}")
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_MODEL_SNAPSHOT_ID = re.compile(r"mdl_[0-9a-f]{32}")
_ARTIFACT_ID = re.compile(r"pub_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SETTING_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_ARTIFACT_KIND = re.compile(r"[a-z][a-z0-9_]{0,63}")

_Scalar = bool | int | float | str | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utc(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be a UTC timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include UTC.")
    return value


def _identifier(value: object, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _bounded_text(value: object, label: str, *, maximum: int = MAX_RUN_MESSAGE) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    normalized = " ".join(value.split())
    if len(normalized) > maximum or any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{label} exceeds its bounded printable format.")
    return normalized


def _settings(
    value: Mapping[str, _Scalar] | tuple[tuple[str, _Scalar], ...],
) -> tuple[tuple[str, _Scalar], ...]:
    rows = tuple(value.items()) if isinstance(value, Mapping) else tuple(value)
    if len(rows) > 64:
        raise ValueError("Detect Run settings exceed the 64-field limit.")
    normalized: list[tuple[str, _Scalar]] = []
    for key, setting in rows:
        if not isinstance(key, str) or _SETTING_NAME.fullmatch(key) is None:
            raise ValueError("Detect Run setting name is invalid.")
        if not isinstance(setting, (bool, int, float, str, type(None))):
            raise ValueError("Detect Run settings must contain JSON scalar values.")
        if isinstance(setting, float) and not math.isfinite(setting):
            raise ValueError("Detect Run settings cannot contain non-finite numbers.")
        if isinstance(setting, str):
            setting = _bounded_text(setting, "Detect Run setting", maximum=500)
        normalized.append((key, setting))
    normalized.sort(key=lambda item: item[0])
    if len({key for key, _setting in normalized}) != len(normalized):
        raise ValueError("Detect Run settings contain duplicate names.")
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class DetectRunRequest:
    """Versioned path-free snapshot of all inputs reserved by one Detect Run."""

    schema_version: int
    run_id: str
    request_id: str
    launch_id: str
    reservation_owner_id: str
    collection_id: str
    binding_revision: int
    inventory_id: str
    inventory_digest: str
    selected_recording_keys: tuple[str, ...]
    model_snapshot_id: str
    model_digest: str
    settings: tuple[tuple[str, _Scalar], ...]
    artifact_id: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != DETECT_RUN_REQUEST_SCHEMA_VERSION:
            raise ValueError("Unsupported DetectRunRequest schema.")
        _identifier(self.run_id, _RUN_ID, "Detect Run ID")
        _identifier(self.request_id, _REQUEST_ID, "Detect request ID")
        _identifier(self.launch_id, _LAUNCH_ID, "Detect launch ID")
        _identifier(self.reservation_owner_id, _OWNER_ID, "reservation owner ID")
        validate_collection_id(self.collection_id)
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Detect binding revision is invalid.")
        _identifier(self.inventory_id, _INVENTORY_ID, "Inventory ID")
        _digest(self.inventory_digest, "Inventory digest")
        if not self.selected_recording_keys:
            raise ValueError("A Detect Run must reserve at least one recording.")
        if len(self.selected_recording_keys) > MAX_SELECTED_RECORDINGS:
            raise ValueError("Detect Run selection exceeds its bounded size.")
        normalized_keys = tuple(
            validate_relative_reference(key) for key in self.selected_recording_keys
        )
        if normalized_keys != self.selected_recording_keys:
            raise ValueError("Detect Run recording keys must already be normalized.")
        if normalized_keys != tuple(sorted(set(normalized_keys))):
            raise ValueError("Detect Run recording keys must be unique and sorted.")
        _identifier(self.model_snapshot_id, _MODEL_SNAPSHOT_ID, "ModelSnapshot ID")
        _digest(self.model_digest, "Model digest")
        if _settings(self.settings) != self.settings:
            raise ValueError("Detect Run settings must be canonically ordered.")
        _identifier(self.artifact_id, _ARTIFACT_ID, "publication artifact ID")
        _utc(self.created_at, "Detect Run creation time")

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        request_id: str,
        launch_id: str,
        reservation_owner_id: str,
        collection_id: str,
        binding_revision: int,
        inventory_id: str,
        inventory_digest: str,
        selected_recording_keys: tuple[str, ...] | list[str],
        model_snapshot_id: str,
        model_digest: str,
        settings: Mapping[str, _Scalar] | tuple[tuple[str, _Scalar], ...],
        artifact_id: str,
        created_at: str | None = None,
    ) -> DetectRunRequest:
        return cls(
            DETECT_RUN_REQUEST_SCHEMA_VERSION,
            run_id,
            request_id,
            launch_id,
            reservation_owner_id,
            collection_id,
            binding_revision,
            inventory_id,
            inventory_digest,
            tuple(selected_recording_keys),
            model_snapshot_id,
            model_digest,
            _settings(settings),
            artifact_id,
            created_at or utc_now(),
        )

    def setting(self, name: str) -> _Scalar:
        try:
            return dict(self.settings)[name]
        except KeyError as exc:
            raise KeyError(f"Detect Run setting is not frozen: {name}") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "launch_id": self.launch_id,
            "reservation_owner_id": self.reservation_owner_id,
            "collection_id": self.collection_id,
            "binding_revision": self.binding_revision,
            "inventory_id": self.inventory_id,
            "inventory_digest": self.inventory_digest,
            "selected_recording_keys": list(self.selected_recording_keys),
            "model_snapshot_id": self.model_snapshot_id,
            "model_digest": self.model_digest,
            "settings": [[key, value] for key, value in self.settings],
            "artifact_id": self.artifact_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> DetectRunRequest:
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "launch_id",
            "reservation_owner_id",
            "collection_id",
            "binding_revision",
            "inventory_id",
            "inventory_digest",
            "selected_recording_keys",
            "model_snapshot_id",
            "model_digest",
            "settings",
            "artifact_id",
            "created_at",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("DetectRunRequest document is invalid.")
        if not isinstance(raw["selected_recording_keys"], list) or not isinstance(
            raw["settings"], list
        ):
            raise ValueError("DetectRunRequest collections are invalid.")
        setting_rows: list[tuple[str, _Scalar]] = []
        for row in raw["settings"]:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("DetectRunRequest setting row is invalid.")
            setting_rows.append((row[0], row[1]))
        return cls(
            schema_version=raw["schema_version"],
            run_id=raw["run_id"],
            request_id=raw["request_id"],
            launch_id=raw["launch_id"],
            reservation_owner_id=raw["reservation_owner_id"],
            collection_id=raw["collection_id"],
            binding_revision=raw["binding_revision"],
            inventory_id=raw["inventory_id"],
            inventory_digest=raw["inventory_digest"],
            selected_recording_keys=tuple(raw["selected_recording_keys"]),
            model_snapshot_id=raw["model_snapshot_id"],
            model_digest=raw["model_digest"],
            settings=tuple(setting_rows),
            artifact_id=raw["artifact_id"],
            created_at=raw["created_at"],
        )


class DetectRunStatus(StrEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    COMPLETED = "completed"


_ACTIVE = frozenset(
    {DetectRunStatus.PREPARING, DetectRunStatus.RUNNING, DetectRunStatus.CANCELLING}
)
_TERMINAL = frozenset(set(DetectRunStatus) - _ACTIVE)
_TRANSITIONS = {
    DetectRunStatus.PREPARING: frozenset(
        {
            DetectRunStatus.RUNNING,
            DetectRunStatus.CANCELLING,
            DetectRunStatus.INTERRUPTED,
            DetectRunStatus.FAILED,
        }
    ),
    DetectRunStatus.RUNNING: frozenset(
        {
            DetectRunStatus.CANCELLING,
            DetectRunStatus.INTERRUPTED,
            DetectRunStatus.FAILED,
            DetectRunStatus.COMPLETED,
        }
    ),
    DetectRunStatus.CANCELLING: frozenset(
        {
            DetectRunStatus.CANCELLED,
            DetectRunStatus.INTERRUPTED,
            DetectRunStatus.FAILED,
            DetectRunStatus.COMPLETED,
        }
    ),
    DetectRunStatus.CANCELLED: frozenset(),
    DetectRunStatus.INTERRUPTED: frozenset(),
    DetectRunStatus.FAILED: frozenset(),
    DetectRunStatus.COMPLETED: frozenset(),
}


class RunTransitionError(ValueError):
    pass


class RunConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PublicationReceipt:
    schema_version: int
    run_id: str
    request_id: str
    launch_id: str
    artifact_id: str
    artifact_kind: str
    artifact_digest: str
    published_at: str

    def __post_init__(self) -> None:
        if self.schema_version != PUBLICATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("Unsupported PublicationReceipt schema.")
        _identifier(self.run_id, _RUN_ID, "Detect Run ID")
        _identifier(self.request_id, _REQUEST_ID, "Detect request ID")
        _identifier(self.launch_id, _LAUNCH_ID, "Detect launch ID")
        _identifier(self.artifact_id, _ARTIFACT_ID, "publication artifact ID")
        if (
            not isinstance(self.artifact_kind, str)
            or _ARTIFACT_KIND.fullmatch(self.artifact_kind) is None
        ):
            raise ValueError("Publication artifact kind is invalid.")
        _digest(self.artifact_digest, "Publication artifact digest")
        _utc(self.published_at, "Publication time")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "launch_id": self.launch_id,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "artifact_digest": self.artifact_digest,
            "published_at": self.published_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> PublicationReceipt:
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "launch_id",
            "artifact_id",
            "artifact_kind",
            "artifact_digest",
            "published_at",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("PublicationReceipt document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class DetectRunRecord:
    schema_version: int
    run_id: str
    request_id: str
    launch_id: str
    reservation_owner_id: str
    collection_id: str
    inventory_id: str
    model_snapshot_id: str
    artifact_id: str
    title: str
    status: DetectRunStatus
    stages: tuple[str, ...]
    stage_index: int
    progress: int
    process_id: int | None
    created_at: str
    updated_at: str
    activity: tuple[str, ...]
    error_code: str
    error_message: str
    published_artifact_id: str | None
    published_artifact_digest: str | None

    def __post_init__(self) -> None:
        if self.schema_version != DETECT_RUN_RECORD_SCHEMA_VERSION:
            raise ValueError("Unsupported DetectRunRecord schema.")
        _identifier(self.run_id, _RUN_ID, "Detect Run ID")
        _identifier(self.request_id, _REQUEST_ID, "Detect request ID")
        _identifier(self.launch_id, _LAUNCH_ID, "Detect launch ID")
        _identifier(self.reservation_owner_id, _OWNER_ID, "reservation owner ID")
        validate_collection_id(self.collection_id)
        _identifier(self.inventory_id, _INVENTORY_ID, "Inventory ID")
        _identifier(self.model_snapshot_id, _MODEL_SNAPSHOT_ID, "ModelSnapshot ID")
        _identifier(self.artifact_id, _ARTIFACT_ID, "publication artifact ID")
        if not isinstance(self.status, DetectRunStatus):
            raise ValueError("Detect Run status is invalid.")
        _bounded_text(self.title, "Detect Run title", maximum=100)
        if not self.stages or len(self.stages) > 16:
            raise ValueError("Detect Run stage list is invalid.")
        for stage in self.stages:
            _bounded_text(stage, "Detect Run stage", maximum=100)
        if type(self.progress) is not int or not 0 <= self.progress <= 100:
            raise ValueError("Detect Run progress is invalid.")
        maximum_stage = (
            len(self.stages) if self.status is DetectRunStatus.COMPLETED else len(self.stages) - 1
        )
        if type(self.stage_index) is not int or not 0 <= self.stage_index <= maximum_stage:
            raise ValueError("Detect Run stage index is invalid.")
        if self.process_id is not None and (
            type(self.process_id) is not int or self.process_id <= 0
        ):
            raise ValueError("Detect Worker process identity is invalid.")
        _utc(self.created_at, "Detect Run creation time")
        _utc(self.updated_at, "Detect Run update time")
        if len(self.activity) > MAX_RUN_ACTIVITY:
            raise ValueError("Detect Run activity exceeds its bounded history.")
        for message in self.activity:
            _bounded_text(message, "Detect Run activity")
        if self.error_code:
            if _ERROR_CODE.fullmatch(self.error_code) is None:
                raise ValueError("Detect Run error code is invalid.")
            _bounded_text(self.error_message, "Detect Run error message")
        elif self.error_message:
            raise ValueError("Detect Run error message requires a stable error code.")
        if self.status is DetectRunStatus.COMPLETED:
            if (
                self.progress != 100
                or self.stage_index != len(self.stages)
                or self.published_artifact_id != self.artifact_id
                or self.published_artifact_digest is None
            ):
                raise ValueError("Completed Detect Run publication evidence is incomplete.")
            _digest(self.published_artifact_digest, "published artifact digest")
        elif self.published_artifact_id is not None or self.published_artifact_digest is not None:
            raise ValueError("Only a completed Detect Run can reference a publication.")

    @property
    def active(self) -> bool:
        return self.status in _ACTIVE

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    @property
    def current_stage(self) -> str:
        if self.status is DetectRunStatus.COMPLETED:
            return "Complete"
        return self.stages[self.stage_index]

    def with_running_process(self, process_id: int, *, now: str) -> DetectRunRecord:
        return transition_run(
            self,
            DetectRunStatus.RUNNING,
            now=now,
            process_id=process_id,
            message="Worker started",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "launch_id": self.launch_id,
            "reservation_owner_id": self.reservation_owner_id,
            "collection_id": self.collection_id,
            "inventory_id": self.inventory_id,
            "model_snapshot_id": self.model_snapshot_id,
            "artifact_id": self.artifact_id,
            "title": self.title,
            "status": self.status.value,
            "stages": list(self.stages),
            "stage_index": self.stage_index,
            "progress": self.progress,
            "process_id": self.process_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "activity": list(self.activity),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "published_artifact_id": self.published_artifact_id,
            "published_artifact_digest": self.published_artifact_digest,
        }

    @classmethod
    def from_dict(cls, raw: object) -> DetectRunRecord:
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "launch_id",
            "reservation_owner_id",
            "collection_id",
            "inventory_id",
            "model_snapshot_id",
            "artifact_id",
            "title",
            "status",
            "stages",
            "stage_index",
            "progress",
            "process_id",
            "created_at",
            "updated_at",
            "activity",
            "error_code",
            "error_message",
            "published_artifact_id",
            "published_artifact_digest",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("DetectRunRecord document is invalid.")
        if not isinstance(raw["stages"], list) or not isinstance(raw["activity"], list):
            raise ValueError("DetectRunRecord lists are invalid.")
        values: dict[str, Any] = dict(raw)
        values["status"] = DetectRunStatus(raw["status"])
        values["stages"] = tuple(raw["stages"])
        values["activity"] = tuple(raw["activity"])
        return cls(**values)


def _activity(existing: tuple[str, ...], message: str | None) -> tuple[str, ...]:
    if message is None:
        return existing
    safe = _bounded_text(message, "Detect Run activity")
    return (*existing, safe)[-MAX_RUN_ACTIVITY:]


def new_run_record(
    request: DetectRunRequest,
    *,
    title: str,
    stages: tuple[str, ...],
    now: str,
) -> DetectRunRecord:
    return DetectRunRecord(
        schema_version=DETECT_RUN_RECORD_SCHEMA_VERSION,
        run_id=request.run_id,
        request_id=request.request_id,
        launch_id=request.launch_id,
        reservation_owner_id=request.reservation_owner_id,
        collection_id=request.collection_id,
        inventory_id=request.inventory_id,
        model_snapshot_id=request.model_snapshot_id,
        artifact_id=request.artifact_id,
        title=_bounded_text(title, "Detect Run title", maximum=100),
        status=DetectRunStatus.PREPARING,
        stages=tuple(stages),
        stage_index=0,
        progress=0,
        process_id=None,
        created_at=_utc(now, "Detect Run creation time"),
        updated_at=now,
        activity=("Run inputs frozen",),
        error_code="",
        error_message="",
        published_artifact_id=None,
        published_artifact_digest=None,
    )


def assert_run_start_allowed(
    existing: list[DetectRunRecord] | tuple[DetectRunRecord, ...],
    request: DetectRunRequest,
) -> None:
    active = next((record for record in existing if record.active), None)
    if active is not None and active.run_id != request.run_id:
        raise RunConflictError("Only one Active Detect Run is allowed.")
    if any(
        record.run_id != request.run_id and record.artifact_id == request.artifact_id
        for record in existing
    ):
        raise RunConflictError("The Detect publication identity is already reserved.")


def transition_run(
    record: DetectRunRecord,
    status: DetectRunStatus,
    *,
    now: str,
    process_id: int | None = None,
    message: str | None = None,
    error_code: str = "",
    error_message: str = "",
) -> DetectRunRecord:
    status = DetectRunStatus(status)
    if status not in _TRANSITIONS[record.status]:
        raise RunTransitionError(
            f"Detect Run cannot transition from {record.status.value} to {status.value}."
        )
    if status is DetectRunStatus.COMPLETED:
        raise RunTransitionError("Detect Run completion requires a verified receipt.")
    if error_code and _ERROR_CODE.fullmatch(error_code) is None:
        raise RunTransitionError("Detect Run error code is invalid.")
    return replace(
        record,
        status=status,
        process_id=record.process_id if process_id is None else process_id,
        updated_at=_utc(now, "Detect Run update time"),
        activity=_activity(record.activity, message),
        error_code=error_code,
        error_message=(
            _bounded_text(error_message, "Detect Run error message") if error_code else ""
        ),
    )


def update_run_progress(
    record: DetectRunRecord,
    *,
    progress: int,
    stage_index: int,
    now: str,
    message: str | None = None,
) -> DetectRunRecord:
    if not record.active or record.status is DetectRunStatus.CANCELLING:
        raise RunTransitionError("This Detect Run does not accept progress updates.")
    if type(progress) is not int or type(stage_index) is not int:
        raise RunTransitionError("Detect Run progress must be integer-valued.")
    if progress < record.progress or stage_index < record.stage_index:
        raise RunTransitionError("Detect Run progress must be monotonic.")
    if not 0 <= stage_index < len(record.stages) or not 0 <= progress <= 99:
        raise RunTransitionError("Detect Run progress is outside its bounded range.")
    return replace(
        record,
        progress=progress,
        stage_index=stage_index,
        updated_at=_utc(now, "Detect Run update time"),
        activity=_activity(record.activity, message),
    )


def _receipt_matches(record: DetectRunRecord, receipt: PublicationReceipt) -> bool:
    return (
        receipt.run_id == record.run_id
        and receipt.request_id == record.request_id
        and receipt.launch_id == record.launch_id
        and receipt.artifact_id == record.artifact_id
    )


def complete_run(
    record: DetectRunRecord,
    receipt: PublicationReceipt,
    *,
    now: str,
    message: str = "Completed · artifact verified and published",
) -> DetectRunRecord:
    if record.status not in {DetectRunStatus.RUNNING, DetectRunStatus.CANCELLING}:
        raise RunTransitionError("Only a supervised Detect Worker can complete a Run.")
    if not _receipt_matches(record, receipt):
        raise RunTransitionError("Publication receipt does not match its Detect Run.")
    return replace(
        record,
        status=DetectRunStatus.COMPLETED,
        progress=100,
        stage_index=len(record.stages),
        updated_at=_utc(now, "Detect Run update time"),
        activity=_activity(record.activity, message),
        error_code="",
        error_message="",
        published_artifact_id=receipt.artifact_id,
        published_artifact_digest=receipt.artifact_digest,
    )


def recover_run(
    record: DetectRunRecord,
    *,
    receipt: PublicationReceipt | None,
    publication_valid: bool,
    now: str,
) -> DetectRunRecord:
    """Reconcile durable evidence without treating missing output as empty success."""
    if record.status is DetectRunStatus.COMPLETED:
        if receipt is not None and publication_valid and _receipt_matches(record, receipt):
            return record
        return replace(
            record,
            status=DetectRunStatus.FAILED,
            progress=min(record.progress, 99),
            stage_index=min(record.stage_index, len(record.stages) - 1),
            updated_at=_utc(now, "Detect Run update time"),
            activity=_activity(record.activity, "Published artifact no longer verifies"),
            error_code="publication_invalid",
            error_message="The published Run artifact is missing or changed.",
            published_artifact_id=None,
            published_artifact_digest=None,
        )
    if record.terminal:
        return record
    if receipt is not None and publication_valid and _receipt_matches(record, receipt):
        return complete_run(
            record,
            receipt,
            now=now,
            message="Recovered verified publication after restart",
        )
    status = (
        DetectRunStatus.CANCELLED
        if record.status is DetectRunStatus.CANCELLING
        else DetectRunStatus.INTERRUPTED
    )
    return transition_run(
        record,
        status,
        now=now,
        message=(
            "Cancellation finalized after restart"
            if status is DetectRunStatus.CANCELLED
            else "Worker supervision was lost before verified publication"
        ),
        error_code=("" if status is DetectRunStatus.CANCELLED else "worker_interrupted"),
        error_message=(
            "" if status is DetectRunStatus.CANCELLED else "The Worker stopped unexpectedly."
        ),
    )


def canonical_digest(payload: object) -> str:
    """Hash a canonical path-free contract, used for ST-07 handoff inputs."""
    import hashlib

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
