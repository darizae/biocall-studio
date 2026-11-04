"""Bounded, source-exact PCM WAV context reads for Review."""

from __future__ import annotations

import hashlib
import io
import os
import wave
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np

from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.spectrograms import CandidateContext, plan_candidate_context

_READ_CHUNK_BYTES = 256 * 1024
_MAX_DISPLAY_SECONDS = 30
_MAX_CONTEXT_BYTES = 64 * 1024 * 1024


class AudioSourceProblem(StrEnum):
    MISSING = "missing"
    UNSAFE = "unsafe"
    CHANGED = "changed"
    UNSUPPORTED = "unsupported"
    TRUNCATED = "truncated"
    CANCELLED = "cancelled"


class AudioSourceError(ValueError):
    """Structured WAV failure that callers can map to approved researcher copy."""

    def __init__(self, problem: AudioSourceProblem, message: str):
        super().__init__(message)
        self.problem = problem


@dataclass(frozen=True, slots=True)
class CandidateAudio:
    context: CandidateContext
    sample_width_bytes: int
    samples: np.ndarray
    wav_bytes: bytes

    def __post_init__(self) -> None:
        if type(self.sample_width_bytes) is not int or not 1 <= self.sample_width_bytes <= 4:
            raise ValueError("Candidate audio sample width is invalid.")
        if self.samples.shape != (self.context.channels, self.context.frame_count):
            raise ValueError("Candidate audio samples do not match context metadata.")
        if self.samples.flags.writeable:
            raise ValueError("Candidate audio samples must be read-only.")
        if not self.wav_bytes.startswith(b"RIFF") or b"WAVE" not in self.wav_bytes[:16]:
            raise ValueError("Candidate playback clip is not a WAV payload.")


def _cancelled(check: Callable[[], bool] | None) -> None:
    if check is not None and check():
        raise AudioSourceError(AudioSourceProblem.CANCELLED, "Candidate audio read was cancelled.")


def _resolve_source(source_root: Path, recording_key: str) -> Path:
    requested_root = Path(source_root).expanduser()
    if requested_root.is_symlink():
        raise AudioSourceError(AudioSourceProblem.UNSAFE, "Recording root is a symbolic link.")
    try:
        root = requested_root.resolve(strict=True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise AudioSourceError(
            AudioSourceProblem.MISSING, "Recording root is unavailable."
        ) from exc
    if not root.is_dir():
        raise AudioSourceError(AudioSourceProblem.UNSAFE, "Recording root is not a directory.")
    relative = Path(recording_key)
    if relative.is_absolute() or ".." in relative.parts:
        raise AudioSourceError(AudioSourceProblem.UNSAFE, "Recording reference is unsafe.")
    source = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AudioSourceError(AudioSourceProblem.UNSAFE, "Recording path contains a link.")
    try:
        resolved = source.resolve(strict=True)
    except FileNotFoundError as exc:
        raise AudioSourceError(AudioSourceProblem.MISSING, "Recording was not found.") from exc
    except (PermissionError, OSError) as exc:
        raise AudioSourceError(AudioSourceProblem.MISSING, "Recording is unavailable.") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AudioSourceError(
            AudioSourceProblem.UNSAFE, "Recording path escapes its source root."
        ) from exc
    if not resolved.is_file():
        raise AudioSourceError(AudioSourceProblem.UNSAFE, "Recording path is not a regular file.")
    return resolved


def _hash_stream(stream, cancelled: Callable[[], bool] | None) -> str:
    digest = hashlib.sha256()
    while True:
        _cancelled(cancelled)
        chunk = stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _decode_pcm(payload: bytes, *, sample_width: int, channels: int) -> np.ndarray:
    bytes_per_frame = sample_width * channels
    if len(payload) % bytes_per_frame:
        raise AudioSourceError(
            AudioSourceProblem.TRUNCATED,
            "PCM payload does not contain complete source frames.",
        )
    if sample_width == 1:
        values = (np.frombuffer(payload, dtype=np.uint8).astype(np.float64) - 128) / 128
    elif sample_width == 2:
        values = np.frombuffer(payload, dtype="<i2").astype(np.float64) / 32_768
    elif sample_width == 3:
        octets = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        signed = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        signed = (signed ^ (1 << 23)) - (1 << 23)
        values = signed.astype(np.float64) / (1 << 23)
    elif sample_width == 4:
        values = np.frombuffer(payload, dtype="<i4").astype(np.float64) / (1 << 31)
    else:
        raise AudioSourceError(AudioSourceProblem.UNSUPPORTED, "PCM sample width is unsupported.")
    frames = values.reshape(-1, channels)
    samples = np.ascontiguousarray(frames.T)
    samples.setflags(write=False)
    return samples


def _playback_wav(
    payload: bytes,
    *,
    channels: int,
    sample_width: int,
    sample_rate: int,
) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(sample_rate)
        target.writeframes(payload)
    return output.getvalue()


def read_candidate_audio(
    source_root: Path,
    candidate: EligibleCandidate,
    *,
    context_seconds: int,
    cancelled: Callable[[], bool] | None = None,
) -> CandidateAudio:
    """Verify a source and read only the exact clamped candidate context.

    The returned in-memory WAV retains the original channel/sample encoding and
    is solely a playback clip. Candidate export boundaries remain the immutable
    original ``start_frame``/``end_frame`` on ``EligibleCandidate``.
    """

    context = plan_candidate_context(candidate, context_seconds=context_seconds)
    if context.frame_count > context.sample_rate_hz * _MAX_DISPLAY_SECONDS:
        raise AudioSourceError(
            AudioSourceProblem.UNSUPPORTED,
            "Candidate context exceeds the bounded Review display duration.",
        )
    source = _resolve_source(Path(source_root), candidate.recording_key)
    try:
        with source.open("rb", buffering=0) as raw:
            before = os.fstat(raw.fileno())
            source_digest = _hash_stream(raw, cancelled)
            if source_digest != candidate.source_sha256:
                raise AudioSourceError(
                    AudioSourceProblem.CHANGED,
                    "Recording content does not match the frozen Detect source.",
                )
            raw.seek(0)
            try:
                reader_context = wave.open(raw, "rb")
            except (EOFError, wave.Error) as exc:
                raise AudioSourceError(
                    AudioSourceProblem.UNSUPPORTED,
                    "Recording is not a supported uncompressed PCM WAV.",
                ) from exc
            with reader_context as reader:
                if reader.getcomptype() != "NONE":
                    raise AudioSourceError(
                        AudioSourceProblem.UNSUPPORTED,
                        "Recording is not an uncompressed PCM WAV.",
                    )
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                sample_rate = reader.getframerate()
                source_frames = reader.getnframes()
                if channels != candidate.channels or not 1 <= channels <= 8:
                    raise AudioSourceError(
                        AudioSourceProblem.CHANGED,
                        "Recording channel facts changed after detection.",
                    )
                if (
                    sample_rate != candidate.sample_rate_hz
                    or source_frames != candidate.frame_count
                ):
                    raise AudioSourceError(
                        AudioSourceProblem.CHANGED,
                        "Recording frame or sample-rate facts changed after detection.",
                    )
                if sample_width not in (1, 2, 3, 4):
                    raise AudioSourceError(
                        AudioSourceProblem.UNSUPPORTED,
                        "Recording PCM sample width is unsupported.",
                    )
                payload_size = context.frame_count * channels * sample_width
                if payload_size > _MAX_CONTEXT_BYTES:
                    raise AudioSourceError(
                        AudioSourceProblem.UNSUPPORTED,
                        "Candidate context exceeds the bounded Review memory limit.",
                    )
                reader.setpos(context.context_start_frame)
                remaining = context.frame_count
                bytes_per_frame = channels * sample_width
                parts: list[bytes] = []
                chunk_frames = max(1, _READ_CHUNK_BYTES // bytes_per_frame)
                while remaining:
                    _cancelled(cancelled)
                    requested = min(remaining, chunk_frames)
                    chunk = reader.readframes(requested)
                    actual = len(chunk) // bytes_per_frame
                    if actual != requested or len(chunk) % bytes_per_frame:
                        raise AudioSourceError(
                            AudioSourceProblem.TRUNCATED,
                            "Recording ended before the requested context was read.",
                        )
                    parts.append(chunk)
                    remaining -= actual
            payload = b"".join(parts)
            raw.seek(0)
            verified_digest = _hash_stream(raw, cancelled)
            after = os.fstat(raw.fileno())
        path_after = source.stat()
    except AudioSourceError:
        raise
    except FileNotFoundError as exc:
        raise AudioSourceError(
            AudioSourceProblem.MISSING, "Recording disappeared while reading."
        ) from exc
    except (PermissionError, OSError) as exc:
        raise AudioSourceError(AudioSourceProblem.MISSING, "Recording could not be read.") from exc
    stable_file = (
        before.st_dev == after.st_dev == path_after.st_dev
        and before.st_ino == after.st_ino == path_after.st_ino
        and before.st_size == after.st_size == path_after.st_size
        and before.st_mtime_ns == after.st_mtime_ns == path_after.st_mtime_ns
    )
    if not stable_file or verified_digest != source_digest:
        raise AudioSourceError(
            AudioSourceProblem.CHANGED,
            "Recording changed while its context was being read.",
        )
    samples = _decode_pcm(payload, sample_width=sample_width, channels=channels)
    return CandidateAudio(
        context=context,
        sample_width_bytes=sample_width,
        samples=samples,
        wav_bytes=_playback_wav(
            payload,
            channels=channels,
            sample_width=sample_width,
            sample_rate=sample_rate,
        ),
    )


__all__ = [
    "AudioSourceError",
    "AudioSourceProblem",
    "CandidateAudio",
    "read_candidate_audio",
]
