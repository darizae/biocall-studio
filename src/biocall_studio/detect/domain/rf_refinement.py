"""Verified RF scoring and immutable parent-to-child Result lineage."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import librosa
import numpy as np
from bioacoustics_dl_toolbox.audio import load_audio_file
from bioacoustics_dl_toolbox.rf import compute_rf_features
from numpy.typing import NDArray

from biocall_studio.detect.domain import validate_collection_id, validate_relative_reference
from biocall_studio.detect.domain.models import ModelFamily, ModelRole, ModelSnapshot
from biocall_studio.detect.domain.results import (
    SOURCE_TIME_SEMANTICS,
    CandidateInterval,
    DetectionResult,
    FileOutcomeStatus,
    RecordingOutcome,
)
from biocall_studio.detect.domain.runs import canonical_digest
from biocall_studio.shared.paths import validate_relative_path

DERIVED_RESULT_SCHEMA_VERSION = 1
RF_SCORE_SEMANTICS = (
    "sklearn_predict_proba_for_integer_target_class_1; "
    "accepted_when_score_greater_than_or_equal_to_frozen_model_threshold"
)
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_RUN_ID = re.compile(r"drun_[0-9a-f]{32}")
_REQUEST_ID = re.compile(r"dreq_[0-9a-f]{32}")
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_MODEL_ID = re.compile(r"mdl_[0-9a-f]{32}")
_RECORDING_ID = re.compile(r"rec_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UNSCORED_REASONS = frozenset(
    {"short_segment", "feature_extraction_failed", "non_finite_features"}
)
_ROBUST_FEATURE_NAMES = (
    "Dur 90% (s)",
    "Dur 50% (s)",
    "Center Freq (Hz)",
    "Freq 5% (Hz)",
    "Freq 25% (Hz)",
    "Freq 75% (Hz)",
    "Freq 95% (Hz)",
    "BW 50% (Hz)",
    "BW 90% (Hz)",
    "Avg Entropy (bits)",
    "Agg Entropy (bits)",
)
_RF_CONFIG_KEYS = frozenset(
    {
        "sample_rate_hz",
        "min_duration_s",
        "pad_short_segments",
        "pad_mode",
        "n_fft",
        "hop_length",
        "n_mfcc",
        "include_deltas",
        "fmin_hz",
        "fmax_hz",
    }
)
_Scalar = bool | int | float | str | None
_ConfigItems = tuple[tuple[str, _Scalar], ...]


class RefinementStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNSCORED = "unscored"


class RfFeatureSchemaError(ValueError):
    """Extracted or estimator feature/class schema differs from the trusted Model."""


class RfNonFiniteFeatureError(ValueError):
    """One candidate produced a non-finite feature vector."""


class RfSourceMismatchError(ValueError):
    """Decoded source facts no longer match the parent Result."""


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _utc(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Derived Result completion time must be UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Derived Result completion time must be UTC.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Derived Result completion time must include UTC.")
    return value


def _config_items(value: Mapping[str, _Scalar] | _ConfigItems) -> _ConfigItems:
    rows = tuple(value.items()) if isinstance(value, Mapping) else tuple(value)
    normalized: list[tuple[str, _Scalar]] = []
    for key, setting in rows:
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(setting, (bool, int, float, str, type(None)))
            or isinstance(setting, float)
            and not math.isfinite(setting)
        ):
            raise ValueError("RF feature configuration is invalid.")
        normalized.append((key, setting))
    normalized.sort(key=lambda item: item[0])
    if len({key for key, _value in normalized}) != len(normalized):
        raise ValueError("RF feature configuration contains duplicate names.")
    return tuple(normalized)


def ordered_feature_vector(
    features: Mapping[str, float], feature_names: tuple[str, ...]
) -> NDArray[np.float64]:
    """Require the extractor's exact insertion order and a finite float64 row."""
    if (
        not feature_names
        or len(feature_names) != len(set(feature_names))
        or any(not isinstance(name, str) or not name for name in feature_names)
    ):
        raise RfFeatureSchemaError("RF ordered feature names are invalid.")
    if tuple(features) != feature_names:
        raise RfFeatureSchemaError(
            "RF extracted feature order disagrees with the trusted Model schema."
        )
    vector = np.asarray([float(features[name]) for name in feature_names], dtype=np.float64)
    if vector.shape != (len(feature_names),):
        raise RfFeatureSchemaError("RF feature vector width disagrees with its exact schema.")
    if not np.isfinite(vector).all():
        raise RfNonFiniteFeatureError("RF feature vector contains non-finite values.")
    return vector.reshape(1, -1)


def target_probability_score(
    probabilities: object,
    *,
    estimator_classes: object,
    probability_class_order: tuple[int, ...],
    target_probability_column: int,
) -> float:
    """Return class 1's probability only after exact class-column validation."""
    try:
        classes = np.asarray(estimator_classes)
    except (TypeError, ValueError) as exc:
        raise RfFeatureSchemaError("RF estimator class order is invalid.") from exc
    if (
        classes.ndim != 1
        or classes.shape != (2,)
        or any(type(value.item()) is not int for value in classes)
        or tuple(int(value) for value in classes) != probability_class_order
        or set(probability_class_order) != {0, 1}
    ):
        raise RfFeatureSchemaError(
            "RF estimator class order disagrees with the trusted Model metadata."
        )
    if (
        type(target_probability_column) is not int
        or not 0 <= target_probability_column < 2
        or probability_class_order[target_probability_column] != 1
    ):
        raise RfFeatureSchemaError("RF target probability column is invalid.")
    values = np.asarray(probabilities, dtype=np.float64)
    if values.shape != (1, 2):
        raise RfFeatureSchemaError("RF prediction must contain one two-class probability row.")
    if not np.isfinite(values).all():
        raise ValueError("RF prediction contains non-finite probabilities.")
    if (values < 0).any() or (values > 1).any() or not math.isclose(
        float(values.sum()), 1.0, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise ValueError("RF prediction does not contain valid class probabilities.")
    return float(values[0, target_probability_column])


def prepare_candidate_segment(
    signal: NDArray[np.float32],
    *,
    source_sample_rate_hz: int,
    start_frame: int,
    end_frame: int,
    target_sample_rate_hz: int,
    minimum_duration_seconds: float,
    short_segment_policy: str,
) -> NDArray[np.float32] | None:
    """Apply the frozen RF resample, source-time slice, and short-segment policy."""
    values = np.asarray(signal, dtype=np.float32)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("RF source signal must be nonempty mono float32 audio.")
    if (
        type(source_sample_rate_hz) is not int
        or source_sample_rate_hz <= 0
        or type(target_sample_rate_hz) is not int
        or target_sample_rate_hz <= 0
        or type(start_frame) is not int
        or type(end_frame) is not int
        or start_frame < 0
        or end_frame <= start_frame
        or end_frame > values.shape[0]
        or not isinstance(minimum_duration_seconds, (int, float))
        or isinstance(minimum_duration_seconds, bool)
        or not math.isfinite(minimum_duration_seconds)
        or minimum_duration_seconds <= 0
    ):
        raise ValueError("RF candidate source-time facts are invalid.")
    if short_segment_policy not in {"center_zero_pad", "reject"}:
        raise ValueError("RF short-segment policy is unsupported.")
    if source_sample_rate_hz != target_sample_rate_hz:
        source_samples = int(values.shape[0])
        values = np.asarray(
            librosa.resample(
                values,
                orig_sr=source_sample_rate_hz,
                target_sr=target_sample_rate_hz,
                res_type="soxr_hq",
                fix=True,
                scale=False,
            ),
            dtype=np.float32,
        )
        expected_samples = round(
            source_samples * target_sample_rate_hz / source_sample_rate_hz
        )
        values = values[:expected_samples]
    start = round(start_frame * target_sample_rate_hz / source_sample_rate_hz)
    end = round(end_frame * target_sample_rate_hz / source_sample_rate_hz)
    end = min(end, int(values.shape[0]))
    if end <= start:
        return None
    segment = values[start:end].astype(np.float32, copy=False)
    minimum_samples = round(target_sample_rate_hz * minimum_duration_seconds)
    if segment.shape[0] < minimum_samples:
        if short_segment_policy == "reject":
            return None
        missing = minimum_samples - int(segment.shape[0])
        segment = np.pad(
            segment, (missing // 2, missing - missing // 2), mode="constant"
        ).astype(np.float32, copy=False)
    return segment


def _canonical_features(
    raw: Mapping[str, float], *, n_mfcc: int, include_deltas: bool
) -> dict[str, float]:
    try:
        mapped = {name: float(raw[name]) for name in _ROBUST_FEATURE_NAMES}
        for toolbox_prefix, canonical_prefix in (
            ("MFCC", "mfcc"),
            ("ΔMFCC", "d_mfcc"),
            ("ΔΔMFCC", "dd_mfcc"),
        ):
            if canonical_prefix != "mfcc" and not include_deltas:
                continue
            for coefficient in range(1, n_mfcc + 1):
                mapped[f"{canonical_prefix}{coefficient}_mean"] = float(
                    raw[f"{toolbox_prefix} {coefficient:02d} mean"]
                )
                mapped[f"{canonical_prefix}{coefficient}_std"] = float(
                    raw[f"{toolbox_prefix} {coefficient:02d} std"]
                )
    except (KeyError, TypeError, ValueError) as exc:
        raise RfFeatureSchemaError(
            "RF extractor output does not match the verified robust+MFCC schema."
        ) from exc
    return mapped


def _validated_feature_config(snapshot: ModelSnapshot) -> dict[str, _Scalar]:
    if (
        snapshot.family is not ModelFamily.RANDOM_FOREST
        or snapshot.role is not ModelRole.INTERVAL_REFINEMENT
        or snapshot.rf_feature_family != "robust-mfcc-v1"
        or snapshot.short_segment_policy not in {"center_zero_pad", "reject"}
    ):
        raise RfFeatureSchemaError("A compatible trusted RF ModelSnapshot is required.")
    config = dict(snapshot.rf_feature_config)
    if set(config) != _RF_CONFIG_KEYS:
        raise RfFeatureSchemaError("RF feature configuration fields are incompatible.")
    if (
        config["sample_rate_hz"] != snapshot.sample_rate_hz
        or float(config["min_duration_s"]) != snapshot.minimum_duration_seconds
        or (bool(config["pad_short_segments"]))
        != (snapshot.short_segment_policy == "center_zero_pad")
        or config["pad_mode"] != "constant"
    ):
        raise RfFeatureSchemaError("RF preprocessing metadata is internally inconsistent.")
    return config


def extract_candidate_features(
    path: Path,
    *,
    source_sample_rate_hz: int,
    source_frame_count: int,
    start_frame: int,
    end_frame: int,
    snapshot: ModelSnapshot,
) -> dict[str, float] | None:
    """Extract one parent candidate using the same callable toolbox API as Train."""
    config = _validated_feature_config(snapshot)
    waveform = load_audio_file(str(path), sample_rate=None, mono=True)
    if waveform.ndim != 2 or waveform.shape[0] != 1 or waveform.shape[1] == 0:
        raise ValueError("RF input must decode to nonempty mono audio.")
    signal = np.asarray(waveform[0].numpy(), dtype=np.float32)
    if signal.shape[0] != source_frame_count:
        raise RfSourceMismatchError(
            "Decoded RF source frame count disagrees with the parent Result."
        )
    segment = prepare_candidate_segment(
        signal,
        source_sample_rate_hz=source_sample_rate_hz,
        start_frame=start_frame,
        end_frame=end_frame,
        target_sample_rate_hz=int(config["sample_rate_hz"]),
        minimum_duration_seconds=float(config["min_duration_s"]),
        short_segment_policy=snapshot.short_segment_policy,
    )
    if segment is None:
        return None
    sample_rate = int(config["sample_rate_hz"])
    raw = compute_rf_features(
        segment,
        sample_rate,
        0.0,
        float(segment.shape[0]) / sample_rate,
        low_hz=float(config["fmin_hz"]),
        high_hz=float(config["fmax_hz"]),
        n_fft=int(config["n_fft"]),
        hop_length=int(config["hop_length"]),
        n_mfcc=int(config["n_mfcc"]),
        include_deltas=bool(config["include_deltas"]),
        window="hann",
        center=True,
    )
    canonical = _canonical_features(
        raw,
        n_mfcc=int(config["n_mfcc"]),
        include_deltas=bool(config["include_deltas"]),
    )
    ordered_feature_vector(canonical, snapshot.rf_feature_names)
    return canonical


@dataclass(frozen=True, slots=True)
class RefinementDecision:
    status: RefinementStatus
    rf_target_score: float | None
    unscored_reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, RefinementStatus):
            raise ValueError("RF refinement status is invalid.")
        if self.status is RefinementStatus.UNSCORED:
            if self.rf_target_score is not None or self.unscored_reason not in _UNSCORED_REASONS:
                raise ValueError("An unscored RF decision requires an allowlisted reason.")
        elif (
            not isinstance(self.rf_target_score, (int, float))
            or isinstance(self.rf_target_score, bool)
            or not math.isfinite(self.rf_target_score)
            or not 0 <= self.rf_target_score <= 1
            or self.unscored_reason
        ):
            raise ValueError("A scored RF decision requires one finite probability.")

    @classmethod
    def scored(cls, score: float, *, threshold: float) -> RefinementDecision:
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("RF decision threshold is invalid.")
        value = float(score)
        return cls(
            RefinementStatus.ACCEPTED if value >= threshold else RefinementStatus.REJECTED,
            value,
            "",
        )

    @classmethod
    def unscored(cls, reason: str) -> RefinementDecision:
        return cls(RefinementStatus.UNSCORED, None, reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "rf_target_score": self.rf_target_score,
            "unscored_reason": self.unscored_reason,
        }


@dataclass(frozen=True, slots=True)
class RefinedCandidate:
    candidate_id: str
    recording_ref: str
    start_frame: int
    end_frame: int
    start_time_ns: int
    end_time_ns: int
    max_target_score: float
    contributing_windows: int
    status: RefinementStatus
    rf_target_score: float | None
    unscored_reason: str

    def __post_init__(self) -> None:
        CandidateInterval(
            self.candidate_id,
            self.recording_ref,
            self.start_frame,
            self.end_frame,
            self.start_time_ns,
            self.end_time_ns,
            self.max_target_score,
            self.contributing_windows,
        )
        RefinementDecision(self.status, self.rf_target_score, self.unscored_reason)

    @classmethod
    def from_parent(
        cls, candidate: CandidateInterval, decision: RefinementDecision
    ) -> RefinedCandidate:
        return cls(
            candidate.candidate_id,
            candidate.recording_ref,
            candidate.start_frame,
            candidate.end_frame,
            candidate.start_time_ns,
            candidate.end_time_ns,
            candidate.max_target_score,
            candidate.contributing_windows,
            decision.status,
            decision.rf_target_score,
            decision.unscored_reason,
        )

    def parent_candidate(self) -> CandidateInterval:
        return CandidateInterval(
            self.candidate_id,
            self.recording_ref,
            self.start_frame,
            self.end_frame,
            self.start_time_ns,
            self.end_time_ns,
            self.max_target_score,
            self.contributing_windows,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.parent_candidate().to_dict(),
            "status": self.status.value,
            "rf_target_score": self.rf_target_score,
            "unscored_reason": self.unscored_reason,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RefinedCandidate:
        expected = {
            "candidate_id",
            "recording_ref",
            "start_frame",
            "end_frame",
            "start_time_ns",
            "end_time_ns",
            "max_target_score",
            "contributing_windows",
            "status",
            "rf_target_score",
            "unscored_reason",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Refined candidate document is invalid.")
        values = dict(raw)
        values["status"] = RefinementStatus(raw["status"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class DerivedRecording:
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    parent_status: FileOutcomeStatus
    parent_error_code: str
    candidates: tuple[RefinedCandidate, ...]

    def __post_init__(self) -> None:
        if _RECORDING_ID.fullmatch(self.recording_ref) is None:
            raise ValueError("Derived recording reference is invalid.")
        if validate_relative_reference(self.recording_key) != self.recording_key:
            raise ValueError("Derived recording key is invalid.")
        _digest(self.source_sha256, "Derived recording source checksum")
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.frame_count) is not int
            or self.frame_count < 0
            or type(self.channels) is not int
            or self.channels <= 0
            or not isinstance(self.parent_status, FileOutcomeStatus)
        ):
            raise ValueError("Derived recording source facts are invalid.")
        if self.parent_status is FileOutcomeStatus.FAILED:
            if self.candidates or not self.parent_error_code:
                raise ValueError("A failed parent recording cannot contain refined candidates.")
        elif self.parent_error_code:
            raise ValueError("A successful parent recording cannot contain an error.")
        previous_end = -1
        for candidate in self.candidates:
            if (
                candidate.recording_ref != self.recording_ref
                or candidate.end_frame > self.frame_count
                or candidate.start_frame <= previous_end
            ):
                raise ValueError("Refined candidates do not preserve source-time ordering.")
            previous_end = candidate.end_frame

    @classmethod
    def from_parent(
        cls,
        outcome: RecordingOutcome,
        decisions: Mapping[str, RefinementDecision],
    ) -> DerivedRecording:
        return cls(
            outcome.recording_ref,
            outcome.recording_key,
            outcome.source_sha256,
            outcome.sample_rate_hz,
            outcome.frame_count,
            outcome.channels,
            outcome.status,
            outcome.error_code,
            tuple(
                RefinedCandidate.from_parent(candidate, decisions[candidate.candidate_id])
                for candidate in outcome.candidates
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_ref": self.recording_ref,
            "recording_key": self.recording_key,
            "source_sha256": self.source_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channels": self.channels,
            "parent_status": self.parent_status.value,
            "parent_error_code": self.parent_error_code,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @classmethod
    def from_dict(cls, raw: object) -> DerivedRecording:
        expected = {
            "recording_ref",
            "recording_key",
            "source_sha256",
            "sample_rate_hz",
            "frame_count",
            "channels",
            "parent_status",
            "parent_error_code",
            "candidates",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw["candidates"], list)
        ):
            raise ValueError("Derived recording document is invalid.")
        return cls(
            recording_ref=raw["recording_ref"],
            recording_key=raw["recording_key"],
            source_sha256=raw["source_sha256"],
            sample_rate_hz=raw["sample_rate_hz"],
            frame_count=raw["frame_count"],
            channels=raw["channels"],
            parent_status=FileOutcomeStatus(raw["parent_status"]),
            parent_error_code=raw["parent_error_code"],
            candidates=tuple(RefinedCandidate.from_dict(item) for item in raw["candidates"]),
        )


@dataclass(frozen=True, slots=True)
class DerivedResult:
    schema_version: int
    result_id: str
    result_digest: str
    run_id: str
    request_id: str
    parent_result_id: str
    parent_result_digest: str
    parent_run_id: str
    collection_id: str
    binding_revision: int
    inventory_id: str
    inventory_digest: str
    rf_model_id: str
    rf_model_snapshot_id: str
    rf_model_manifest_sha256: str
    rf_model_artifact_sha256: str
    rf_model_snapshot_digest: str
    threshold: float
    probability_class_order: tuple[int, ...]
    target_probability_column: int
    feature_family: str
    feature_names: tuple[str, ...]
    feature_config: _ConfigItems
    preprocessing_order: tuple[str, ...]
    backend_distribution: str
    backend_version: str
    backend_revision: str
    score_semantics: str
    source_time_semantics: str
    completed_at: str
    successful_files: int
    failed_files: int
    candidate_count: int
    accepted_count: int
    rejected_count: int
    unscored_count: int
    recordings: tuple[DerivedRecording, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DERIVED_RESULT_SCHEMA_VERSION:
            raise ValueError("Unsupported DerivedResult schema.")
        for value, pattern, label in (
            (self.result_id, _RESULT_ID, "Result ID"),
            (self.run_id, _RUN_ID, "Run ID"),
            (self.request_id, _REQUEST_ID, "request ID"),
            (self.parent_result_id, _RESULT_ID, "parent Result ID"),
            (self.parent_run_id, _RUN_ID, "parent Run ID"),
            (self.inventory_id, _INVENTORY_ID, "Inventory ID"),
            (self.rf_model_snapshot_id, _MODEL_ID, "RF ModelSnapshot ID"),
        ):
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise ValueError(f"Derived Result {label} is invalid.")
        if self.result_id == self.parent_result_id or self.run_id == self.parent_run_id:
            raise ValueError("Derived Result identity must differ from its parent.")
        validate_collection_id(self.collection_id)
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Derived Result binding revision is invalid.")
        safe_model_id = validate_relative_path(self.rf_model_id)
        if safe_model_id != self.rf_model_id or "/" in self.rf_model_id:
            raise ValueError("Derived Result RF Model ID is invalid.")
        for value, label in (
            (self.result_digest, "Result digest"),
            (self.parent_result_digest, "parent Result digest"),
            (self.inventory_digest, "Inventory digest"),
            (self.rf_model_manifest_sha256, "RF Model manifest digest"),
            (self.rf_model_artifact_sha256, "RF Model artifact digest"),
            (self.rf_model_snapshot_digest, "RF ModelSnapshot digest"),
        ):
            _digest(value, label)
        if (
            not isinstance(self.threshold, (int, float))
            or isinstance(self.threshold, bool)
            or not math.isfinite(self.threshold)
            or not 0 <= self.threshold <= 1
            or len(self.probability_class_order) != 2
            or set(self.probability_class_order) != {0, 1}
            or type(self.target_probability_column) is not int
            or not 0 <= self.target_probability_column < 2
            or self.probability_class_order[self.target_probability_column] != 1
        ):
            raise ValueError("Derived Result RF probability policy is invalid.")
        if (
            self.feature_family != "robust-mfcc-v1"
            or not self.feature_names
            or len(self.feature_names) != len(set(self.feature_names))
            or _config_items(self.feature_config) != self.feature_config
            or not self.preprocessing_order
        ):
            raise ValueError("Derived Result RF feature schema is invalid.")
        if not all(
            isinstance(value, str) and value and len(value) <= 200
            for value in (
                self.backend_distribution,
                self.backend_version,
                self.backend_revision,
            )
        ):
            raise ValueError("Derived Result backend provenance is invalid.")
        if self.score_semantics != RF_SCORE_SEMANTICS:
            raise ValueError("Derived Result RF score semantics are unsupported.")
        if self.source_time_semantics != SOURCE_TIME_SEMANTICS:
            raise ValueError("Derived Result source-time semantics are unsupported.")
        _utc(self.completed_at)
        keys = [recording.recording_key for recording in self.recordings]
        if not keys or keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Derived Result recordings must be nonempty, unique and sorted.")
        successful = sum(
            recording.parent_status is FileOutcomeStatus.SUCCEEDED
            for recording in self.recordings
        )
        candidates = tuple(
            candidate for recording in self.recordings for candidate in recording.candidates
        )
        counts = {
            status: sum(candidate.status is status for candidate in candidates)
            for status in RefinementStatus
        }
        if (
            self.successful_files != successful
            or self.failed_files != len(self.recordings) - successful
            or self.candidate_count != len(candidates)
            or self.candidate_count < 1
            or self.accepted_count != counts[RefinementStatus.ACCEPTED]
            or self.rejected_count != counts[RefinementStatus.REJECTED]
            or self.unscored_count != counts[RefinementStatus.UNSCORED]
            or len({candidate.candidate_id for candidate in candidates}) != len(candidates)
        ):
            raise ValueError("Derived Result status or candidate counts are inconsistent.")
        if canonical_digest(self._unsigned_dict()) != self.result_digest:
            raise ValueError("Derived Result digest does not match its immutable contents.")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "parent_result_id": self.parent_result_id,
            "parent_result_digest": self.parent_result_digest,
            "parent_run_id": self.parent_run_id,
            "collection_id": self.collection_id,
            "binding_revision": self.binding_revision,
            "inventory_id": self.inventory_id,
            "inventory_digest": self.inventory_digest,
            "rf_model_id": self.rf_model_id,
            "rf_model_snapshot_id": self.rf_model_snapshot_id,
            "rf_model_manifest_sha256": self.rf_model_manifest_sha256,
            "rf_model_artifact_sha256": self.rf_model_artifact_sha256,
            "rf_model_snapshot_digest": self.rf_model_snapshot_digest,
            "threshold": self.threshold,
            "probability_class_order": list(self.probability_class_order),
            "target_probability_column": self.target_probability_column,
            "feature_family": self.feature_family,
            "feature_names": list(self.feature_names),
            "feature_config": [list(row) for row in self.feature_config],
            "preprocessing_order": list(self.preprocessing_order),
            "backend_distribution": self.backend_distribution,
            "backend_version": self.backend_version,
            "backend_revision": self.backend_revision,
            "score_semantics": self.score_semantics,
            "source_time_semantics": self.source_time_semantics,
            "completed_at": self.completed_at,
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
            "candidate_count": self.candidate_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "unscored_count": self.unscored_count,
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
        parent: DetectionResult,
        rf_model_id: str,
        rf_model_snapshot_id: str,
        rf_model_manifest_sha256: str,
        rf_model_artifact_sha256: str,
        rf_model_snapshot_digest: str,
        threshold: float,
        probability_class_order: tuple[int, ...],
        target_probability_column: int,
        feature_family: str,
        feature_names: tuple[str, ...],
        feature_config: Mapping[str, _Scalar] | _ConfigItems,
        preprocessing_order: tuple[str, ...],
        backend_distribution: str,
        backend_version: str,
        backend_revision: str,
        completed_at: str,
        decisions: Mapping[str, RefinementDecision],
    ) -> DerivedResult:
        parent_ids = tuple(
            candidate.candidate_id
            for recording in parent.recordings
            for candidate in recording.candidates
        )
        if len(decisions) != len(parent_ids):
            raise ValueError("Derived Result requires exactly one decision per parent candidate.")
        if set(decisions) != set(parent_ids):
            raise ValueError("Derived Result decision refers to an unknown parent candidate.")
        recordings = tuple(
            DerivedRecording.from_parent(recording, decisions)
            for recording in parent.recordings
        )
        candidates = tuple(
            candidate for recording in recordings for candidate in recording.candidates
        )
        config = _config_items(feature_config)
        values: dict[str, object] = {
            "schema_version": DERIVED_RESULT_SCHEMA_VERSION,
            "result_id": result_id,
            "result_digest": "0" * 64,
            "run_id": run_id,
            "request_id": request_id,
            "parent_result_id": parent.result_id,
            "parent_result_digest": parent.result_digest,
            "parent_run_id": parent.run_id,
            "collection_id": parent.collection_id,
            "binding_revision": parent.binding_revision,
            "inventory_id": parent.inventory_id,
            "inventory_digest": parent.inventory_digest,
            "rf_model_id": rf_model_id,
            "rf_model_snapshot_id": rf_model_snapshot_id,
            "rf_model_manifest_sha256": rf_model_manifest_sha256,
            "rf_model_artifact_sha256": rf_model_artifact_sha256,
            "rf_model_snapshot_digest": rf_model_snapshot_digest,
            "threshold": float(threshold),
            "probability_class_order": tuple(probability_class_order),
            "target_probability_column": target_probability_column,
            "feature_family": feature_family,
            "feature_names": tuple(feature_names),
            "feature_config": config,
            "preprocessing_order": tuple(preprocessing_order),
            "backend_distribution": backend_distribution,
            "backend_version": backend_version,
            "backend_revision": backend_revision,
            "score_semantics": RF_SCORE_SEMANTICS,
            "source_time_semantics": SOURCE_TIME_SEMANTICS,
            "completed_at": completed_at,
            "successful_files": parent.successful_files,
            "failed_files": parent.failed_files,
            "candidate_count": len(candidates),
            "accepted_count": sum(
                candidate.status is RefinementStatus.ACCEPTED for candidate in candidates
            ),
            "rejected_count": sum(
                candidate.status is RefinementStatus.REJECTED for candidate in candidates
            ),
            "unscored_count": sum(
                candidate.status is RefinementStatus.UNSCORED for candidate in candidates
            ),
            "recordings": recordings,
        }
        placeholder = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(placeholder, name, value)
        values["result_digest"] = canonical_digest(placeholder._unsigned_dict())
        return cls(**values)  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, raw: object) -> DerivedResult:
        expected = {
            "schema_version",
            "result_id",
            "result_digest",
            "run_id",
            "request_id",
            "parent_result_id",
            "parent_result_digest",
            "parent_run_id",
            "collection_id",
            "binding_revision",
            "inventory_id",
            "inventory_digest",
            "rf_model_id",
            "rf_model_snapshot_id",
            "rf_model_manifest_sha256",
            "rf_model_artifact_sha256",
            "rf_model_snapshot_digest",
            "threshold",
            "probability_class_order",
            "target_probability_column",
            "feature_family",
            "feature_names",
            "feature_config",
            "preprocessing_order",
            "backend_distribution",
            "backend_version",
            "backend_revision",
            "score_semantics",
            "source_time_semantics",
            "completed_at",
            "successful_files",
            "failed_files",
            "candidate_count",
            "accepted_count",
            "rejected_count",
            "unscored_count",
            "recordings",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw["probability_class_order"], list)
            or not isinstance(raw["feature_names"], list)
            or not isinstance(raw["feature_config"], list)
            or not isinstance(raw["preprocessing_order"], list)
            or not isinstance(raw["recordings"], list)
        ):
            raise ValueError("DerivedResult document is invalid.")
        config_rows: list[tuple[str, _Scalar]] = []
        for row in raw["feature_config"]:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("DerivedResult feature configuration is invalid.")
            config_rows.append((row[0], row[1]))
        values = dict(raw)
        values["probability_class_order"] = tuple(raw["probability_class_order"])
        values["feature_names"] = tuple(raw["feature_names"])
        values["feature_config"] = tuple(config_rows)
        values["preprocessing_order"] = tuple(raw["preprocessing_order"])
        values["recordings"] = tuple(
            DerivedRecording.from_dict(item) for item in raw["recordings"]
        )
        return cls(**values)

    def verify_parent(self, parent: DetectionResult) -> None:
        if (
            self.parent_result_id != parent.result_id
            or self.parent_result_digest != parent.result_digest
            or self.parent_run_id != parent.run_id
            or self.collection_id != parent.collection_id
            or self.binding_revision != parent.binding_revision
            or self.inventory_id != parent.inventory_id
            or self.inventory_digest != parent.inventory_digest
            or self.successful_files != parent.successful_files
            or self.failed_files != parent.failed_files
            or len(self.recordings) != len(parent.recordings)
        ):
            raise ValueError("Derived Result parent lineage does not match the original Result.")
        for derived_recording, parent_recording in zip(
            self.recordings, parent.recordings, strict=True
        ):
            if (
                derived_recording.recording_ref != parent_recording.recording_ref
                or derived_recording.recording_key != parent_recording.recording_key
                or derived_recording.source_sha256 != parent_recording.source_sha256
                or derived_recording.sample_rate_hz != parent_recording.sample_rate_hz
                or derived_recording.frame_count != parent_recording.frame_count
                or derived_recording.channels != parent_recording.channels
                or derived_recording.parent_status is not parent_recording.status
                or derived_recording.parent_error_code != parent_recording.error_code
                or tuple(
                    candidate.parent_candidate() for candidate in derived_recording.candidates
                )
                != parent_recording.candidates
            ):
                raise ValueError(
                    "Derived Result candidate lineage differs from the original parent."
                )


ResultArtifact = DetectionResult | DerivedResult


__all__ = [
    "DERIVED_RESULT_SCHEMA_VERSION",
    "RF_SCORE_SEMANTICS",
    "DerivedRecording",
    "DerivedResult",
    "RefinedCandidate",
    "RefinementDecision",
    "RefinementStatus",
    "ResultArtifact",
    "RfFeatureSchemaError",
    "RfNonFiniteFeatureError",
    "RfSourceMismatchError",
    "extract_candidate_features",
    "ordered_feature_vector",
    "prepare_candidate_segment",
    "target_probability_score",
]
