"""Bounded PCM WAV segment extraction used by Dataset Build."""

from __future__ import annotations

import hashlib
import os
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

AUDIO_TRANSFORM_POLICY = "pcm-preserve-nearest-frame-v1"
IO_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class ExtractedAudio:
    start_frame: int
    end_frame: int
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int

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


def sha256_file(path: Path, *, cancelled: Callable[[], bool] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(IO_CHUNK_BYTES):
            if cancelled is not None and cancelled():
                raise InterruptedError("Dataset Build cancelled.")
            digest.update(chunk)
    return digest.hexdigest()


def _millisecond_frame(milliseconds: int, sample_rate_hz: int) -> int:
    return (milliseconds * sample_rate_hz + 500) // 1_000


def extract_pcm_segment(
    source: Path,
    destination: Path,
    *,
    start_ms: int,
    end_ms: int,
    cancelled: Callable[[], bool] | None = None,
) -> ExtractedAudio:
    """Seek-read one half-open source interval and preserve its PCM representation."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Audio segment source-time interval is invalid.")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Snippet WAV: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(source), "rb") as input_wav:
            if input_wav.getcomptype() != "NONE":
                raise ValueError("Only uncompressed PCM WAV input is supported.")
            channels = input_wav.getnchannels()
            sample_width = input_wav.getsampwidth()
            sample_rate = input_wav.getframerate()
            source_frames = input_wav.getnframes()
            start_frame = _millisecond_frame(start_ms, sample_rate)
            end_frame = _millisecond_frame(end_ms, sample_rate)
            if start_frame < 0 or end_frame <= start_frame or end_frame > source_frames:
                raise ValueError("Audio segment frame interval is outside the Source Recording.")
            input_wav.setpos(start_frame)
            frames_remaining = end_frame - start_frame
            bytes_per_frame = channels * sample_width
            chunk_frames = max(1, IO_CHUNK_BYTES // bytes_per_frame)
            with wave.open(str(destination), "wb") as output_wav:
                output_wav.setnchannels(channels)
                output_wav.setsampwidth(sample_width)
                output_wav.setframerate(sample_rate)
                while frames_remaining:
                    if cancelled is not None and cancelled():
                        raise InterruptedError("Dataset Build cancelled.")
                    count = min(chunk_frames, frames_remaining)
                    payload = input_wav.readframes(count)
                    actual_frames = len(payload) // bytes_per_frame
                    if actual_frames != count:
                        raise ValueError("Source Recording ended before the requested interval.")
                    output_wav.writeframesraw(payload)
                    frames_remaining -= actual_frames
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    with destination.open("r+b") as stream:
        os.fsync(stream.fileno())
    return ExtractedAudio(
        start_frame,
        end_frame,
        sample_rate,
        channels,
        sample_width,
        end_frame - start_frame,
    )
