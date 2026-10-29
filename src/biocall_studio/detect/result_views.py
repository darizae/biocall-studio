"""Pure ST-08 Result projections and app-owned per-Result selections."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from biocall_studio.detect.results import (
    CandidateInterval,
    DetectionResult,
    FileOutcomeStatus,
    RecordingOutcome,
)
from biocall_studio.detect.rf_refinement import (
    DerivedRecording,
    DerivedResult,
    RefinedCandidate,
    RefinementStatus,
    ResultArtifact,
)
from biocall_studio.detect.runs import utc_now

RESULT_SELECTION_SCHEMA_VERSION = 1
FROZEN_RESULT_SELECTION_SCHEMA_VERSION = 2
MAX_SELECTED_CANDIDATES = 100_000
MAX_SELECTION_BYTES = 1_048_576
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ResultContentState(StrEnum):
    POPULATED = "populated"
    EMPTY = "empty"
    PARTIAL = "partial"


class ResultSourceState(StrEnum):
    AVAILABLE = "available"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class SelectionReconciliation(StrEnum):
    CURRENT = "current"
    RESULT_CHANGED = "result_changed"
    CANDIDATES_REMOVED = "candidates_removed"


class ResultHistoryState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ResultSelectionError(ValueError):
    """Selection metadata is unsafe, corrupt, unsupported, or inconsistent."""


@dataclass(frozen=True, slots=True)
class CandidateViewRow:
    candidate_id: str
    recording_id: str
    start_frame: int
    end_frame: int
    start_time_ns: int
    end_time_ns: int
    max_target_score: float
    contributing_windows: int
    refinement_status: RefinementStatus | None = None
    rf_target_score: float | None = None
    unscored_reason: str = ""

    @classmethod
    def from_candidate(cls, candidate: CandidateInterval) -> CandidateViewRow:
        return cls(
            candidate_id=candidate.candidate_id,
            recording_id=candidate.recording_ref,
            start_frame=candidate.start_frame,
            end_frame=candidate.end_frame,
            start_time_ns=candidate.start_time_ns,
            end_time_ns=candidate.end_time_ns,
            max_target_score=candidate.max_target_score,
            contributing_windows=candidate.contributing_windows,
        )

    @classmethod
    def from_refined_candidate(cls, candidate: RefinedCandidate) -> CandidateViewRow:
        return cls(
            candidate_id=candidate.candidate_id,
            recording_id=candidate.recording_ref,
            start_frame=candidate.start_frame,
            end_frame=candidate.end_frame,
            start_time_ns=candidate.start_time_ns,
            end_time_ns=candidate.end_time_ns,
            max_target_score=candidate.max_target_score,
            contributing_windows=candidate.contributing_windows,
            refinement_status=candidate.status,
            rf_target_score=candidate.rf_target_score,
            unscored_reason=candidate.unscored_reason,
        )


@dataclass(frozen=True, slots=True)
class RecordingViewRow:
    recording_id: str
    source_relative_name: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    outcome: FileOutcomeStatus
    error_code: str
    candidates: tuple[CandidateViewRow, ...]

    @classmethod
    def from_outcome(cls, outcome: RecordingOutcome) -> RecordingViewRow:
        return cls(
            recording_id=outcome.recording_ref,
            source_relative_name=outcome.recording_key,
            source_sha256=outcome.source_sha256,
            sample_rate_hz=outcome.sample_rate_hz,
            frame_count=outcome.frame_count,
            channels=outcome.channels,
            outcome=outcome.status,
            error_code=outcome.error_code,
            candidates=tuple(
                CandidateViewRow.from_candidate(candidate)
                for candidate in outcome.candidates
            ),
        )

    @classmethod
    def from_derived(cls, outcome: DerivedRecording) -> RecordingViewRow:
        return cls(
            recording_id=outcome.recording_ref,
            source_relative_name=outcome.recording_key,
            source_sha256=outcome.source_sha256,
            sample_rate_hz=outcome.sample_rate_hz,
            frame_count=outcome.frame_count,
            channels=outcome.channels,
            outcome=outcome.parent_status,
            error_code=outcome.parent_error_code,
            candidates=tuple(
                CandidateViewRow.from_refined_candidate(candidate)
                for candidate in outcome.candidates
            ),
        )


@dataclass(frozen=True, slots=True)
class ResultViewProjection:
    result_kind: str
    result_id: str
    result_digest: str
    run_id: str
    collection_id: str
    binding_revision: int
    inventory_id: str
    inventory_digest: str
    model_id: str
    model_snapshot_id: str
    completed_at: str
    content_state: ResultContentState
    source_state: ResultSourceState
    successful_files: int
    failed_files: int
    candidate_count: int
    score_semantics: str
    source_time_semantics: str
    recordings: tuple[RecordingViewRow, ...]
    parent_result_id: str | None
    parent_result_digest: str | None
    accepted_count: int | None
    rejected_count: int | None
    unscored_count: int | None
    threshold: float | None

    @property
    def provenance_visible(self) -> bool:
        return True

    @property
    def source_navigation_enabled(self) -> bool:
        return self.source_state is ResultSourceState.AVAILABLE

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.candidate_id
            for recording in self.recordings
            for candidate in recording.candidates
        )


@dataclass(frozen=True, slots=True)
class ResultHistoryItem:
    result_id: str
    run_id: str
    created_at: str
    state: ResultHistoryState
    result: ResultArtifact | None
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, ResultHistoryState):
            raise ValueError("Result history state is invalid.")
        if not isinstance(self.result_id, str) or _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("Result history ID is invalid.")
        if self.state is ResultHistoryState.AVAILABLE:
            if self.result is None or self.result.result_id != self.result_id:
                raise ValueError("Available Result history requires its immutable Result.")
            if self.message:
                raise ValueError("Available Result history cannot contain an error message.")
        elif self.result is not None or not self.message:
            raise ValueError("Unavailable Result history requires a visible error message.")

    @property
    def available(self) -> bool:
        return self.state is ResultHistoryState.AVAILABLE


def project_result(
    result: ResultArtifact,
    *,
    source_state: ResultSourceState,
) -> ResultViewProjection:
    """Copy only persisted immutable facts into a Qt-independent view contract."""
    if not isinstance(result, (DetectionResult, DerivedResult)):
        raise TypeError("Result projection requires a persisted scientific Result.")
    source_state = ResultSourceState(source_state)
    content_state = (
        ResultContentState.PARTIAL
        if result.failed_files
        else (
            ResultContentState.EMPTY
            if result.candidate_count == 0
            else ResultContentState.POPULATED
        )
    )
    return ResultViewProjection(
        result_kind="derived" if isinstance(result, DerivedResult) else "original",
        result_id=result.result_id,
        result_digest=result.result_digest,
        run_id=result.run_id,
        collection_id=result.collection_id,
        binding_revision=result.binding_revision,
        inventory_id=result.inventory_id,
        inventory_digest=result.inventory_digest,
        model_id=(
            result.rf_model_id if isinstance(result, DerivedResult) else result.model_id
        ),
        model_snapshot_id=(
            result.rf_model_snapshot_id
            if isinstance(result, DerivedResult)
            else result.model_snapshot_id
        ),
        completed_at=result.completed_at,
        content_state=content_state,
        source_state=source_state,
        successful_files=result.successful_files,
        failed_files=result.failed_files,
        candidate_count=result.candidate_count,
        score_semantics=result.score_semantics,
        source_time_semantics=result.source_time_semantics,
        recordings=tuple(
            (
                RecordingViewRow.from_derived(recording)
                if isinstance(recording, DerivedRecording)
                else RecordingViewRow.from_outcome(recording)
            )
            for recording in result.recordings
        ),
        parent_result_id=(
            result.parent_result_id if isinstance(result, DerivedResult) else None
        ),
        parent_result_digest=(
            result.parent_result_digest if isinstance(result, DerivedResult) else None
        ),
        accepted_count=(
            result.accepted_count if isinstance(result, DerivedResult) else None
        ),
        rejected_count=(
            result.rejected_count if isinstance(result, DerivedResult) else None
        ),
        unscored_count=(
            result.unscored_count if isinstance(result, DerivedResult) else None
        ),
        threshold=result.threshold if isinstance(result, DerivedResult) else None,
    )


@dataclass(frozen=True, slots=True)
class ResultSelection:
    schema_version: int
    result_id: str
    result_digest: str
    selection_revision: int
    candidate_ids: tuple[str, ...]
    updated_at: str

    def __post_init__(self) -> None:
        if self.schema_version != RESULT_SELECTION_SCHEMA_VERSION:
            raise ResultSelectionError("Unsupported Result selection schema.")
        if not isinstance(self.result_id, str) or _RESULT_ID.fullmatch(self.result_id) is None:
            raise ResultSelectionError("Result selection Result ID is invalid.")
        if (
            not isinstance(self.result_digest, str)
            or _SHA256.fullmatch(self.result_digest) is None
        ):
            raise ResultSelectionError("Result selection digest is invalid.")
        if type(self.selection_revision) is not int or self.selection_revision < 0:
            raise ResultSelectionError("Result selection revision is invalid.")
        if len(self.candidate_ids) > MAX_SELECTED_CANDIDATES:
            raise ResultSelectionError("Result selection exceeds its candidate limit.")
        if (
            any(
                not isinstance(candidate_id, str)
                or _CANDIDATE_ID.fullmatch(candidate_id) is None
                for candidate_id in self.candidate_ids
            )
            or len(self.candidate_ids) != len(set(self.candidate_ids))
        ):
            raise ResultSelectionError("Result selection candidate IDs are invalid.")
        if not isinstance(self.updated_at, str) or not self.updated_at.endswith("Z"):
            raise ResultSelectionError("Result selection timestamp must be UTC.")

    @classmethod
    def empty(cls, result: ResultArtifact) -> ResultSelection:
        return cls(
            RESULT_SELECTION_SCHEMA_VERSION,
            result.result_id,
            result.result_digest,
            0,
            (),
            utc_now(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "selection_revision": self.selection_revision,
            "candidate_ids": list(self.candidate_ids),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ResultSelection:
        expected = {
            "schema_version",
            "result_id",
            "result_digest",
            "selection_revision",
            "candidate_ids",
            "updated_at",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw.get("candidate_ids"), list)
        ):
            raise ResultSelectionError("Result selection document is invalid.")
        values = dict(raw)
        values["candidate_ids"] = tuple(raw["candidate_ids"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ResolvedResultSelection:
    selection: ResultSelection
    reconciliation: SelectionReconciliation
    message: str


@dataclass(frozen=True, slots=True)
class FrozenResultSelection:
    """Versioned ST-09/ST-10 handoff; consumers freeze it only when their work begins."""

    schema_version: int
    result_id: str
    result_digest: str
    result_kind: str
    parent_result_id: str | None
    parent_result_digest: str | None
    selection_revision: int
    candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FROZEN_RESULT_SELECTION_SCHEMA_VERSION:
            raise ResultSelectionError("Unsupported frozen Result selection schema.")
        if not isinstance(self.result_id, str) or _RESULT_ID.fullmatch(self.result_id) is None:
            raise ResultSelectionError("Frozen Result selection ID is invalid.")
        if (
            not isinstance(self.result_digest, str)
            or _SHA256.fullmatch(self.result_digest) is None
        ):
            raise ResultSelectionError("Frozen Result selection digest is invalid.")
        if self.result_kind not in {"original", "derived"}:
            raise ResultSelectionError("Frozen Result selection kind is invalid.")
        if self.result_kind == "original":
            if self.parent_result_id is not None or self.parent_result_digest is not None:
                raise ResultSelectionError("Original Result selection cannot contain lineage.")
        elif (
            not isinstance(self.parent_result_id, str)
            or _RESULT_ID.fullmatch(self.parent_result_id) is None
            or not isinstance(self.parent_result_digest, str)
            or _SHA256.fullmatch(self.parent_result_digest) is None
        ):
            raise ResultSelectionError("Derived Result selection requires parent lineage.")
        if type(self.selection_revision) is not int or self.selection_revision < 0:
            raise ResultSelectionError("Frozen Result selection revision is invalid.")
        if (
            len(self.candidate_ids) > MAX_SELECTED_CANDIDATES
            or any(
                not isinstance(candidate_id, str)
                or _CANDIDATE_ID.fullmatch(candidate_id) is None
                for candidate_id in self.candidate_ids
            )
            or len(self.candidate_ids) != len(set(self.candidate_ids))
        ):
            raise ResultSelectionError("Frozen Result selection candidate IDs are invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "result_kind": self.result_kind,
            "parent_result_id": self.parent_result_id,
            "parent_result_digest": self.parent_result_digest,
            "selection_revision": self.selection_revision,
            "candidate_ids": list(self.candidate_ids),
        }

    @classmethod
    def from_dict(cls, raw: object) -> FrozenResultSelection:
        expected = {
            "schema_version",
            "result_id",
            "result_digest",
            "result_kind",
            "parent_result_id",
            "parent_result_digest",
            "selection_revision",
            "candidate_ids",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw.get("candidate_ids"), list)
        ):
            raise ResultSelectionError("Frozen Result selection document is invalid.")
        values = dict(raw)
        values["candidate_ids"] = tuple(raw["candidate_ids"])
        return cls(**values)


def _ordered_candidate_ids(
    result: ResultArtifact, candidate_ids: tuple[str, ...] | list[str] | set[str]
) -> tuple[str, ...]:
    requested = tuple(candidate_ids)
    if len(requested) != len(set(requested)):
        raise ResultSelectionError("Result selection contains duplicate candidate IDs.")
    requested_set = set(requested)
    result_ids = tuple(
        candidate.candidate_id
        for recording in result.recordings
        for candidate in recording.candidates
    )
    unknown = requested_set.difference(result_ids)
    if unknown:
        raise ResultSelectionError("Result selection refers to an unknown candidate ID.")
    return tuple(candidate_id for candidate_id in result_ids if candidate_id in requested_set)


def freeze_result_selection(
    result: ResultArtifact, selection: ResultSelection
) -> FrozenResultSelection:
    if (
        selection.result_id != result.result_id
        or selection.result_digest != result.result_digest
    ):
        raise ResultSelectionError("Result selection does not match the immutable Result.")
    ordered = _ordered_candidate_ids(result, selection.candidate_ids)
    return FrozenResultSelection(
        FROZEN_RESULT_SELECTION_SCHEMA_VERSION,
        result.result_id,
        result.result_digest,
        "derived" if isinstance(result, DerivedResult) else "original",
        result.parent_result_id if isinstance(result, DerivedResult) else None,
        result.parent_result_digest if isinstance(result, DerivedResult) else None,
        selection.selection_revision,
        ordered,
    )


class ResultSelectionStore:
    """Atomic mutable selection metadata kept beside, never inside, Results."""

    def __init__(self, collection_root: Path):
        root = Path(collection_root)
        if root.is_symlink() or not root.is_dir():
            raise ResultSelectionError("Detect Collection metadata root is missing or unsafe.")
        self.collection_root = root.resolve(strict=True)
        self.selection_root = self.collection_root / "result-selections"

    def _ensure_root(self) -> None:
        if self.selection_root.is_symlink():
            raise ResultSelectionError("Result selection storage cannot be a symlink.")
        if self.selection_root.exists() and not self.selection_root.is_dir():
            raise ResultSelectionError("Result selection storage must be a directory.")
        self.selection_root.mkdir(mode=0o700, exist_ok=True)
        self.selection_root.chmod(0o700)

    def path_for(self, result_id: str) -> Path:
        if not isinstance(result_id, str) or _RESULT_ID.fullmatch(result_id) is None:
            raise ResultSelectionError("Result selection Result ID is invalid.")
        return self.selection_root / f"{result_id}.json"

    def _load(self, result_id: str) -> ResultSelection | None:
        if self.selection_root.is_symlink() or (
            self.selection_root.exists() and not self.selection_root.is_dir()
        ):
            raise ResultSelectionError("Result selection storage is unsafe.")
        path = self.path_for(result_id)
        if not path.exists() and not path.is_symlink():
            return None
        if path.is_symlink() or not path.is_file():
            raise ResultSelectionError("Result selection document is missing or unsafe.")
        try:
            if path.stat().st_size > MAX_SELECTION_BYTES:
                raise ResultSelectionError("Result selection document exceeds 1 MiB.")
            raw = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResultSelectionError("Result selection document is corrupt.") from exc
        selection = ResultSelection.from_dict(raw)
        if selection.result_id != result_id:
            raise ResultSelectionError("Result selection filename and Result ID disagree.")
        return selection

    def _write(self, selection: ResultSelection) -> None:
        self._ensure_root()
        path = self.path_for(selection.result_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ResultSelectionError("Result selection document path is unsafe.")
        payload = (
            json.dumps(selection.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if len(payload) > MAX_SELECTION_BYTES:
            raise ResultSelectionError("Result selection document exceeds 1 MiB.")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.selection_root,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
            try:
                descriptor = os.open(self.selection_root, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                pass
        except OSError as exc:
            raise ResultSelectionError("Result selection could not be saved.") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, result: ResultArtifact) -> ResolvedResultSelection:
        stored = self._load(result.result_id)
        if stored is None:
            return ResolvedResultSelection(
                ResultSelection.empty(result), SelectionReconciliation.CURRENT, ""
            )
        if stored.result_digest != result.result_digest:
            selection = ResultSelection(
                RESULT_SELECTION_SCHEMA_VERSION,
                result.result_id,
                result.result_digest,
                stored.selection_revision + 1,
                (),
                utc_now(),
            )
            self._write(selection)
            return ResolvedResultSelection(
                selection,
                SelectionReconciliation.RESULT_CHANGED,
                "Saved selections were cleared because the Result contents changed.",
            )
        valid_ids = set(
            candidate.candidate_id
            for recording in result.recordings
            for candidate in recording.candidates
        )
        retained = tuple(
            candidate_id
            for candidate_id in stored.candidate_ids
            if candidate_id in valid_ids
        )
        if retained != stored.candidate_ids:
            selection = ResultSelection(
                RESULT_SELECTION_SCHEMA_VERSION,
                result.result_id,
                result.result_digest,
                stored.selection_revision + 1,
                retained,
                utc_now(),
            )
            self._write(selection)
            return ResolvedResultSelection(
                selection,
                SelectionReconciliation.CANDIDATES_REMOVED,
                "Selections that no longer exist in this Result were removed.",
            )
        return ResolvedResultSelection(stored, SelectionReconciliation.CURRENT, "")

    def replace(
        self,
        result: ResultArtifact,
        candidate_ids: tuple[str, ...] | list[str] | set[str],
    ) -> ResultSelection:
        ordered = _ordered_candidate_ids(result, candidate_ids)
        resolved = self.read(result)
        selection = ResultSelection(
            RESULT_SELECTION_SCHEMA_VERSION,
            result.result_id,
            result.result_digest,
            resolved.selection.selection_revision + 1,
            ordered,
            utc_now(),
        )
        self._write(selection)
        return selection


__all__ = [
    "CandidateViewRow",
    "FrozenResultSelection",
    "RecordingViewRow",
    "ResolvedResultSelection",
    "ResultContentState",
    "ResultHistoryItem",
    "ResultHistoryState",
    "ResultSelection",
    "ResultSelectionError",
    "ResultSelectionStore",
    "ResultSourceState",
    "ResultViewProjection",
    "SelectionReconciliation",
    "freeze_result_selection",
    "project_result",
]
