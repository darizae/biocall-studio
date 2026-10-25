"""Trainer policy adapter for reusable toolbox PCM WAV extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from bioacoustics_dl_toolbox.audio import (
    PcmExtractionCancelled,
    PcmSegmentFacts,
    extract_pcm_wav_segment,
)

AUDIO_TRANSFORM_POLICY = "pcm-preserve-nearest-frame-v1"
TOOLBOX_DISTRIBUTION = "bioacoustics-dl-toolbox"
TOOLBOX_VERSION = version(TOOLBOX_DISTRIBUTION)
TOOLBOX_SOURCE_REVISION = "0fce0d4fa3d0931c5731e8b868f705e0a2120835"


class AudioExtractionCancelled(InterruptedError):
    """Application-owned cancellation raised across the Dataset Build seam."""


def audio_extraction_provenance() -> dict[str, str]:
    return {
        "distribution": TOOLBOX_DISTRIBUTION,
        "version": TOOLBOX_VERSION,
        "revision": TOOLBOX_SOURCE_REVISION,
        "api": "bioacoustics_dl_toolbox.audio.extract_pcm_wav_segment",
    }


def _nearest_frame(milliseconds: int, sample_rate_hz: int) -> int:
    return (milliseconds * sample_rate_hz + 500) // 1_000


@dataclass(frozen=True)
class DatasetAudioTransform:
    start_frame: int
    end_frame: int
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int

    @classmethod
    def from_facts(
        cls,
        facts: PcmSegmentFacts,
        *,
        start_ms: int,
        end_ms: int,
    ) -> DatasetAudioTransform:
        values = (
            facts.start_frame,
            facts.end_frame,
            facts.sample_rate_hz,
            facts.channels,
            facts.sample_width_bytes,
            facts.frame_count,
        )
        if any(type(value) is not int for value in values):
            raise ValueError("Toolbox PCM extraction facts are invalid.")
        expected_start = _nearest_frame(start_ms, facts.sample_rate_hz)
        expected_end = _nearest_frame(end_ms, facts.sample_rate_hz)
        if (
            start_ms < 0
            or end_ms <= start_ms
            or facts.start_frame != expected_start
            or facts.end_frame != expected_end
            or facts.start_frame < 0
            or facts.end_frame <= facts.start_frame
            or facts.frame_count != facts.end_frame - facts.start_frame
            or facts.sample_rate_hz <= 0
            or facts.channels not in {1, 2}
            or facts.sample_width_bytes not in {1, 2, 3, 4}
        ):
            raise ValueError("Toolbox PCM extraction facts do not match Trainer policy.")
        return cls(*values)

    def to_dict(self) -> dict[str, int | str]:
        return {
            "policy": AUDIO_TRANSFORM_POLICY,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
        }


def extract_dataset_audio(
    source: Path,
    destination: Path,
    *,
    start_ms: int,
    end_ms: int,
    cancelled: Callable[[], bool] | None = None,
) -> DatasetAudioTransform:
    try:
        facts = extract_pcm_wav_segment(
            source,
            destination,
            start_ms=start_ms,
            end_ms=end_ms,
            cancelled=cancelled,
        )
    except PcmExtractionCancelled as exc:
        raise AudioExtractionCancelled("Dataset Build audio extraction cancelled.") from exc
    try:
        return DatasetAudioTransform.from_facts(
            facts,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
