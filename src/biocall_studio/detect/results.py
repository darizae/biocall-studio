"""Immutable metadata-only first-pass Detection Result contract."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from biocall_studio.detect.detection import DetectionSettings
from biocall_studio.detect.domain import validate_collection_id, validate_relative_reference
from biocall_studio.detect.runs import canonical_digest
from biocall_studio_train.domain.paths import validate_relative_path

DETECTION_RESULT_SCHEMA_VERSION = 1
SCORE_SEMANTICS = "binary_softmax_target_output_index_1; not_a_calibrated_probability"
SOURCE_TIME_SEMANTICS = (
    "half_open_original_recording_frames; resampled starts floor and ends ceil; "
    "nanoseconds round to nearest with half upward"
)
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_RUN_ID = re.compile(r"drun_[0-9a-f]{32}")
_REQUEST_ID = re.compile(r"dreq_[0-9a-f]{32}")
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_MODEL_ID = re.compile(r"mdl_[0-9a-f]{32}")
_RECORDING_ID = re.compile(r"rec_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE_ERROR_CODES = frozenset(
    {"audio_decode_failed", "inference_failed", "unsupported_output"}
)


class FileOutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResultCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _utc(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Detection Result completion time must be UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Detection Result completion time must be UTC.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Detection Result completion time must include UTC.")
    return value


def _token(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}"


def recording_identity(inventory_id: str, recording_key: str, source_sha256: str) -> str:
    if _INVENTORY_ID.fullmatch(inventory_id) is None:
        raise ValueError("Inventory identifier is invalid.")
    key = validate_relative_reference(recording_key)
    _digest(source_sha256, "Recording checksum")
    return _token("rec", [inventory_id, key, source_sha256])


def candidate_identity(
    recording_ref: str,
    start_frame: int,
    end_frame: int,
    scientific_identity: str,
) -> str:
    if _RECORDING_ID.fullmatch(recording_ref) is None:
        raise ValueError("Recording reference is invalid.")
    if (
        type(start_frame) is not int
        or type(end_frame) is not int
        or start_frame < 0
        or end_frame <= start_frame
        or not isinstance(scientific_identity, str)
        or not scientific_identity
    ):
        raise ValueError("Candidate identity inputs are invalid.")
    return _token("cand", [recording_ref, start_frame, end_frame, scientific_identity])


def _frame_ns(frame: int, sample_rate_hz: int) -> int:
    return (frame * 1_000_000_000 + sample_rate_hz // 2) // sample_rate_hz


@dataclass(frozen=True, slots=True)
class CandidateInterval:
    candidate_id: str
    recording_ref: str
    start_frame: int
    end_frame: int
    start_time_ns: int
    end_time_ns: int
    max_target_score: float
    contributing_windows: int

    def __post_init__(self) -> None:
        if _CANDIDATE_ID.fullmatch(self.candidate_id) is None:
            raise ValueError("Candidate identifier is invalid.")
        if _RECORDING_ID.fullmatch(self.recording_ref) is None:
            raise ValueError("Candidate recording reference is invalid.")
        if (
            type(self.start_frame) is not int
            or type(self.end_frame) is not int
            or self.start_frame < 0
            or self.end_frame <= self.start_frame
            or type(self.start_time_ns) is not int
            or type(self.end_time_ns) is not int
            or self.start_time_ns < 0
            or self.end_time_ns <= self.start_time_ns
        ):
            raise ValueError("Candidate source interval is invalid.")
        if (
            not isinstance(self.max_target_score, (int, float))
            or isinstance(self.max_target_score, bool)
            or not math.isfinite(self.max_target_score)
            or not 0 <= self.max_target_score <= 1
        ):
            raise ValueError("Candidate target score is invalid.")
        if type(self.contributing_windows) is not int or self.contributing_windows <= 0:
            raise ValueError("Candidate window count is invalid.")

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        recording_ref: str,
        start_frame: int,
        end_frame: int,
        sample_rate_hz: int,
        max_target_score: float,
        contributing_windows: int,
    ) -> CandidateInterval:
        if type(sample_rate_hz) is not int or sample_rate_hz <= 0:
            raise ValueError("Candidate source sample rate is invalid.")
        return cls(
            candidate_id,
            recording_ref,
            start_frame,
            end_frame,
            _frame_ns(start_frame, sample_rate_hz),
            _frame_ns(end_frame, sample_rate_hz),
            float(max_target_score),
            contributing_windows,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "recording_ref": self.recording_ref,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_time_ns": self.start_time_ns,
            "end_time_ns": self.end_time_ns,
            "max_target_score": self.max_target_score,
            "contributing_windows": self.contributing_windows,
        }

    @classmethod
    def from_dict(cls, raw: object) -> CandidateInterval:
        expected = {
            "candidate_id",
            "recording_ref",
            "start_frame",
            "end_frame",
            "start_time_ns",
            "end_time_ns",
            "max_target_score",
            "contributing_windows",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Candidate interval document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class RecordingOutcome:
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    status: FileOutcomeStatus
    candidates: tuple[CandidateInterval, ...]
    error_code: str

    def __post_init__(self) -> None:
        if _RECORDING_ID.fullmatch(self.recording_ref) is None:
            raise ValueError("Recording outcome reference is invalid.")
        key = validate_relative_reference(self.recording_key)
        if key != self.recording_key:
            raise ValueError("Recording outcome key is not normalized.")
        _digest(self.source_sha256, "Recording source checksum")
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.frame_count) is not int
            or self.frame_count < 0
            or type(self.channels) is not int
            or self.channels <= 0
        ):
            raise ValueError("Recording outcome time-base facts are invalid.")
        if not isinstance(self.status, FileOutcomeStatus):
            raise ValueError("Recording outcome status is invalid.")
        if self.status is FileOutcomeStatus.SUCCEEDED:
            if self.error_code:
                raise ValueError("A successful recording cannot contain a file error.")
        elif self.candidates:
            raise ValueError("A failed recording cannot contain candidates.")
        elif self.error_code not in _FILE_ERROR_CODES:
            raise ValueError("A failed recording requires an allowlisted error code.")
        previous_end = -1
        for candidate in self.candidates:
            if (
                candidate.recording_ref != self.recording_ref
                or candidate.end_frame > self.frame_count
                or candidate.start_frame <= previous_end
                or candidate.start_time_ns != _frame_ns(
                    candidate.start_frame, self.sample_rate_hz
                )
                or candidate.end_time_ns != _frame_ns(
                    candidate.end_frame, self.sample_rate_hz
                )
            ):
                raise ValueError("Recording candidates do not match source-time provenance.")
            previous_end = candidate.end_frame

    @classmethod
    def succeeded(
        cls,
        *,
        recording_ref: str,
        recording_key: str,
        source_sha256: str,
        sample_rate_hz: int,
        frame_count: int,
        channels: int,
        candidates: tuple[CandidateInterval, ...],
    ) -> RecordingOutcome:
        return cls(
            recording_ref,
            recording_key,
            source_sha256,
            sample_rate_hz,
            frame_count,
            channels,
            FileOutcomeStatus.SUCCEEDED,
            tuple(candidates),
            "",
        )

    @classmethod
    def failed(
        cls,
        *,
        recording_ref: str,
        recording_key: str,
        source_sha256: str,
        sample_rate_hz: int,
        frame_count: int,
        channels: int,
        error_code: str,
    ) -> RecordingOutcome:
        return cls(
            recording_ref,
            recording_key,
            source_sha256,
            sample_rate_hz,
            frame_count,
            channels,
            FileOutcomeStatus.FAILED,
            (),
            error_code,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_ref": self.recording_ref,
            "recording_key": self.recording_key,
            "source_sha256": self.source_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channels": self.channels,
            "status": self.status.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RecordingOutcome:
        expected = {
            "recording_ref",
            "recording_key",
            "source_sha256",
            "sample_rate_hz",
            "frame_count",
            "channels",
            "status",
            "candidates",
            "error_code",
        }
        if not isinstance(raw, dict) or set(raw) != expected or not isinstance(
            raw["candidates"], list
        ):
            raise ValueError("Recording outcome document is invalid.")
        return cls(
            recording_ref=raw["recording_ref"],
            recording_key=raw["recording_key"],
            source_sha256=raw["source_sha256"],
            sample_rate_hz=raw["sample_rate_hz"],
            frame_count=raw["frame_count"],
            channels=raw["channels"],
            status=FileOutcomeStatus(raw["status"]),
            candidates=tuple(CandidateInterval.from_dict(item) for item in raw["candidates"]),
            error_code=raw["error_code"],
        )


@dataclass(frozen=True, slots=True)
class DetectionResult:
    schema_version: int
    result_id: str
    result_digest: str
    run_id: str
    request_id: str
    collection_id: str
    binding_revision: int
    inventory_id: str
    inventory_digest: str
    model_id: str
    model_snapshot_id: str
    model_manifest_sha256: str
    model_artifact_sha256: str
    model_snapshot_digest: str
    settings: DetectionSettings
    window_length_samples: int
    hop_samples: int
    model_sample_rate_hz: int
    backend_distribution: str
    backend_version: str
    backend_revision: str
    score_semantics: str
    source_time_semantics: str
    completed_at: str
    completeness: ResultCompleteness
    successful_files: int
    failed_files: int
    candidate_count: int
    recordings: tuple[RecordingOutcome, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DETECTION_RESULT_SCHEMA_VERSION:
            raise ValueError("Unsupported DetectionResult schema.")
        for value, pattern, label in (
            (self.result_id, _RESULT_ID, "Result ID"),
            (self.run_id, _RUN_ID, "Run ID"),
            (self.request_id, _REQUEST_ID, "request ID"),
            (self.inventory_id, _INVENTORY_ID, "Inventory ID"),
            (self.model_snapshot_id, _MODEL_ID, "ModelSnapshot ID"),
        ):
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise ValueError(f"Detection Result {label} is invalid.")
        validate_collection_id(self.collection_id)
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Detection Result binding revision is invalid.")
        safe_model_id = validate_relative_path(self.model_id)
        if safe_model_id != self.model_id or "/" in self.model_id:
            raise ValueError("Detection Result Model ID is invalid.")
        for value, label in (
            (self.result_digest, "Result digest"),
            (self.inventory_digest, "Inventory digest"),
            (self.model_manifest_sha256, "Model manifest digest"),
            (self.model_artifact_sha256, "Model artifact digest"),
            (self.model_snapshot_digest, "ModelSnapshot digest"),
        ):
            _digest(value, label)
        if (
            type(self.window_length_samples) is not int
            or self.window_length_samples <= 0
            or self.hop_samples != self.settings.hop_samples(self.window_length_samples)
            or type(self.model_sample_rate_hz) is not int
            or self.model_sample_rate_hz <= 0
        ):
            raise ValueError("Detection Result resolved window settings are invalid.")
        if not all(
            isinstance(value, str) and value and len(value) <= 200
            for value in (
                self.backend_distribution,
                self.backend_version,
                self.backend_revision,
            )
        ):
            raise ValueError("Detection Result backend provenance is invalid.")
        if self.score_semantics != SCORE_SEMANTICS:
            raise ValueError("Detection Result score semantics are unsupported.")
        if self.source_time_semantics != SOURCE_TIME_SEMANTICS:
            raise ValueError("Detection Result source-time semantics are unsupported.")
        _utc(self.completed_at)
        keys = [recording.recording_key for recording in self.recordings]
        if not keys or keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Detection Result recordings must be nonempty, unique and sorted.")
        succeeded = sum(
            item.status is FileOutcomeStatus.SUCCEEDED for item in self.recordings
        )
        failed = len(self.recordings) - succeeded
        candidates = sum(len(item.candidates) for item in self.recordings)
        if succeeded < 1:
            raise ValueError("Detection Result requires at least one successful recording.")
        expected_completeness = (
            ResultCompleteness.COMPLETE if failed == 0 else ResultCompleteness.PARTIAL
        )
        if (
            self.successful_files != succeeded
            or self.failed_files != failed
            or self.candidate_count != candidates
            or self.completeness is not expected_completeness
        ):
            raise ValueError("Detection Result status or candidate count is inconsistent.")
        candidate_ids = [
            candidate.candidate_id
            for recording in self.recordings
            for candidate in recording.candidates
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Detection Result candidate identifiers are not unique.")
        if canonical_digest(self._unsigned_dict()) != self.result_digest:
            raise ValueError("Detection Result digest does not match its immutable contents.")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "collection_id": self.collection_id,
            "binding_revision": self.binding_revision,
            "inventory_id": self.inventory_id,
            "inventory_digest": self.inventory_digest,
            "model_id": self.model_id,
            "model_snapshot_id": self.model_snapshot_id,
            "model_manifest_sha256": self.model_manifest_sha256,
            "model_artifact_sha256": self.model_artifact_sha256,
            "model_snapshot_digest": self.model_snapshot_digest,
            "settings": self.settings.to_mapping(),
            "window_length_samples": self.window_length_samples,
            "hop_samples": self.hop_samples,
            "model_sample_rate_hz": self.model_sample_rate_hz,
            "backend_distribution": self.backend_distribution,
            "backend_version": self.backend_version,
            "backend_revision": self.backend_revision,
            "score_semantics": self.score_semantics,
            "source_time_semantics": self.source_time_semantics,
            "completed_at": self.completed_at,
            "completeness": self.completeness.value,
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
            "candidate_count": self.candidate_count,
            "recordings": [recording.to_dict() for recording in self.recordings],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "result_digest": self.result_digest}

    @classmethod
    def create(
        cls,
        *,
        result_id: str,
        run_id: str,
        request_id: str,
        collection_id: str,
        binding_revision: int,
        inventory_id: str,
        inventory_digest: str,
        model_id: str,
        model_snapshot_id: str,
        model_manifest_sha256: str,
        model_artifact_sha256: str,
        model_snapshot_digest: str,
        settings: DetectionSettings,
        window_length_samples: int,
        hop_samples: int,
        model_sample_rate_hz: int,
        backend_distribution: str,
        backend_version: str,
        backend_revision: str,
        completed_at: str,
        recordings: tuple[RecordingOutcome, ...],
    ) -> DetectionResult:
        ordered = tuple(sorted(recordings, key=lambda item: item.recording_key))
        successful = sum(item.status is FileOutcomeStatus.SUCCEEDED for item in ordered)
        failed = len(ordered) - successful
        candidates = sum(len(item.candidates) for item in ordered)
        placeholder = cls.__new__(cls)
        values = {
            "schema_version": DETECTION_RESULT_SCHEMA_VERSION,
            "result_id": result_id,
            "result_digest": "0" * 64,
            "run_id": run_id,
            "request_id": request_id,
            "collection_id": collection_id,
            "binding_revision": binding_revision,
            "inventory_id": inventory_id,
            "inventory_digest": inventory_digest,
            "model_id": model_id,
            "model_snapshot_id": model_snapshot_id,
            "model_manifest_sha256": model_manifest_sha256,
            "model_artifact_sha256": model_artifact_sha256,
            "model_snapshot_digest": model_snapshot_digest,
            "settings": settings,
            "window_length_samples": window_length_samples,
            "hop_samples": hop_samples,
            "model_sample_rate_hz": model_sample_rate_hz,
            "backend_distribution": backend_distribution,
            "backend_version": backend_version,
            "backend_revision": backend_revision,
            "score_semantics": SCORE_SEMANTICS,
            "source_time_semantics": SOURCE_TIME_SEMANTICS,
            "completed_at": completed_at,
            "completeness": (
                ResultCompleteness.COMPLETE
                if failed == 0
                else ResultCompleteness.PARTIAL
            ),
            "successful_files": successful,
            "failed_files": failed,
            "candidate_count": candidates,
            "recordings": ordered,
        }
        for name, value in values.items():
            object.__setattr__(placeholder, name, value)
        digest = canonical_digest(placeholder._unsigned_dict())
        values["result_digest"] = digest
        return cls(**values)

    @classmethod
    def from_dict(cls, raw: object) -> DetectionResult:
        expected = {
            "schema_version",
            "result_id",
            "result_digest",
            "run_id",
            "request_id",
            "collection_id",
            "binding_revision",
            "inventory_id",
            "inventory_digest",
            "model_id",
            "model_snapshot_id",
            "model_manifest_sha256",
            "model_artifact_sha256",
            "model_snapshot_digest",
            "settings",
            "window_length_samples",
            "hop_samples",
            "model_sample_rate_hz",
            "backend_distribution",
            "backend_version",
            "backend_revision",
            "score_semantics",
            "source_time_semantics",
            "completed_at",
            "completeness",
            "successful_files",
            "failed_files",
            "candidate_count",
            "recordings",
        }
        if not isinstance(raw, dict) or set(raw) != expected or not isinstance(
            raw["recordings"], list
        ) or not isinstance(raw["settings"], dict):
            raise ValueError("DetectionResult document is invalid.")
        values = dict(raw)
        values["settings"] = DetectionSettings.from_mapping(raw["settings"])
        values["completeness"] = ResultCompleteness(raw["completeness"])
        values["recordings"] = tuple(
            RecordingOutcome.from_dict(item) for item in raw["recordings"]
        )
        return cls(**values)


__all__ = [
    "DETECTION_RESULT_SCHEMA_VERSION",
    "SCORE_SEMANTICS",
    "SOURCE_TIME_SEMANTICS",
    "CandidateInterval",
    "DetectionResult",
    "FileOutcomeStatus",
    "RecordingOutcome",
    "ResultCompleteness",
    "candidate_identity",
    "recording_identity",
]
