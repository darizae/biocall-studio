"""Frozen eligibility projection from immutable Detect Results."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from biocall_studio.detect.domain import validate_collection_id, validate_relative_reference
from biocall_studio.detect.domain.inventory import (
    InclusionDecision,
    InventorySnapshot,
    RecordingStatus,
)
from biocall_studio.detect.domain.results import (
    DetectionResult,
    FileOutcomeStatus,
    recording_identity,
)
from biocall_studio.detect.domain.rf_refinement import (
    DerivedResult,
    RefinementStatus,
    ResultArtifact,
)

REVIEW_INTAKE_SCHEMA_VERSION = 1
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_RECORDING_ID = re.compile(r"rec_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ReviewResultKind(StrEnum):
    CNN = "cnn"
    RF = "rf"


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _frame_ns(frame: int, sample_rate_hz: int) -> int:
    return (frame * 1_000_000_000 + sample_rate_hz // 2) // sample_rate_hz


def _canonical_line(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


@dataclass(frozen=True, slots=True)
class ReviewRecording:
    ordinal: int
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    failed: bool
    error_code: str
    eligible_candidate_count: int

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("Review recording order is invalid.")
        if (
            not isinstance(self.recording_ref, str)
            or _RECORDING_ID.fullmatch(self.recording_ref) is None
        ):
            raise ValueError("Review recording reference is invalid.")
        if validate_relative_reference(
            self.recording_key
        ) != self.recording_key or not self.recording_key.casefold().endswith(".wav"):
            raise ValueError("Review recording key is invalid.")
        _digest(self.source_sha256, "Review recording source digest")
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.frame_count) is not int
            or self.frame_count < 0
            or type(self.channels) is not int
            or self.channels <= 0
            or not isinstance(self.failed, bool)
            or type(self.eligible_candidate_count) is not int
            or self.eligible_candidate_count < 0
        ):
            raise ValueError("Review recording facts are invalid.")
        if self.failed:
            if not self.error_code or self.eligible_candidate_count:
                raise ValueError("A failed Review recording cannot have eligible candidates.")
        elif self.error_code:
            raise ValueError("A successful Review recording cannot contain an error.")

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "recording_ref": self.recording_ref,
            "recording_key": self.recording_key,
            "source_sha256": self.source_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channels": self.channels,
            "failed": self.failed,
            "error_code": self.error_code,
            "eligible_candidate_count": self.eligible_candidate_count,
        }


@dataclass(frozen=True, slots=True)
class EligibleCandidate:
    ordinal: int
    recording_ordinal: int
    candidate_id: str
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    start_frame: int
    end_frame: int
    start_time_ns: int
    end_time_ns: int
    cnn_target_score: float
    rf_target_score: float | None
    contributing_windows: int

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 0
            or type(self.recording_ordinal) is not int
            or self.recording_ordinal < 0
        ):
            raise ValueError("Review candidate order is invalid.")
        if (
            not isinstance(self.candidate_id, str)
            or _CANDIDATE_ID.fullmatch(self.candidate_id) is None
        ):
            raise ValueError("Review candidate identifier is invalid.")
        ReviewRecording(
            ordinal=self.recording_ordinal,
            recording_ref=self.recording_ref,
            recording_key=self.recording_key,
            source_sha256=self.source_sha256,
            sample_rate_hz=self.sample_rate_hz,
            frame_count=self.frame_count,
            channels=self.channels,
            failed=False,
            error_code="",
            eligible_candidate_count=1,
        )
        if (
            type(self.start_frame) is not int
            or type(self.end_frame) is not int
            or self.start_frame < 0
            or self.end_frame <= self.start_frame
            or self.end_frame > self.frame_count
            or type(self.start_time_ns) is not int
            or type(self.end_time_ns) is not int
            or self.start_time_ns != _frame_ns(self.start_frame, self.sample_rate_hz)
            or self.end_time_ns != _frame_ns(self.end_frame, self.sample_rate_hz)
        ):
            raise ValueError("Review candidate source interval is invalid.")
        for score, label in (
            (self.cnn_target_score, "CNN target score"),
            (self.rf_target_score, "RF target score"),
        ):
            if score is None and label.startswith("RF"):
                continue
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ValueError(f"Review candidate {label} is invalid.")
        if type(self.contributing_windows) is not int or self.contributing_windows <= 0:
            raise ValueError("Review candidate window count is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "recording_ordinal": self.recording_ordinal,
            "candidate_id": self.candidate_id,
            "recording_ref": self.recording_ref,
            "recording_key": self.recording_key,
            "source_sha256": self.source_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channels": self.channels,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_time_ns": self.start_time_ns,
            "end_time_ns": self.end_time_ns,
            "cnn_target_score": self.cnn_target_score,
            "rf_target_score": self.rf_target_score,
            "contributing_windows": self.contributing_windows,
        }


@dataclass(frozen=True, slots=True)
class ReviewIntakeManifest:
    schema_version: int
    projection_digest: str
    result_kind: ReviewResultKind
    collection_id: str
    result_id: str
    result_digest: str
    publication_digest: str
    parent_result_id: str | None
    parent_result_digest: str | None
    binding_revision: int
    inventory_id: str
    inventory_digest: str
    source_time_semantics: str
    recording_count: int
    failed_recording_count: int
    eligible_candidate_count: int

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_INTAKE_SCHEMA_VERSION:
            raise ValueError("Unsupported Review intake schema.")
        _digest(self.projection_digest, "Review projection digest")
        if not isinstance(self.result_kind, ReviewResultKind):
            raise ValueError("Review Result kind is invalid.")
        validate_collection_id(self.collection_id)
        if not isinstance(self.result_id, str) or _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("Review Result reference is invalid.")
        _digest(self.result_digest, "Review Result digest")
        _digest(self.publication_digest, "Review publication digest")
        if self.result_kind is ReviewResultKind.CNN:
            if self.parent_result_id is not None or self.parent_result_digest is not None:
                raise ValueError("A CNN Review intake cannot contain RF parent lineage.")
        elif (
            not isinstance(self.parent_result_id, str)
            or _RESULT_ID.fullmatch(self.parent_result_id) is None
            or self.parent_result_id == self.result_id
            or self.parent_result_digest is None
        ):
            raise ValueError("An RF Review intake requires valid parent lineage.")
        if self.parent_result_digest is not None:
            _digest(self.parent_result_digest, "Review parent Result digest")
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Review binding revision is invalid.")
        if (
            not isinstance(self.inventory_id, str)
            or _INVENTORY_ID.fullmatch(self.inventory_id) is None
        ):
            raise ValueError("Review inventory reference is invalid.")
        _digest(self.inventory_digest, "Review inventory digest")
        if not isinstance(self.source_time_semantics, str) or not self.source_time_semantics:
            raise ValueError("Review source-time semantics are invalid.")
        if (
            type(self.recording_count) is not int
            or self.recording_count <= 0
            or type(self.failed_recording_count) is not int
            or not 0 <= self.failed_recording_count < self.recording_count
            or type(self.eligible_candidate_count) is not int
            or self.eligible_candidate_count < 0
        ):
            raise ValueError("Review projection counts are invalid.")

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result_kind": self.result_kind.value,
            "collection_id": self.collection_id,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "publication_digest": self.publication_digest,
            "parent_result_id": self.parent_result_id,
            "parent_result_digest": self.parent_result_digest,
            "binding_revision": self.binding_revision,
            "inventory_id": self.inventory_id,
            "inventory_digest": self.inventory_digest,
            "source_time_semantics": self.source_time_semantics,
            "recording_count": self.recording_count,
            "failed_recording_count": self.failed_recording_count,
            "eligible_candidate_count": self.eligible_candidate_count,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "projection_digest": self.projection_digest}


def projection_digest(
    manifest: ReviewIntakeManifest,
    recordings: Iterable[ReviewRecording],
    candidates: Iterable[EligibleCandidate],
) -> str:
    digest = hashlib.sha256(b"biocall-studio-review-intake-v1\n")
    digest.update(_canonical_line(manifest.unsigned_dict()))
    for recording in recordings:
        digest.update(_canonical_line(recording.to_dict()))
    for candidate in candidates:
        digest.update(_canonical_line(candidate.to_dict()))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewIntakeProjection:
    manifest: ReviewIntakeManifest
    recordings: tuple[ReviewRecording, ...]
    candidates: tuple[EligibleCandidate, ...]

    def __post_init__(self) -> None:
        if tuple(row.ordinal for row in self.recordings) != tuple(range(len(self.recordings))):
            raise ValueError("Review recordings are not in canonical order.")
        if tuple(row.ordinal for row in self.candidates) != tuple(range(len(self.candidates))):
            raise ValueError("Review candidates are not in canonical order.")
        if len({row.recording_ref for row in self.recordings}) != len(self.recordings):
            raise ValueError("Review recording references are not unique.")
        if len({row.candidate_id for row in self.candidates}) != len(self.candidates):
            raise ValueError("Review candidate identifiers are not unique.")
        by_ordinal = {row.ordinal: row for row in self.recordings}
        per_recording = dict.fromkeys(by_ordinal, 0)
        for candidate in self.candidates:
            recording = by_ordinal.get(candidate.recording_ordinal)
            if recording is None or (
                candidate.recording_ref,
                candidate.recording_key,
                candidate.source_sha256,
                candidate.sample_rate_hz,
                candidate.frame_count,
                candidate.channels,
            ) != (
                recording.recording_ref,
                recording.recording_key,
                recording.source_sha256,
                recording.sample_rate_hz,
                recording.frame_count,
                recording.channels,
            ):
                raise ValueError("Review candidate recording provenance is inconsistent.")
            per_recording[candidate.recording_ordinal] += 1
        if any(
            recording.eligible_candidate_count != per_recording[recording.ordinal]
            for recording in self.recordings
        ):
            raise ValueError("Review per-recording eligible counts are inconsistent.")
        if (
            self.manifest.recording_count != len(self.recordings)
            or self.manifest.failed_recording_count
            != sum(recording.failed for recording in self.recordings)
            or self.manifest.eligible_candidate_count != len(self.candidates)
        ):
            raise ValueError("Review projection counts are inconsistent.")
        expected_digest = projection_digest(self.manifest, self.recordings, self.candidates)
        if self.manifest.projection_digest != expected_digest:
            raise ValueError("Review projection digest does not match its eligible rows.")


def _validated_inputs(
    result: ResultArtifact,
    inventory: InventorySnapshot,
    parent: DetectionResult | None,
) -> tuple[ResultArtifact, InventorySnapshot, DetectionResult | None]:
    if isinstance(result, DetectionResult):
        checked_result: ResultArtifact = DetectionResult.from_dict(result.to_dict())
        if parent is not None:
            raise ValueError("A CNN Result cannot have a separate parent Result.")
        checked_parent = None
    elif isinstance(result, DerivedResult):
        checked_result = DerivedResult.from_dict(result.to_dict())
        if parent is None:
            raise ValueError("An RF-derived Result requires its original parent Result.")
        checked_parent = DetectionResult.from_dict(parent.to_dict())
        checked_result.verify_parent(checked_parent)
    else:
        raise ValueError("Review accepts only a Detect CNN or RF-derived Result.")
    checked_inventory = InventorySnapshot.from_dict(inventory.to_dict())
    return checked_result, checked_inventory, checked_parent


def build_review_projection(
    result: ResultArtifact,
    inventory: InventorySnapshot,
    *,
    publication_digest: str,
    parent: DetectionResult | None = None,
) -> ReviewIntakeProjection:
    """Validate Detect lineage and freeze only the candidates Review may expose."""
    checked_result, checked_inventory, checked_parent = _validated_inputs(result, inventory, parent)
    _digest(publication_digest, "Detect publication digest")
    if (
        checked_result.collection_id != checked_inventory.collection_id
        or checked_result.binding_revision != checked_inventory.binding_revision
        or checked_result.inventory_id != checked_inventory.inventory_id
        or checked_result.inventory_digest != checked_inventory.digest
    ):
        raise ValueError("Result and inventory identity or digest do not match.")
    result_keys = tuple(recording.recording_key for recording in checked_result.recordings)
    if result_keys != checked_inventory.included_keys:
        raise ValueError("Result recordings do not match the frozen included inventory.")
    inventory_rows = {row.recording_key: row for row in checked_inventory.recordings}
    result_kind = (
        ReviewResultKind.RF if isinstance(checked_result, DerivedResult) else ReviewResultKind.CNN
    )
    candidate_rows: list[EligibleCandidate] = []
    recording_rows: list[ReviewRecording] = []
    for recording_ordinal, recording in enumerate(checked_result.recordings):
        inventory_row = inventory_rows[recording.recording_key]
        wav = inventory_row.wav
        if (
            inventory_row.status is not RecordingStatus.VALID
            or inventory_row.decision is not InclusionDecision.INCLUDED
            or inventory_row.content_sha256 is None
            or wav is None
            or recording.source_sha256 != inventory_row.content_sha256
            or recording.sample_rate_hz != wav.sample_rate_hz
            or recording.frame_count != wav.frame_count
            or recording.channels != wav.channels
            or recording.recording_ref
            != recording_identity(
                checked_inventory.inventory_id,
                recording.recording_key,
                inventory_row.content_sha256,
            )
        ):
            raise ValueError("Result recording provenance differs from its frozen inventory.")
        failed = (
            recording.parent_status is FileOutcomeStatus.FAILED
            if isinstance(checked_result, DerivedResult)
            else recording.status is FileOutcomeStatus.FAILED
        )
        error_code = (
            recording.parent_error_code
            if isinstance(checked_result, DerivedResult)
            else recording.error_code
        )
        eligible = tuple(
            candidate
            for candidate in recording.candidates
            if not isinstance(checked_result, DerivedResult)
            or candidate.status is RefinementStatus.ACCEPTED
        )
        recording_rows.append(
            ReviewRecording(
                ordinal=recording_ordinal,
                recording_ref=recording.recording_ref,
                recording_key=recording.recording_key,
                source_sha256=recording.source_sha256,
                sample_rate_hz=recording.sample_rate_hz,
                frame_count=recording.frame_count,
                channels=recording.channels,
                failed=failed,
                error_code=error_code,
                eligible_candidate_count=len(eligible),
            )
        )
        for candidate in eligible:
            rf_score = (
                candidate.rf_target_score if isinstance(checked_result, DerivedResult) else None
            )
            if isinstance(checked_result, DerivedResult) and rf_score is None:
                raise ValueError("An RF-accepted candidate requires a finite RF score.")
            candidate_rows.append(
                EligibleCandidate(
                    ordinal=len(candidate_rows),
                    recording_ordinal=recording_ordinal,
                    candidate_id=candidate.candidate_id,
                    recording_ref=recording.recording_ref,
                    recording_key=recording.recording_key,
                    source_sha256=recording.source_sha256,
                    sample_rate_hz=recording.sample_rate_hz,
                    frame_count=recording.frame_count,
                    channels=recording.channels,
                    start_frame=candidate.start_frame,
                    end_frame=candidate.end_frame,
                    start_time_ns=candidate.start_time_ns,
                    end_time_ns=candidate.end_time_ns,
                    cnn_target_score=candidate.max_target_score,
                    rf_target_score=rf_score,
                    contributing_windows=candidate.contributing_windows,
                )
            )
    recordings = tuple(recording_rows)
    candidates = tuple(candidate_rows)
    manifest = ReviewIntakeManifest(
        schema_version=REVIEW_INTAKE_SCHEMA_VERSION,
        projection_digest="0" * 64,
        result_kind=result_kind,
        collection_id=checked_result.collection_id,
        result_id=checked_result.result_id,
        result_digest=checked_result.result_digest,
        publication_digest=publication_digest,
        parent_result_id=(
            checked_result.parent_result_id if isinstance(checked_result, DerivedResult) else None
        ),
        parent_result_digest=(
            checked_result.parent_result_digest
            if isinstance(checked_result, DerivedResult)
            else None
        ),
        binding_revision=checked_result.binding_revision,
        inventory_id=checked_result.inventory_id,
        inventory_digest=checked_result.inventory_digest,
        source_time_semantics=checked_result.source_time_semantics,
        recording_count=len(recordings),
        failed_recording_count=sum(recording.failed for recording in recordings),
        eligible_candidate_count=len(candidates),
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, recordings, candidates),
    )
    projection = ReviewIntakeProjection(manifest, recordings, candidates)
    if isinstance(checked_result, DerivedResult) and checked_parent is None:
        raise AssertionError("RF lineage validation did not retain its parent.")
    return projection


__all__ = [
    "REVIEW_INTAKE_SCHEMA_VERSION",
    "EligibleCandidate",
    "ReviewIntakeManifest",
    "ReviewIntakeProjection",
    "ReviewRecording",
    "ReviewResultKind",
    "build_review_projection",
    "projection_digest",
]
