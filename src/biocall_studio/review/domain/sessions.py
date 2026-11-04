"""Pure Review session, annotation, settings, and finalization contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeAlias

from biocall_studio.review.domain.intake import (
    EligibleCandidate,
    ReviewIntakeManifest,
    ReviewIntakeProjection,
    ReviewRecording,
    ReviewResultKind,
)

REVIEW_SESSION_SCHEMA_VERSION = 1
SPECTROGRAM_SETTINGS_SCHEMA_VERSION = 1
FINALIZATION_SCHEMA_VERSION = 1
DEFAULT_PRESET_ID = "rsp_" + "0" * 32

_SESSION_ID = re.compile(r"rsn_[0-9a-f]{32}")
_PRESET_ID = re.compile(r"rsp_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_NAME_LENGTH = 120
_MAX_SETTINGS_BYTES = 65_536
_MAX_JSON_DEPTH = 8

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ReviewRevisionConflict(RuntimeError):
    """The caller acted on a stale immutable revision."""


class ReviewSessionState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    FINALIZED = "finalized"


class ReviewLabel(StrEnum):
    UNREVIEWED = "unreviewed"
    CALL = "call"
    NOT_CALL = "not_call"


class DecisionOrigin(StrEnum):
    INDIVIDUAL = "individual"
    BULK = "bulk"


def validate_session_id(value: object) -> str:
    if not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None:
        raise ValueError("Review session ID is invalid.")
    return value


def validate_preset_id(value: object) -> str:
    if not isinstance(value, str) or _PRESET_ID.fullmatch(value) is None:
        raise ValueError("Spectrogram preset ID is invalid.")
    return value


def validate_candidate_id(value: object) -> str:
    if not isinstance(value, str) or _CANDIDATE_ID.fullmatch(value) is None:
        raise ValueError("Review candidate ID is invalid.")
    return value


def validate_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} digest is invalid.")
    return value


def validate_timestamp(value: object, label: str = "Review timestamp") -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} is invalid.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} is invalid.") from exc
    if parsed.tzinfo != UTC:
        raise ValueError(f"{label} is invalid.")
    return value


def validate_display_name(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid.")
    normalized = " ".join(value.split())
    if (
        normalized != value
        or not normalized
        or len(normalized) > _MAX_NAME_LENGTH
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError(f"{label} is invalid.")
    return value


def _validated_json(value: object, *, depth: int = 0) -> JsonValue:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("Spectrogram settings are nested too deeply.")
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Spectrogram settings contain a non-finite value.")
        return value
    if isinstance(value, list):
        return [_validated_json(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) and key for key in value):
            raise ValueError("Spectrogram setting names are invalid.")
        return {key: _validated_json(item, depth=depth + 1) for key, item in sorted(value.items())}
    raise ValueError("Spectrogram settings must contain only portable JSON values.")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_payload(prefix: bytes, value: object) -> str:
    digest = hashlib.sha256(prefix)
    digest.update(_canonical_json(value).encode("utf-8"))
    digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SpectrogramSettingsSnapshot:
    schema_version: int
    preset_id: str
    preset_name: str
    preset_revision: int
    algorithm_version: str
    render_version: str
    effective_settings_json: str
    settings_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != SPECTROGRAM_SETTINGS_SCHEMA_VERSION:
            raise ValueError("Unsupported spectrogram settings schema.")
        validate_preset_id(self.preset_id)
        validate_display_name(self.preset_name, "Spectrogram preset name")
        if type(self.preset_revision) is not int or self.preset_revision < 1:
            raise ValueError("Spectrogram preset revision is invalid.")
        for value, label in (
            (self.algorithm_version, "Spectrogram algorithm version"),
            (self.render_version, "Spectrogram render version"),
        ):
            if not isinstance(value, str) or not value or len(value) > 200:
                raise ValueError(f"{label} is invalid.")
        if not isinstance(self.effective_settings_json, str):
            raise ValueError("Spectrogram settings document is invalid.")
        try:
            settings = _validated_json(json.loads(self.effective_settings_json))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Spectrogram settings document is invalid.") from exc
        if not isinstance(settings, dict) or not settings:
            raise ValueError("Spectrogram settings must be a non-empty object.")
        canonical = _canonical_json(settings)
        if (
            canonical != self.effective_settings_json
            or len(canonical.encode()) > _MAX_SETTINGS_BYTES
        ):
            raise ValueError("Spectrogram settings document is not canonical or is too large.")
        expected = _digest_payload(
            b"biocall-review-spectrogram-settings-v1\n", self.unsigned_dict()
        )
        if self.settings_digest != expected:
            raise ValueError("Spectrogram settings digest does not match its snapshot.")

    @property
    def effective_settings(self) -> dict[str, JsonValue]:
        value = json.loads(self.effective_settings_json)
        if not isinstance(value, dict):
            raise AssertionError("Validated settings stopped being an object.")
        return value

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "preset_id": self.preset_id,
            "preset_name": self.preset_name,
            "preset_revision": self.preset_revision,
            "algorithm_version": self.algorithm_version,
            "render_version": self.render_version,
            "effective_settings": self.effective_settings,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "settings_digest": self.settings_digest}

    @classmethod
    def create(
        cls,
        *,
        preset_id: str,
        preset_name: str,
        preset_revision: int,
        algorithm_version: str,
        render_version: str,
        effective_settings: object,
    ) -> SpectrogramSettingsSnapshot:
        settings = _validated_json(effective_settings)
        if not isinstance(settings, dict) or not settings:
            raise ValueError("Spectrogram settings must be a non-empty object.")
        unsigned = {
            "schema_version": SPECTROGRAM_SETTINGS_SCHEMA_VERSION,
            "preset_id": preset_id,
            "preset_name": preset_name,
            "preset_revision": preset_revision,
            "algorithm_version": algorithm_version,
            "render_version": render_version,
            "effective_settings": settings,
        }
        return cls(
            schema_version=SPECTROGRAM_SETTINGS_SCHEMA_VERSION,
            preset_id=preset_id,
            preset_name=preset_name,
            preset_revision=preset_revision,
            algorithm_version=algorithm_version,
            render_version=render_version,
            effective_settings_json=_canonical_json(settings),
            settings_digest=_digest_payload(b"biocall-review-spectrogram-settings-v1\n", unsigned),
        )

    @classmethod
    def from_dict(cls, raw: object) -> SpectrogramSettingsSnapshot:
        expected = {
            "schema_version",
            "preset_id",
            "preset_name",
            "preset_revision",
            "algorithm_version",
            "render_version",
            "effective_settings",
            "settings_digest",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Spectrogram settings snapshot is invalid.")
        settings = _validated_json(raw["effective_settings"])
        return cls(
            schema_version=raw["schema_version"],
            preset_id=raw["preset_id"],
            preset_name=raw["preset_name"],
            preset_revision=raw["preset_revision"],
            algorithm_version=raw["algorithm_version"],
            render_version=raw["render_version"],
            effective_settings_json=_canonical_json(settings),
            settings_digest=raw["settings_digest"],
        )


def _manifest_from_dict(raw: object) -> ReviewIntakeManifest:
    if not isinstance(raw, dict):
        raise ValueError("Review source manifest is invalid.")
    values = dict(raw)
    try:
        values["result_kind"] = ReviewResultKind(values["result_kind"])
        return ReviewIntakeManifest(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Review source manifest is invalid.") from exc


@dataclass(frozen=True, slots=True)
class ReviewSessionSource:
    schema_version: int
    manifest_json: str
    recordings_json: str
    score_semantics: str
    eligibility_threshold: float
    parent_score_semantics: str | None
    parent_eligibility_threshold: float | None
    source_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_SESSION_SCHEMA_VERSION:
            raise ValueError("Unsupported Review session source schema.")
        try:
            manifest_raw = json.loads(self.manifest_json)
            recordings_raw = json.loads(self.recordings_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Review session source document is invalid.") from exc
        manifest = _manifest_from_dict(manifest_raw)
        if not isinstance(recordings_raw, list) or len(recordings_raw) != manifest.recording_count:
            raise ValueError("Review session recording identities are invalid.")
        recordings = tuple(ReviewRecording(**row) for row in recordings_raw)
        if tuple(row.ordinal for row in recordings) != tuple(range(len(recordings))):
            raise ValueError("Review session recordings are not in canonical order.")
        if not isinstance(self.score_semantics, str) or not self.score_semantics:
            raise ValueError("Review score semantics are invalid.")
        if (
            not isinstance(self.eligibility_threshold, (int, float))
            or isinstance(self.eligibility_threshold, bool)
            or not math.isfinite(self.eligibility_threshold)
            or not 0 <= self.eligibility_threshold <= 1
        ):
            raise ValueError("Review eligibility threshold is invalid.")
        if (self.parent_score_semantics is None) != (
            self.parent_eligibility_threshold is None
        ):
            raise ValueError("Review parent score provenance is incomplete.")
        if self.parent_score_semantics is not None and (
            not isinstance(self.parent_score_semantics, str)
            or not self.parent_score_semantics
            or not isinstance(self.parent_eligibility_threshold, (int, float))
            or isinstance(self.parent_eligibility_threshold, bool)
            or not math.isfinite(self.parent_eligibility_threshold)
            or not 0 <= self.parent_eligibility_threshold <= 1
        ):
            raise ValueError("Review parent score provenance is invalid.")
        if self.manifest.result_kind is ReviewResultKind.CNN and (
            self.parent_score_semantics is not None
        ):
            raise ValueError("A CNN Review source cannot contain parent score provenance.")
        if self.manifest.result_kind is ReviewResultKind.RF and (
            self.parent_score_semantics is None
        ):
            raise ValueError("An RF Review source requires parent score provenance.")
        if self.manifest_json != _canonical_json(
            manifest.to_dict()
        ) or self.recordings_json != _canonical_json([row.to_dict() for row in recordings]):
            raise ValueError("Review session source document is not canonical.")
        expected = _digest_payload(b"biocall-review-session-source-v1\n", self.unsigned_dict())
        if self.source_digest != expected:
            raise ValueError("Review session source digest does not match.")

    @property
    def manifest(self) -> ReviewIntakeManifest:
        return _manifest_from_dict(json.loads(self.manifest_json))

    @property
    def recordings(self) -> tuple[ReviewRecording, ...]:
        raw = json.loads(self.recordings_json)
        return tuple(ReviewRecording(**row) for row in raw)

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest": self.manifest.to_dict(),
            "recordings": [row.to_dict() for row in self.recordings],
            "score_semantics": self.score_semantics,
            "eligibility_threshold": float(self.eligibility_threshold),
            "parent_score_semantics": self.parent_score_semantics,
            "parent_eligibility_threshold": self.parent_eligibility_threshold,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "source_digest": self.source_digest}

    @classmethod
    def from_projection(
        cls,
        projection: ReviewIntakeProjection,
        *,
        score_semantics: str,
        eligibility_threshold: float,
        parent_score_semantics: str | None = None,
        parent_eligibility_threshold: float | None = None,
    ) -> ReviewSessionSource:
        unsigned = {
            "schema_version": REVIEW_SESSION_SCHEMA_VERSION,
            "manifest": projection.manifest.to_dict(),
            "recordings": [row.to_dict() for row in projection.recordings],
            "score_semantics": score_semantics,
            "eligibility_threshold": float(eligibility_threshold),
            "parent_score_semantics": parent_score_semantics,
            "parent_eligibility_threshold": parent_eligibility_threshold,
        }
        return cls(
            schema_version=REVIEW_SESSION_SCHEMA_VERSION,
            manifest_json=_canonical_json(unsigned["manifest"]),
            recordings_json=_canonical_json(unsigned["recordings"]),
            score_semantics=score_semantics,
            eligibility_threshold=float(eligibility_threshold),
            parent_score_semantics=parent_score_semantics,
            parent_eligibility_threshold=parent_eligibility_threshold,
            source_digest=_digest_payload(b"biocall-review-session-source-v1\n", unsigned),
        )

    @classmethod
    def from_dict(cls, raw: object) -> ReviewSessionSource:
        expected = {
            "schema_version",
            "manifest",
            "recordings",
            "score_semantics",
            "eligibility_threshold",
            "parent_score_semantics",
            "parent_eligibility_threshold",
            "source_digest",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Review session source snapshot is invalid.")
        return cls(
            schema_version=raw["schema_version"],
            manifest_json=_canonical_json(raw["manifest"]),
            recordings_json=_canonical_json(raw["recordings"]),
            score_semantics=raw["score_semantics"],
            eligibility_threshold=raw["eligibility_threshold"],
            parent_score_semantics=raw["parent_score_semantics"],
            parent_eligibility_threshold=raw["parent_eligibility_threshold"],
            source_digest=raw["source_digest"],
        )


def propose_session_name(result_kind: ReviewResultKind) -> str:
    if result_kind is ReviewResultKind.CNN:
        return "Review of detected calls"
    if result_kind is ReviewResultKind.RF:
        return "Review of refined detections"
    raise ValueError("Review Result kind is invalid.")


@dataclass(frozen=True, slots=True)
class HumanDecision:
    candidate_id: str
    label: ReviewLabel
    origin: DecisionOrigin
    modified_at: str

    def __post_init__(self) -> None:
        validate_candidate_id(self.candidate_id)
        if self.label is ReviewLabel.UNREVIEWED:
            raise ValueError("Unreviewed is represented by the absence of a human decision.")
        if not isinstance(self.origin, DecisionOrigin):
            raise ValueError("Review decision origin is invalid.")
        validate_timestamp(self.modified_at, "Review decision timestamp")


@dataclass(frozen=True, slots=True)
class AnnotationChange:
    candidate_id: str
    before: HumanDecision | None
    after: HumanDecision | None

    def __post_init__(self) -> None:
        validate_candidate_id(self.candidate_id)
        if self.before is not None and self.before.candidate_id != self.candidate_id:
            raise ValueError("Review change prior decision is inconsistent.")
        if self.after is not None and self.after.candidate_id != self.candidate_id:
            raise ValueError("Review change new decision is inconsistent.")
        if self.before == self.after:
            raise ValueError("Review change must alter a decision.")


@dataclass(frozen=True, slots=True)
class AnnotationOperation:
    kind: str
    changes: tuple[AnnotationChange, ...]

    def __post_init__(self) -> None:
        if self.kind not in {"individual", "accept_all"}:
            raise ValueError("Review annotation operation kind is invalid.")
        if len({change.candidate_id for change in self.changes}) != len(self.changes):
            raise ValueError("Review annotation operation repeats a candidate.")

    @property
    def changed_count(self) -> int:
        return len(self.changes)


@dataclass(frozen=True, slots=True)
class AnnotationBook:
    eligible_candidate_ids: tuple[str, ...]
    decisions: tuple[HumanDecision, ...]
    revision: int

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("Review annotation revision is invalid.")
        for candidate_id in self.eligible_candidate_ids:
            validate_candidate_id(candidate_id)
        if len(set(self.eligible_candidate_ids)) != len(self.eligible_candidate_ids):
            raise ValueError("Review eligibility repeats a candidate.")
        by_id = {decision.candidate_id: decision for decision in self.decisions}
        if len(by_id) != len(self.decisions) or not set(by_id).issubset(
            self.eligible_candidate_ids
        ):
            raise ValueError("Review decisions do not match frozen eligibility.")
        order = {
            candidate_id: index for index, candidate_id in enumerate(self.eligible_candidate_ids)
        }
        if self.decisions != tuple(sorted(self.decisions, key=lambda row: order[row.candidate_id])):
            raise ValueError("Review decisions are not in eligibility order.")

    @classmethod
    def create(cls, candidate_ids: tuple[str, ...]) -> AnnotationBook:
        return cls(tuple(candidate_ids), (), 0)

    def _mapping(self) -> dict[str, HumanDecision]:
        return {decision.candidate_id: decision for decision in self.decisions}

    def _replace(self, decisions: dict[str, HumanDecision], *, revision: int) -> AnnotationBook:
        return AnnotationBook(
            self.eligible_candidate_ids,
            tuple(
                decisions[candidate_id]
                for candidate_id in self.eligible_candidate_ids
                if candidate_id in decisions
            ),
            revision,
        )

    def _expect_revision(self, expected_revision: int) -> None:
        if expected_revision != self.revision:
            raise ReviewRevisionConflict("Review annotation revision changed.")

    def decision(self, candidate_id: str) -> HumanDecision:
        try:
            return self._mapping()[candidate_id]
        except KeyError as exc:
            raise KeyError("Candidate has no human decision.") from exc

    def label_for(self, candidate_id: str) -> ReviewLabel:
        if candidate_id not in self.eligible_candidate_ids:
            raise KeyError("Candidate is not eligible for this Review session.")
        decision = self._mapping().get(candidate_id)
        return ReviewLabel.UNREVIEWED if decision is None else decision.label

    def set_label(
        self,
        candidate_id: str,
        label: ReviewLabel,
        *,
        expected_revision: int,
        modified_at: str,
    ) -> tuple[AnnotationBook, AnnotationOperation]:
        self._expect_revision(expected_revision)
        if candidate_id not in self.eligible_candidate_ids:
            raise KeyError("Candidate is not eligible for this Review session.")
        if not isinstance(label, ReviewLabel):
            raise ValueError("Review label is invalid.")
        validate_timestamp(modified_at, "Review decision timestamp")
        decisions = self._mapping()
        before = decisions.get(candidate_id)
        after = (
            None
            if label is ReviewLabel.UNREVIEWED
            else HumanDecision(candidate_id, label, DecisionOrigin.INDIVIDUAL, modified_at)
        )
        if before == after:
            return self, AnnotationOperation("individual", ())
        if after is None:
            decisions.pop(candidate_id, None)
        else:
            decisions[candidate_id] = after
        operation = AnnotationOperation(
            "individual", (AnnotationChange(candidate_id, before, after),)
        )
        return self._replace(decisions, revision=self.revision + 1), operation

    def accept_all(
        self, *, expected_revision: int, modified_at: str
    ) -> tuple[AnnotationBook, AnnotationOperation]:
        self._expect_revision(expected_revision)
        validate_timestamp(modified_at, "Review decision timestamp")
        decisions = self._mapping()
        changes = tuple(
            AnnotationChange(
                candidate_id,
                None,
                HumanDecision(
                    candidate_id,
                    ReviewLabel.CALL,
                    DecisionOrigin.BULK,
                    modified_at,
                ),
            )
            for candidate_id in self.eligible_candidate_ids
            if candidate_id not in decisions
        )
        for change in changes:
            if change.after is None:
                raise AssertionError("Bulk acceptance lost its decision.")
            decisions[change.candidate_id] = change.after
        operation = AnnotationOperation("accept_all", changes)
        revision = self.revision + (1 if changes else 0)
        return self._replace(decisions, revision=revision), operation

    def _apply_operation(
        self,
        operation: AnnotationOperation,
        *,
        forward: bool,
        expected_revision: int,
    ) -> AnnotationBook:
        self._expect_revision(expected_revision)
        decisions = self._mapping()
        for change in operation.changes:
            expected = change.before if forward else change.after
            replacement = change.after if forward else change.before
            if decisions.get(change.candidate_id) != expected:
                raise ReviewRevisionConflict("Review annotation history is no longer applicable.")
            if replacement is None:
                decisions.pop(change.candidate_id, None)
            else:
                decisions[change.candidate_id] = replacement
        return self._replace(decisions, revision=self.revision + 1)

    def undo(self, operation: AnnotationOperation, *, expected_revision: int) -> AnnotationBook:
        return self._apply_operation(operation, forward=False, expected_revision=expected_revision)

    def redo(self, operation: AnnotationOperation, *, expected_revision: int) -> AnnotationBook:
        return self._apply_operation(operation, forward=True, expected_revision=expected_revision)


def require_session_transition(current: ReviewSessionState, target: ReviewSessionState) -> None:
    allowed = {
        ReviewSessionState.OPEN: {ReviewSessionState.CLOSED, ReviewSessionState.FINALIZED},
        ReviewSessionState.CLOSED: {ReviewSessionState.OPEN},
        ReviewSessionState.FINALIZED: set(),
    }
    if not isinstance(current, ReviewSessionState) or not isinstance(target, ReviewSessionState):
        raise ValueError("Review session state is invalid.")
    if target not in allowed[current]:
        if current is ReviewSessionState.FINALIZED:
            raise ValueError("A Finalized Review session is immutable.")
        raise ValueError(
            f"Review session cannot transition from {current.value} to {target.value}."
        )


@dataclass(frozen=True, slots=True)
class FinalizedCandidateDecision:
    ordinal: int
    candidate_id: str
    label: ReviewLabel
    origin: DecisionOrigin | None
    modified_at: str | None

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("Finalized candidate order is invalid.")
        validate_candidate_id(self.candidate_id)
        if not isinstance(self.label, ReviewLabel):
            raise ValueError("Finalized Review label is invalid.")
        if self.label is ReviewLabel.UNREVIEWED:
            if self.origin is not None or self.modified_at is not None:
                raise ValueError("Unreviewed candidates cannot have human decision metadata.")
        elif not isinstance(self.origin, DecisionOrigin) or self.modified_at is None:
            raise ValueError("Human decisions require an origin and timestamp.")
        if self.modified_at is not None:
            validate_timestamp(self.modified_at, "Finalized decision timestamp")

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "candidate_id": self.candidate_id,
            "label": self.label.value,
            "origin": None if self.origin is None else self.origin.value,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, raw: object) -> FinalizedCandidateDecision:
        expected = {"ordinal", "candidate_id", "label", "origin", "modified_at"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Finalized Review decision is invalid.")
        return cls(
            ordinal=raw["ordinal"],
            candidate_id=raw["candidate_id"],
            label=ReviewLabel(raw["label"]),
            origin=None if raw["origin"] is None else DecisionOrigin(raw["origin"]),
            modified_at=raw["modified_at"],
        )


@dataclass(frozen=True, slots=True)
class ReviewFinalizationSnapshot:
    schema_version: int
    session_id: str
    session_name: str
    source_digest: str
    settings: SpectrogramSettingsSnapshot
    parent_session_id: str | None
    parent_snapshot_digest: str | None
    finalized_at: str
    candidates: tuple[FinalizedCandidateDecision, ...]
    call_count: int
    not_call_count: int
    unreviewed_count: int
    snapshot_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != FINALIZATION_SCHEMA_VERSION:
            raise ValueError("Unsupported Review finalization schema.")
        validate_session_id(self.session_id)
        validate_display_name(self.session_name, "Review session name")
        validate_digest(self.source_digest, "Review source")
        if not isinstance(self.settings, SpectrogramSettingsSnapshot):
            raise ValueError("Review finalization settings are invalid.")
        if self.parent_session_id is None:
            if self.parent_snapshot_digest is not None:
                raise ValueError("Review parent snapshot lineage is incomplete.")
        else:
            validate_session_id(self.parent_session_id)
            validate_digest(self.parent_snapshot_digest, "Review parent snapshot")
        validate_timestamp(self.finalized_at, "Review finalization timestamp")
        if tuple(row.ordinal for row in self.candidates) != tuple(range(len(self.candidates))):
            raise ValueError("Finalized Review candidates are not in canonical order.")
        if len({row.candidate_id for row in self.candidates}) != len(self.candidates):
            raise ValueError("Finalized Review candidates are not unique.")
        counts = (
            sum(row.label is ReviewLabel.CALL for row in self.candidates),
            sum(row.label is ReviewLabel.NOT_CALL for row in self.candidates),
            sum(row.label is ReviewLabel.UNREVIEWED for row in self.candidates),
        )
        if counts != (self.call_count, self.not_call_count, self.unreviewed_count):
            raise ValueError("Review finalization counts do not match its decisions.")
        expected = _digest_payload(b"biocall-review-finalization-v1\n", self.unsigned_dict())
        if self.snapshot_digest != expected:
            raise ValueError("Review finalization snapshot digest does not match.")

    @property
    def partial(self) -> bool:
        return self.unreviewed_count > 0

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "session_name": self.session_name,
            "source_digest": self.source_digest,
            "settings": self.settings.to_dict(),
            "parent_session_id": self.parent_session_id,
            "parent_snapshot_digest": self.parent_snapshot_digest,
            "finalized_at": self.finalized_at,
            "candidates": [row.to_dict() for row in self.candidates],
            "call_count": self.call_count,
            "not_call_count": self.not_call_count,
            "unreviewed_count": self.unreviewed_count,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "snapshot_digest": self.snapshot_digest}

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        session_name: str,
        source_digest: str,
        settings: SpectrogramSettingsSnapshot,
        parent_session_id: str | None,
        parent_snapshot_digest: str | None,
        finalized_at: str,
        candidates: tuple[FinalizedCandidateDecision, ...],
    ) -> ReviewFinalizationSnapshot:
        call_count = sum(row.label is ReviewLabel.CALL for row in candidates)
        not_call_count = sum(row.label is ReviewLabel.NOT_CALL for row in candidates)
        unreviewed_count = sum(row.label is ReviewLabel.UNREVIEWED for row in candidates)
        unsigned = {
            "schema_version": FINALIZATION_SCHEMA_VERSION,
            "session_id": session_id,
            "session_name": session_name,
            "source_digest": source_digest,
            "settings": settings.to_dict(),
            "parent_session_id": parent_session_id,
            "parent_snapshot_digest": parent_snapshot_digest,
            "finalized_at": finalized_at,
            "candidates": [row.to_dict() for row in candidates],
            "call_count": call_count,
            "not_call_count": not_call_count,
            "unreviewed_count": unreviewed_count,
        }
        return cls(
            schema_version=FINALIZATION_SCHEMA_VERSION,
            session_id=session_id,
            session_name=session_name,
            source_digest=source_digest,
            settings=settings,
            parent_session_id=parent_session_id,
            parent_snapshot_digest=parent_snapshot_digest,
            finalized_at=finalized_at,
            candidates=candidates,
            call_count=call_count,
            not_call_count=not_call_count,
            unreviewed_count=unreviewed_count,
            snapshot_digest=_digest_payload(b"biocall-review-finalization-v1\n", unsigned),
        )

    @classmethod
    def from_dict(cls, raw: object) -> ReviewFinalizationSnapshot:
        expected = {
            "schema_version",
            "session_id",
            "session_name",
            "source_digest",
            "settings",
            "parent_session_id",
            "parent_snapshot_digest",
            "finalized_at",
            "candidates",
            "call_count",
            "not_call_count",
            "unreviewed_count",
            "snapshot_digest",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw["candidates"], list)
        ):
            raise ValueError("Review finalization snapshot is invalid.")
        return cls(
            schema_version=raw["schema_version"],
            session_id=raw["session_id"],
            session_name=raw["session_name"],
            source_digest=raw["source_digest"],
            settings=SpectrogramSettingsSnapshot.from_dict(raw["settings"]),
            parent_session_id=raw["parent_session_id"],
            parent_snapshot_digest=raw["parent_snapshot_digest"],
            finalized_at=raw["finalized_at"],
            candidates=tuple(
                FinalizedCandidateDecision.from_dict(row) for row in raw["candidates"]
            ),
            call_count=raw["call_count"],
            not_call_count=raw["not_call_count"],
            unreviewed_count=raw["unreviewed_count"],
            snapshot_digest=raw["snapshot_digest"],
        )


def candidate_to_storage_tuple(candidate: EligibleCandidate) -> tuple[object, ...]:
    """Canonical candidate projection used by the transactional session store."""
    return (
        candidate.ordinal,
        candidate.recording_ordinal,
        candidate.candidate_id,
        candidate.recording_ref,
        candidate.recording_key,
        candidate.source_sha256,
        candidate.sample_rate_hz,
        candidate.frame_count,
        candidate.channels,
        candidate.start_frame,
        candidate.end_frame,
        candidate.start_time_ns,
        candidate.end_time_ns,
        float(candidate.cnn_target_score),
        candidate.rf_target_score,
        candidate.contributing_windows,
    )


__all__ = [
    "AnnotationBook",
    "AnnotationChange",
    "AnnotationOperation",
    "DEFAULT_PRESET_ID",
    "DecisionOrigin",
    "FINALIZATION_SCHEMA_VERSION",
    "FinalizedCandidateDecision",
    "HumanDecision",
    "REVIEW_SESSION_SCHEMA_VERSION",
    "ReviewFinalizationSnapshot",
    "ReviewLabel",
    "ReviewRevisionConflict",
    "ReviewSessionSource",
    "ReviewSessionState",
    "SPECTROGRAM_SETTINGS_SCHEMA_VERSION",
    "SpectrogramSettingsSnapshot",
    "candidate_to_storage_tuple",
    "propose_session_name",
    "require_session_transition",
    "validate_candidate_id",
    "validate_digest",
    "validate_display_name",
    "validate_preset_id",
    "validate_session_id",
    "validate_timestamp",
]
