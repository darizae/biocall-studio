"""Pure CNN window decisions and the verified toolbox inference adapter."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from bioacoustics_dl_toolbox.prediction import predict_windows

from biocall_studio.detect.domain.models import ModelFamily, VerifiedModelReference


@dataclass(frozen=True, slots=True)
class DetectionSettings:
    """Validated user decisions frozen into every first-pass Detect Run."""

    minimum_score: float
    window_overlap_percent: int
    combine_gap_ms: int
    batch_size: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.minimum_score, (int, float))
            or isinstance(self.minimum_score, bool)
            or not math.isfinite(self.minimum_score)
            or not 0 <= self.minimum_score <= 1
        ):
            raise ValueError("Minimum detection score must be finite and between 0 and 1.")
        if (
            type(self.window_overlap_percent) is not int
            or not 0 <= self.window_overlap_percent <= 99
        ):
            raise ValueError("Window overlap must be an integer percentage from 0 to 99.")
        if type(self.combine_gap_ms) is not int or not 0 <= self.combine_gap_ms <= 60_000:
            raise ValueError("Candidate combination gap must be 0 to 60,000 milliseconds.")
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 128:
            raise ValueError("CNN batch size must be an integer from 1 to 128.")

    def hop_samples(self, window_samples: int) -> int:
        """Resolve overlap with nearest-integer rounding, half upward."""
        if type(window_samples) is not int or window_samples <= 0:
            raise ValueError("Model window length must be a positive number of samples.")
        retained_percent = 100 - self.window_overlap_percent
        return max(1, (window_samples * retained_percent + 50) // 100)

    def combine_gap_frames(self, sample_rate_hz: int) -> int:
        if type(sample_rate_hz) is not int or sample_rate_hz <= 0:
            raise ValueError("Source sample rate must be positive.")
        return (self.combine_gap_ms * sample_rate_hz + 500) // 1_000

    def to_mapping(self) -> dict[str, int | float | str]:
        return {
            "batch_size": self.batch_size,
            "combine_gap_ms": self.combine_gap_ms,
            "minimum_score": float(self.minimum_score),
            "settings_contract": "cnn-first-pass-v1",
            "window_overlap_percent": self.window_overlap_percent,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> DetectionSettings:
        expected = {
            "batch_size",
            "combine_gap_ms",
            "minimum_score",
            "settings_contract",
            "window_overlap_percent",
        }
        if set(raw) != expected or raw.get("settings_contract") != "cnn-first-pass-v1":
            raise ValueError("Detect Run settings do not match the CNN first-pass contract.")
        return cls(
            minimum_score=raw["minimum_score"],  # type: ignore[arg-type]
            window_overlap_percent=raw["window_overlap_percent"],  # type: ignore[arg-type]
            combine_gap_ms=raw["combine_gap_ms"],  # type: ignore[arg-type]
            batch_size=raw["batch_size"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class WindowScore:
    """Target score for one half-open window in the model-resampled time base."""

    index: int
    start_sample: int
    end_sample: int
    target_score: float

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("CNN window index is invalid.")
        if (
            type(self.start_sample) is not int
            or type(self.end_sample) is not int
            or self.start_sample < 0
            or self.end_sample <= self.start_sample
        ):
            raise ValueError("CNN window interval is invalid.")
        if (
            not isinstance(self.target_score, (int, float))
            or isinstance(self.target_score, bool)
            or not math.isfinite(self.target_score)
            or not 0 <= self.target_score <= 1
        ):
            raise ValueError("CNN target score must be finite and between 0 and 1.")


def target_score(
    probabilities: Mapping[str, float],
    *,
    class_to_index: tuple[tuple[str, int], ...],
) -> float:
    """Read the proven target output without treating it as calibrated certainty."""
    if class_to_index != (("noise", 0), ("target", 1)):
        raise ValueError("CNN output class mapping is ambiguous or unsupported.")
    if tuple(probabilities) != ("noise", "target"):
        raise ValueError("CNN output columns are ambiguous or out of order.")
    values = tuple(probabilities.values())
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in values
    ):
        raise ValueError("CNN output probabilities must be finite values from 0 to 1.")
    if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-5):
        raise ValueError("CNN binary softmax output probabilities do not sum to 1.")
    return float(probabilities["target"])


def map_resampled_interval_to_source(
    start_sample: int,
    end_sample: int,
    *,
    model_sample_rate_hz: int,
    source_sample_rate_hz: int,
    source_frame_count: int,
) -> tuple[int, int]:
    """Map model samples to covering original frames using floor-start/ceil-end."""
    if (
        type(start_sample) is not int
        or type(end_sample) is not int
        or start_sample < 0
        or end_sample <= start_sample
    ):
        raise ValueError("Resampled source interval must be nonempty and half-open.")
    if (
        type(model_sample_rate_hz) is not int
        or model_sample_rate_hz <= 0
        or type(source_sample_rate_hz) is not int
        or source_sample_rate_hz <= 0
        or type(source_frame_count) is not int
        or source_frame_count <= 0
    ):
        raise ValueError("Source interval time-base facts are invalid.")
    start = (start_sample * source_sample_rate_hz) // model_sample_rate_hz
    end = (
        end_sample * source_sample_rate_hz + model_sample_rate_hz - 1
    ) // model_sample_rate_hz
    start = min(start, source_frame_count)
    end = min(end, source_frame_count)
    if end <= start:
        raise ValueError("Resampled source interval maps outside the original recording.")
    return start, end


def predict_recording_windows(
    reference: VerifiedModelReference,
    audio_path: Path,
    settings: DetectionSettings,
) -> tuple[WindowScore, ...]:
    """Run the installed toolbox's verified CPU inference path on a real recording."""
    snapshot = reference.snapshot
    if snapshot.family is not ModelFamily.CNN or snapshot.window_length_samples is None:
        raise ValueError("CNN first-pass inference requires a compatible CNN ModelSnapshot.")
    artifact = reference.root / snapshot.artifact_relative_path
    hop = settings.hop_samples(snapshot.window_length_samples)
    predictions = predict_windows(
        artifact,
        Path(audio_path),
        hop_samples=hop,
        batch_size=settings.batch_size,
        device="cpu",
    )
    scores: list[WindowScore] = []
    for expected_index, prediction in enumerate(predictions):
        if (
            prediction.index != expected_index
            or prediction.start_sample != expected_index * hop
            or prediction.end_sample <= prediction.start_sample
        ):
            raise ValueError("CNN window output order or interval is ambiguous.")
        scores.append(
            WindowScore(
                prediction.index,
                prediction.start_sample,
                prediction.end_sample,
                target_score(
                    prediction.probabilities,
                    class_to_index=snapshot.class_to_index,
                ),
            )
        )
    if not scores:
        raise ValueError("CNN inference returned no windows for a nonempty recording.")
    return tuple(scores)


def merge_candidate_windows(
    windows: tuple[WindowScore, ...] | list[WindowScore],
    *,
    settings: DetectionSettings,
    model_sample_rate_hz: int,
    source_sample_rate_hz: int,
    source_frame_count: int,
) -> tuple[tuple[int, int, float, int], ...]:
    """Threshold, map, clamp and merge windows in exact original-source frames."""
    ordered = tuple(windows)
    if any(window.index != index for index, window in enumerate(ordered)):
        raise ValueError("CNN window outputs are missing, duplicated, or out of order.")
    selected: list[tuple[int, int, float, int]] = []
    for window in ordered:
        if not math.isfinite(window.target_score):
            raise ValueError("CNN target score must be finite.")
        if window.target_score < settings.minimum_score:
            continue
        start, end = map_resampled_interval_to_source(
            window.start_sample,
            window.end_sample,
            model_sample_rate_hz=model_sample_rate_hz,
            source_sample_rate_hz=source_sample_rate_hz,
            source_frame_count=source_frame_count,
        )
        selected.append((start, end, window.target_score, 1))
    gap = settings.combine_gap_frames(source_sample_rate_hz)
    merged: list[tuple[int, int, float, int]] = []
    for start, end, score, count in selected:
        if merged and start <= merged[-1][1] + gap:
            previous = merged[-1]
            merged[-1] = (
                previous[0],
                max(previous[1], end),
                max(previous[2], score),
                previous[3] + count,
            )
        else:
            merged.append((start, end, score, count))
    return tuple(merged)


__all__ = [
    "DetectionSettings",
    "WindowScore",
    "map_resampled_interval_to_source",
    "merge_candidate_windows",
    "predict_recording_windows",
    "target_score",
]
