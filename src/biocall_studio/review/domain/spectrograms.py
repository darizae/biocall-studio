"""Pure source-frame, settings, and raster-coordinate contracts for Review."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from biocall_studio.review.domain.intake import EligibleCandidate

SPECTROGRAM_ALGORITHM_VERSION = "review-stft-v1"
SPECTROGRAM_RENDER_VERSION = "review-raster-v1"
CHANNEL_POLICY = "independent-channel-power-mean"

_CONTENT_KEY = re.compile(r"spec_[0-9a-f]{64}")
_FREQUENCY_MAX_CHOICES = frozenset((3_000, 4_200, 8_000))
_CONTEXT_CHOICES = frozenset((1, 2, 3))
_CONTRAST_CHOICES = frozenset((40, 50, 65))
_EXACT_WINDOW_CHOICES = frozenset((20, 25, 30, 40, 50, 60, 80, 100))
_OVERLAP_CHOICES = frozenset((50, 75))
_FREQUENCY_MIN_CHOICES = frozenset((0, 100, 300))


class SoundDetail(StrEnum):
    FAST_CHANGES = "fast_changes"
    BALANCED = "balanced"
    CLOSE_PITCHES = "close_pitches"


class Palette(StrEnum):
    MAGMA = "magma"
    VIRIDIS = "viridis"


class SpectrogramImageTier(StrEnum):
    THUMBNAIL = "thumbnail"
    DETAIL = "detail"

    @property
    def dimensions(self) -> tuple[int, int]:
        # Fixed v1 data-raster tiers. Axes and detection marks are painted by Qt.
        return (320, 120) if self is SpectrogramImageTier.THUMBNAIL else (1_200, 450)


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _frame_ns(frame: int, sample_rate_hz: int) -> int:
    return (frame * 1_000_000_000 + sample_rate_hz // 2) // sample_rate_hz


@dataclass(frozen=True, slots=True)
class CandidateContext:
    candidate_id: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    channels: int
    source_frame_count: int
    context_start_frame: int
    context_end_frame: int
    candidate_start_frame: int
    candidate_end_frame: int

    def __post_init__(self) -> None:
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.channels) is not int
            or self.channels <= 0
            or type(self.source_frame_count) is not int
            or self.source_frame_count <= 0
            or type(self.context_start_frame) is not int
            or type(self.context_end_frame) is not int
            or type(self.candidate_start_frame) is not int
            or type(self.candidate_end_frame) is not int
            or not 0 <= self.context_start_frame < self.context_end_frame <= self.source_frame_count
            or not self.context_start_frame
            <= self.candidate_start_frame
            < self.candidate_end_frame
            <= self.context_end_frame
        ):
            raise ValueError("Review candidate context frames are invalid.")

    @property
    def frame_count(self) -> int:
        return self.context_end_frame - self.context_start_frame

    @property
    def context_start_time_ns(self) -> int:
        return _frame_ns(self.context_start_frame, self.sample_rate_hz)

    @property
    def context_end_time_ns(self) -> int:
        return _frame_ns(self.context_end_frame, self.sample_rate_hz)

    @property
    def candidate_start_time_ns(self) -> int:
        return _frame_ns(self.candidate_start_frame, self.sample_rate_hz)

    @property
    def candidate_end_time_ns(self) -> int:
        return _frame_ns(self.candidate_end_frame, self.sample_rate_hz)

    @property
    def context_duration_ns(self) -> int:
        return self.context_end_time_ns - self.context_start_time_ns

    @property
    def candidate_duration_ns(self) -> int:
        return self.candidate_end_time_ns - self.candidate_start_time_ns

    def frame_fraction(self, frame: int) -> float:
        if (
            type(frame) is not int
            or not self.context_start_frame <= frame <= self.context_end_frame
        ):
            raise ValueError("Source frame is outside the displayed context.")
        return (frame - self.context_start_frame) / self.frame_count


def plan_candidate_context(
    candidate: EligibleCandidate,
    *,
    context_seconds: int,
) -> CandidateContext:
    if type(context_seconds) is not int or context_seconds not in _CONTEXT_CHOICES:
        raise ValueError("Spectrogram context must be 1, 2, or 3 seconds on each side.")
    margin = context_seconds * candidate.sample_rate_hz
    context_start = max(0, candidate.start_frame - margin)
    context_end = min(candidate.frame_count, candidate.end_frame + margin)
    return CandidateContext(
        candidate_id=candidate.candidate_id,
        recording_key=candidate.recording_key,
        source_sha256=candidate.source_sha256,
        sample_rate_hz=candidate.sample_rate_hz,
        channels=candidate.channels,
        source_frame_count=candidate.frame_count,
        context_start_frame=context_start,
        context_end_frame=context_end,
        candidate_start_frame=candidate.start_frame,
        candidate_end_frame=candidate.end_frame,
    )


@dataclass(frozen=True, slots=True)
class ResolvedSpectrogramPlan:
    requested_window_samples: int
    window_samples: int
    n_fft: int
    hop_samples: int
    frequency_min_hz: int
    frequency_max_hz: float
    short_clip_window: bool


@dataclass(frozen=True, slots=True)
class SpectrogramSettings:
    frequency_max_hz: int = 4_200
    sound_detail: SoundDetail = SoundDetail.BALANCED
    context_seconds: int = 2
    contrast_db: int = 50
    palette: Palette = Palette.MAGMA
    exact_window_ms: int | None = None
    overlap_percent: int = 50
    frequency_min_hz: int = 0

    def __post_init__(self) -> None:
        if type(self.frequency_max_hz) is not int or self.frequency_max_hz not in (
            _FREQUENCY_MAX_CHOICES
        ):
            raise ValueError("Spectrogram frequency ceiling is unsupported.")
        if not isinstance(self.sound_detail, SoundDetail):
            raise TypeError("Spectrogram sound detail is invalid.")
        if type(self.context_seconds) is not int or self.context_seconds not in _CONTEXT_CHOICES:
            raise ValueError("Spectrogram context is unsupported.")
        if type(self.contrast_db) is not int or self.contrast_db not in _CONTRAST_CHOICES:
            raise ValueError("Spectrogram contrast is unsupported.")
        if not isinstance(self.palette, Palette):
            raise TypeError("Spectrogram palette is invalid.")
        if self.exact_window_ms is not None and (
            type(self.exact_window_ms) is not int
            or self.exact_window_ms not in _EXACT_WINDOW_CHOICES
        ):
            raise ValueError("Exact sound window is unsupported.")
        if type(self.overlap_percent) is not int or self.overlap_percent not in _OVERLAP_CHOICES:
            raise ValueError("Spectrogram overlap is unsupported.")
        if type(self.frequency_min_hz) is not int or self.frequency_min_hz not in (
            _FREQUENCY_MIN_CHOICES
        ):
            raise ValueError("Spectrogram low-frequency floor is unsupported.")
        if self.frequency_min_hz >= self.frequency_max_hz:
            raise ValueError("Spectrogram frequency floor must be below its ceiling.")

    def resolve(self, *, sample_rate_hz: int, available_frames: int) -> ResolvedSpectrogramPlan:
        sample_rate_hz = _positive_int(sample_rate_hz, "Sample rate")
        available_frames = _positive_int(available_frames, "Available audio frames")
        if self.exact_window_ms is not None:
            requested_window = max(
                1,
                (self.exact_window_ms * sample_rate_hz + 500) // 1_000,
            )
        else:
            historical_samples = {
                SoundDetail.FAST_CHANGES: 1_000,
                SoundDetail.BALANCED: 2_000,
                SoundDetail.CLOSE_PITCHES: 4_000,
            }[self.sound_detail]
            requested_window = max(
                1,
                (historical_samples * sample_rate_hz + 24_000) // 48_000,
            )
        window = min(requested_window, available_frames)
        n_fft = 1 << max(0, window - 1).bit_length()
        hop = max(1, window * (100 - self.overlap_percent) // 100)
        nyquist = sample_rate_hz / 2
        frequency_max = min(float(self.frequency_max_hz), nyquist)
        if self.frequency_min_hz >= frequency_max:
            raise ValueError("Selected frequency range is unavailable at this sample rate.")
        return ResolvedSpectrogramPlan(
            requested_window_samples=requested_window,
            window_samples=window,
            n_fft=n_fft,
            hop_samples=hop,
            frequency_min_hz=self.frequency_min_hz,
            frequency_max_hz=frequency_max,
            short_clip_window=window != requested_window,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "frequency_max_hz": self.frequency_max_hz,
            "sound_detail": self.sound_detail.value,
            "context_seconds": self.context_seconds,
            "contrast_db": self.contrast_db,
            "palette": self.palette.value,
            "exact_window_ms": self.exact_window_ms,
            "overlap_percent": self.overlap_percent,
            "frequency_min_hz": self.frequency_min_hz,
        }

    @classmethod
    def from_mapping(cls, value: object) -> SpectrogramSettings:
        required = {
            "frequency_max_hz",
            "sound_detail",
            "context_seconds",
            "contrast_db",
            "palette",
            "exact_window_ms",
            "overlap_percent",
            "frequency_min_hz",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Spectrogram settings document is unsupported.")
        try:
            sound_detail = SoundDetail(value["sound_detail"])
            palette = Palette(value["palette"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Spectrogram settings document is unsupported.") from exc
        return cls(
            frequency_max_hz=value["frequency_max_hz"],
            sound_detail=sound_detail,
            context_seconds=value["context_seconds"],
            contrast_db=value["contrast_db"],
            palette=palette,
            exact_window_ms=value["exact_window_ms"],
            overlap_percent=value["overlap_percent"],
            frequency_min_hz=value["frequency_min_hz"],
        )


@dataclass(frozen=True, slots=True)
class SpectrogramMetadata:
    algorithm_version: str
    render_version: str
    source_sha256: str
    candidate_id: str
    sample_rate_hz: int
    channels: int
    source_frame_count: int
    channel_policy: str
    dc_policy: str
    context_start_frame: int
    context_end_frame: int
    candidate_start_frame: int
    candidate_end_frame: int
    window_samples: int
    requested_window_samples: int
    n_fft: int
    hop_samples: int
    window_function: str
    frame_centers_x2: tuple[int, ...]
    frequency_centers_hz: tuple[float, ...]
    frequency_edges_hz: tuple[float, ...]
    frequency_min_hz: float
    frequency_max_hz: float
    width: int
    height: int
    tier: SpectrogramImageTier
    palette: Palette
    contrast_db: int
    settings_json: str
    amplitude_scaling: str
    frequency_scale: str
    interpolation: str
    orientation: str
    short_clip_window: bool

    @property
    def context_frame_count(self) -> int:
        return self.context_end_frame - self.context_start_frame

    @property
    def candidate_x_edges(self) -> tuple[float, float]:
        return (
            (self.candidate_start_frame - self.context_start_frame) / self.context_frame_count,
            (self.candidate_end_frame - self.context_start_frame) / self.context_frame_count,
        )

    def frame_fraction(self, frame: int) -> float:
        if (
            type(frame) is not int
            or not self.context_start_frame <= frame <= self.context_end_frame
        ):
            raise ValueError("Source frame is outside spectrogram metadata.")
        return (frame - self.context_start_frame) / self.context_frame_count

    def frequency_fraction(self, frequency_hz: float) -> float:
        if not isinstance(frequency_hz, (int, float)) or not math.isfinite(frequency_hz):
            raise ValueError("Frequency is invalid.")
        if not self.frequency_min_hz <= frequency_hz <= self.frequency_max_hz:
            raise ValueError("Frequency is outside spectrogram metadata.")
        return (frequency_hz - self.frequency_min_hz) / (
            self.frequency_max_hz - self.frequency_min_hz
        )


@dataclass(frozen=True, slots=True)
class SpectrogramRaster:
    content_key: str
    width: int
    height: int
    rgb_bytes: bytes
    relative_db_f32: bytes
    metadata: SpectrogramMetadata

    def __post_init__(self) -> None:
        validate_spectrogram_content_key(self.content_key)
        if self.width != self.metadata.width or self.height != self.metadata.height:
            raise ValueError("Spectrogram raster dimensions do not match metadata.")
        if len(self.rgb_bytes) != self.width * self.height * 3:
            raise ValueError("Spectrogram RGB payload is incomplete.")
        if len(self.relative_db_f32) != self.width * self.height * 4:
            raise ValueError("Spectrogram dB payload is incomplete.")

    @property
    def relative_db(self) -> memoryview:
        return memoryview(self.relative_db_f32).cast("f")


def validate_spectrogram_content_key(value: object) -> str:
    if not isinstance(value, str) or _CONTENT_KEY.fullmatch(value) is None:
        raise ValueError("Spectrogram content identity is invalid.")
    return value


__all__ = [
    "CHANNEL_POLICY",
    "SPECTROGRAM_ALGORITHM_VERSION",
    "SPECTROGRAM_RENDER_VERSION",
    "CandidateContext",
    "Palette",
    "ResolvedSpectrogramPlan",
    "SoundDetail",
    "SpectrogramImageTier",
    "SpectrogramMetadata",
    "SpectrogramRaster",
    "SpectrogramSettings",
    "plan_candidate_context",
    "validate_spectrogram_content_key",
]
