"""Qt-free Collection Scan facts and validation decisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

MAX_TIMESTAMP_MS = 2**63 - 1
_POSITIVE_NAME = re.compile(
    r"^(?P<source>.+)__start-(?P<start>[0-9]+)ms__end-(?P<end>[0-9]+)ms__"
    r"(?P<label>[^/\\]+)\.wav$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PositiveName:
    source_stem: str
    start_ms: int
    end_ms: int
    label: str


@dataclass(frozen=True)
class WavHeader:
    codec: str
    channels: int
    sample_rate_hz: int
    sample_width_bytes: int
    frame_count: int

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate_hz if self.sample_rate_hz else 0.0


@dataclass(frozen=True)
class Fingerprint:
    size_bytes: int
    mtime_ns: int
    header: WavHeader


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class SourceRecording:
    id: str
    relative_path: str
    fingerprint: Fingerprint
    positive_count: int = 0

    @property
    def name(self) -> str:
        return self.relative_path.rsplit("/", 1)[-1]

    @property
    def stem(self) -> str:
        return self.name[:-4]


@dataclass(frozen=True)
class PositiveExample:
    relative_path: str
    source_recording_id: str | None
    start_ms: int | None
    end_ms: int | None
    label: str | None
    fingerprint: Fingerprint | None


@dataclass(frozen=True)
class CollectionIssue:
    code: str
    relative_path: str
    message: str
    correction: str


@dataclass(frozen=True)
class InventoryChanges:
    added: set[str]
    removed: set[str]
    changed: set[str]
    unchanged: set[str]
    cache_state: str


@dataclass(frozen=True)
class ScanResult:
    root_name: str
    records: tuple[SourceRecording, ...]
    positives: tuple[PositiveExample, ...]
    issues: tuple[CollectionIssue, ...]
    inventory: tuple[InventoryEntry, ...]
    header_reads: int = 0
    collection_id: str | None = None
    scanned_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def valid(self) -> bool:
        return not self.issues

    @property
    def recording_count(self) -> int:
        return len(self.records)

    @property
    def positive_count(self) -> int:
        return len(self.positives)

    @property
    def duration_seconds(self) -> float:
        return sum(record.fingerprint.header.duration_seconds for record in self.records)

    @property
    def relative_paths(self) -> tuple[str, ...]:
        return tuple(entry.relative_path for entry in self.inventory)


def parse_positive_filename(filename: str) -> PositiveName:
    """Parse the one supported positive basename grammar."""
    match = _POSITIVE_NAME.fullmatch(filename)
    if match is None:
        raise ValueError(
            "Positive WAV name must match <source>__start-<integer>ms__end-<integer>ms__<label>.wav"
        )
    source = match.group("source")
    label = match.group("label")
    if not source or "__start-" in source.casefold() or not label.strip():
        raise ValueError("Positive WAV source stem and label must be nonempty and unambiguous.")
    start_ms = int(match.group("start"), 10)
    end_ms = int(match.group("end"), 10)
    if start_ms > MAX_TIMESTAMP_MS or end_ms > MAX_TIMESTAMP_MS:
        raise ValueError("Positive WAV timestamp exceeds the supported integer range.")
    return PositiveName(source, start_ms, end_ms, label)


def validate_source_match(source_stem: str, sources: Mapping[str, object]) -> object:
    """Resolve only an exact unique Source Recording stem."""
    if source_stem not in sources:
        raise ValueError(f"Unknown Source Recording: {source_stem}.wav")
    match = sources[source_stem]
    if isinstance(match, tuple) and len(match) != 1:
        raise ValueError(f"Ambiguous Source Recording: {source_stem}.wav")
    return match[0] if isinstance(match, tuple) else match


def ensure_unique_interval(
    source_recording_id: str, start_ms: int, end_ms: int, seen: set[tuple[str, int, int]]
) -> None:
    interval = (source_recording_id, start_ms, end_ms)
    if interval in seen:
        raise ValueError("Duplicate positive interval for this Source Recording.")
    seen.add(interval)


def validate_wav_header(header: WavHeader) -> None:
    """Accept bounded PCM WAV facts used by the current native reader."""
    if header.codec != "PCM":
        raise ValueError(f"Unsupported WAV codec: {header.codec}.")
    if header.channels not in {1, 2}:
        raise ValueError("Unsupported WAV channel count; use mono or stereo PCM.")
    if header.sample_rate_hz <= 0:
        raise ValueError("Invalid WAV sample rate.")
    if header.sample_width_bytes not in {1, 2, 3, 4}:
        raise ValueError("Unsupported WAV sample width.")
    if header.frame_count <= 0:
        raise ValueError("Invalid or empty WAV audio data.")


def validate_interval(
    start_ms: int,
    end_ms: int,
    source_header: WavHeader,
    positive_header: WavHeader,
) -> None:
    """Validate half-open source time and a two-frame quantization tolerance."""
    if start_ms < 0 or start_ms >= end_ms:
        raise ValueError("Positive start must be nonnegative and start must be earlier than end.")
    if end_ms * source_header.sample_rate_hz > source_header.frame_count * 1_000:
        raise ValueError("Positive interval is outside Source Recording duration.")
    expected_scaled_frames = (end_ms - start_ms) * positive_header.sample_rate_hz
    actual_scaled_frames = positive_header.frame_count * 1_000
    if abs(actual_scaled_frames - expected_scaled_frames) > 2_000:
        raise ValueError("Positive WAV duration disagrees with its filename interval.")


def compare_inventories(
    cached: Mapping[str, InventoryEntry] | None,
    current: Mapping[str, InventoryEntry],
    *,
    cache_valid: bool = True,
) -> InventoryChanges:
    if cached is None:
        return InventoryChanges(set(current), set(), set(), set(), "absent")
    if not cache_valid:
        return InventoryChanges(set(current), set(cached), set(), set(), "corrupt")
    old_paths = set(cached)
    new_paths = set(current)
    common = old_paths & new_paths
    unchanged = {path for path in common if cached[path] == current[path]}
    changed = common - unchanged
    state = "fresh" if not (new_paths - old_paths or old_paths - new_paths or changed) else "stale"
    return InventoryChanges(new_paths - old_paths, old_paths - new_paths, changed, unchanged, state)
