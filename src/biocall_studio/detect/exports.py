"""Frozen, PCM-preserving corpus export and atomic publication."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import unicodedata
import uuid
import wave
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from enum import StrEnum
from pathlib import Path, PurePosixPath

from biocall_studio.detect.domain import validate_relative_reference
from biocall_studio.detect.result_views import FrozenResultSelection
from biocall_studio.detect.rf_refinement import DerivedResult, ResultArtifact
from biocall_studio.detect.runs import canonical_digest, utc_now

EXPORT_SNAPSHOT_SCHEMA_VERSION = 1
EXPORT_RECEIPT_SCHEMA_VERSION = 1
FORMAT_POLICY = (
    "pcm-preserve-v1; snippets retain source sample rate, channels, sample width and PCM; "
    "concatenation requires identical PCM formats and mono audio; no resampling or downmix; "
    "gap_frames=0"
)
COLLISION_POLICY = "publish-new-directory; fail-if-name-exists; never-overwrite"
RAVEN_REFERENCE = (
    "Cornell Raven default selection-table columns; tab-separated seconds relative to the "
    "concatenated WAV; provenance columns follow the seven default columns"
)
RAVEN_REFERENCE_URL = (
    "https://www.ravensoundsoftware.com/knowledge-base/error-opening-selection-table/"
)
MAX_EXPORT_CANDIDATES = 10_000
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_COPY_BYTES = 1024 * 1024
_EXPORT_ID = re.compile(r"exp_[0-9a-f]{32}")
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}")
_RECORDING_ID = re.compile(r"rec_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class ExportMode(StrEnum):
    SNIPPETS = "snippets"
    CONCAT = "concat"
    BOTH = "both"

    @property
    def includes_snippets(self) -> bool:
        return self in {ExportMode.SNIPPETS, ExportMode.BOTH}

    @property
    def includes_concat(self) -> bool:
        return self in {ExportMode.CONCAT, ExportMode.BOTH}


class ExportState(StrEnum):
    READY = "ready"
    RUNNING = "running"
    CONFLICT = "conflict"
    STALE = "stale"
    CANCELLED = "cancelled"
    ERROR = "error"
    SUCCESS = "success"


class ExportError(RuntimeError):
    """An export cannot be safely completed."""


class ExportConflictError(ExportError):
    """The collision-safe publication name already exists."""


class ExportStaleSourceError(ExportError):
    """A source no longer matches the frozen Result."""


class ExportCancelledError(ExportError):
    """The user cancelled before publication."""


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _utc(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be UTC.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be UTC.")
    return value


def _relative_path(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid.")
    normalized = validate_relative_reference(value)
    if normalized != value:
        raise ValueError(f"{label} is not normalized.")
    return value


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_COPY_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_seconds(frame: int, sample_rate_hz: int) -> str:
    """Format a frame boundary as decimal seconds with an exact frame round-trip."""
    if (
        type(frame) is not int
        or frame < 0
        or type(sample_rate_hz) is not int
        or sample_rate_hz <= 0
    ):
        raise ValueError("Frame time inputs are invalid.")
    if frame == 0:
        return "0"
    with localcontext() as context:
        context.prec = 60
        seconds = Decimal(frame) / Decimal(sample_rate_hz)
        for places in range(12, 19):
            rendered = format(seconds, f".{places}f").rstrip("0").rstrip(".")
            recovered = (Decimal(rendered) * sample_rate_hz).to_integral_value(
                rounding=ROUND_HALF_UP
            )
            if recovered == frame:
                return rendered
    raise ValueError("Frame boundary cannot be represented without rounding drift.")


def _frame_nanoseconds(frame: int, sample_rate_hz: int) -> int:
    return (frame * 1_000_000_000 + sample_rate_hz // 2) // sample_rate_hz


def _frequency(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def _safe_stem(recording_key: str) -> str:
    source_name = PurePosixPath(recording_key).name
    stem = source_name.rsplit(".", 1)[0] if "." in source_name else source_name
    normalized = unicodedata.normalize("NFC", stem)
    safe = "".join(
        "_" if character in '<>:"/\\|?*' or ord(character) < 32 else character
        for character in normalized
    ).strip(" .")
    safe = re.sub(r"\s+", "_", safe) or "recording"
    if safe.upper() in _WINDOWS_RESERVED:
        safe = f"{safe}_source"
    return safe[:72].rstrip(" .") or "recording"


def _snippet_name(recording_key: str, start_frame: int, end_frame: int, candidate_id: str) -> str:
    token = candidate_id.removeprefix("cand_")
    name = (
        f"{_safe_stem(recording_key)}__start-{start_frame:012d}f"
        f"__end-{end_frame:012d}f__{token}.wav"
    )
    return f"snippets/{name}"


def safe_snippet_relative_path(
    recording_key: str, start_frame: int, end_frame: int, candidate_id: str
) -> str:
    """Return the deterministic Windows-safe output name for one half-open interval."""
    if (
        not isinstance(recording_key, str)
        or type(start_frame) is not int
        or type(end_frame) is not int
        or not 0 <= start_frame < end_frame
        or not isinstance(candidate_id, str)
        or _CANDIDATE_ID.fullmatch(candidate_id) is None
    ):
        raise ValueError("Snippet naming inputs are invalid.")
    return _snippet_name(recording_key, start_frame, end_frame, candidate_id)


@dataclass(frozen=True, slots=True)
class SourceWaveFormat:
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    compression: str

    def __post_init__(self) -> None:
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.channels) is not int
            or self.channels <= 0
            or type(self.sample_width_bytes) is not int
            or not 1 <= self.sample_width_bytes <= 4
            or self.compression != "NONE"
        ):
            raise ValueError("Only finite-width uncompressed PCM WAV sources are supported.")

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "compression": self.compression,
        }

    @classmethod
    def from_dict(cls, raw: object) -> SourceWaveFormat:
        expected = {"sample_rate_hz", "channels", "sample_width_bytes", "compression"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Source WAV format document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ExportCandidate:
    candidate_id: str
    recording_ref: str
    recording_key: str
    source_sha256: str
    sample_rate_hz: int
    frame_count: int
    channels: int
    sample_width_bytes: int
    source_start_frame: int
    source_end_frame: int
    source_start_time_ns: int
    source_end_time_ns: int
    snippet_relative_path: str
    concat_start_frame: int | None
    concat_end_frame: int | None

    def __post_init__(self) -> None:
        if _CANDIDATE_ID.fullmatch(self.candidate_id) is None:
            raise ValueError("Export candidate ID is invalid.")
        if _RECORDING_ID.fullmatch(self.recording_ref) is None:
            raise ValueError("Export recording reference is invalid.")
        _relative_path(self.recording_key, "Export recording key")
        _digest(self.source_sha256, "Export source digest")
        if (
            type(self.sample_rate_hz) is not int
            or self.sample_rate_hz <= 0
            or type(self.frame_count) is not int
            or self.frame_count <= 0
            or type(self.channels) is not int
            or self.channels <= 0
            or type(self.sample_width_bytes) is not int
            or not 1 <= self.sample_width_bytes <= 4
            or type(self.source_start_frame) is not int
            or type(self.source_end_frame) is not int
            or not 0 <= self.source_start_frame < self.source_end_frame <= self.frame_count
            or type(self.source_start_time_ns) is not int
            or type(self.source_end_time_ns) is not int
            or not 0 <= self.source_start_time_ns < self.source_end_time_ns
            or self.source_start_time_ns
            != _frame_nanoseconds(self.source_start_frame, self.sample_rate_hz)
            or self.source_end_time_ns
            != _frame_nanoseconds(self.source_end_frame, self.sample_rate_hz)
        ):
            raise ValueError("Export source frame mapping is invalid.")
        _relative_path(self.snippet_relative_path, "Snippet output path")
        if not self.snippet_relative_path.startswith(
            "snippets/"
        ) or not self.snippet_relative_path.endswith(".wav"):
            raise ValueError("Snippet output path is invalid.")
        if (self.concat_start_frame is None) != (self.concat_end_frame is None):
            raise ValueError("Concatenated frame mapping is incomplete.")
        if self.concat_start_frame is not None and (
            type(self.concat_start_frame) is not int
            or type(self.concat_end_frame) is not int
            or self.concat_start_frame < 0
            or self.concat_end_frame - self.concat_start_frame != self.output_frame_count
        ):
            raise ValueError("Concatenated frame mapping is invalid.")

    @property
    def output_frame_count(self) -> int:
        return self.source_end_frame - self.source_start_frame

    @property
    def expected_pcm_bytes(self) -> int:
        return self.output_frame_count * self.channels * self.sample_width_bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "recording_ref": self.recording_ref,
            "recording_key": self.recording_key,
            "source_sha256": self.source_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "source_start_frame": self.source_start_frame,
            "source_end_frame": self.source_end_frame,
            "source_start_time_ns": self.source_start_time_ns,
            "source_end_time_ns": self.source_end_time_ns,
            "snippet_relative_path": self.snippet_relative_path,
            "concat_start_frame": self.concat_start_frame,
            "concat_end_frame": self.concat_end_frame,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ExportCandidate:
        expected = {
            "candidate_id",
            "recording_ref",
            "recording_key",
            "source_sha256",
            "sample_rate_hz",
            "frame_count",
            "channels",
            "sample_width_bytes",
            "source_start_frame",
            "source_end_frame",
            "source_start_time_ns",
            "source_end_time_ns",
            "snippet_relative_path",
            "concat_start_frame",
            "concat_end_frame",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Export candidate document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class RavenRow:
    selection: int
    candidate_id: str
    recording_key: str
    begin_frame: int
    end_frame: int
    begin_seconds: str
    end_seconds: str
    low_frequency_hz: str
    high_frequency_hz: str
    source_start_frame: int
    source_end_frame: int
    gap_frames: int

    def __post_init__(self) -> None:
        if (
            type(self.selection) is not int
            or self.selection <= 0
            or _CANDIDATE_ID.fullmatch(self.candidate_id) is None
            or type(self.begin_frame) is not int
            or type(self.end_frame) is not int
            or not 0 <= self.begin_frame < self.end_frame
            or type(self.gap_frames) is not int
            or self.gap_frames != 0
        ):
            raise ValueError("Raven row frame mapping is invalid.")
        _relative_path(self.recording_key, "Raven source key")
        for value in (
            self.begin_seconds,
            self.end_seconds,
            self.low_frequency_hz,
            self.high_frequency_hz,
        ):
            try:
                parsed = Decimal(value)
            except Exception as exc:
                raise ValueError("Raven row contains a nonnumeric bound.") from exc
            if not parsed.is_finite() or parsed < 0:
                raise ValueError("Raven row contains a nonnumeric bound.")

    def to_dict(self) -> dict[str, object]:
        return {
            "selection": self.selection,
            "candidate_id": self.candidate_id,
            "recording_key": self.recording_key,
            "begin_frame": self.begin_frame,
            "end_frame": self.end_frame,
            "begin_seconds": self.begin_seconds,
            "end_seconds": self.end_seconds,
            "low_frequency_hz": self.low_frequency_hz,
            "high_frequency_hz": self.high_frequency_hz,
            "source_start_frame": self.source_start_frame,
            "source_end_frame": self.source_end_frame,
            "gap_frames": self.gap_frames,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RavenRow:
        if not isinstance(raw, dict) or set(raw) != {
            "selection",
            "candidate_id",
            "recording_key",
            "begin_frame",
            "end_frame",
            "begin_seconds",
            "end_seconds",
            "low_frequency_hz",
            "high_frequency_hz",
            "source_start_frame",
            "source_end_frame",
            "gap_frames",
        }:
            raise ValueError("Raven row document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ExportSnapshot:
    schema_version: int
    export_id: str
    snapshot_digest: str
    created_at: str
    result_id: str
    result_digest: str
    result_kind: str
    parent_result_id: str | None
    parent_result_digest: str | None
    selection_revision: int
    selected_candidate_ids: tuple[str, ...]
    mode: ExportMode
    format_policy: str
    collision_policy: str
    destination_parent: str
    directory_name: str
    candidates: tuple[ExportCandidate, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EXPORT_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("Unsupported ExportSnapshot schema.")
        if _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("Export ID is invalid.")
        _digest(self.snapshot_digest, "ExportSnapshot digest")
        _utc(self.created_at, "ExportSnapshot creation time")
        if _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("ExportSnapshot Result ID is invalid.")
        _digest(self.result_digest, "ExportSnapshot Result digest")
        if self.result_kind not in {"original", "derived"}:
            raise ValueError("ExportSnapshot Result kind is invalid.")
        if self.result_kind == "original":
            if self.parent_result_id is not None or self.parent_result_digest is not None:
                raise ValueError("Original export cannot contain parent lineage.")
        elif (
            not isinstance(self.parent_result_id, str)
            or _RESULT_ID.fullmatch(self.parent_result_id) is None
            or not isinstance(self.parent_result_digest, str)
            or _SHA256.fullmatch(self.parent_result_digest) is None
        ):
            raise ValueError("Derived export requires parent lineage.")
        if type(self.selection_revision) is not int or self.selection_revision < 0:
            raise ValueError("Export selection revision is invalid.")
        if not isinstance(self.mode, ExportMode):
            raise ValueError("Export mode is invalid.")
        if self.format_policy != FORMAT_POLICY or self.collision_policy != COLLISION_POLICY:
            raise ValueError("Export format or collision policy is unsupported.")
        destination = Path(self.destination_parent)
        if not destination.is_absolute():
            raise ValueError("Export destination must be an absolute folder.")
        if self.directory_name != f"biocall-export-{self.export_id[4:16]}":
            raise ValueError("Export directory name is invalid.")
        if not self.candidates:
            raise ValueError("Export requires at least one selected interval.")
        if len(self.candidates) > MAX_EXPORT_CANDIDATES:
            raise ValueError(
                f"Export is limited to {MAX_EXPORT_CANDIDATES:,} intervals per publication."
            )
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if candidate_ids != self.selected_candidate_ids or len(set(candidate_ids)) != len(
            candidate_ids
        ):
            raise ValueError("Export candidate ordering does not match the frozen selection.")
        order = tuple(
            (candidate.recording_key, candidate.source_start_frame, candidate.source_end_frame)
            for candidate in self.candidates
        )
        if order != tuple(sorted(order)):
            raise ValueError("Export candidates must be in deterministic source order.")
        names = [
            unicodedata.normalize("NFC", candidate.snippet_relative_path).casefold()
            for candidate in self.candidates
        ]
        if len(names) != len(set(names)):
            raise ValueError("Export snippet names collide on Windows or normalized filesystems.")
        if self.mode.includes_concat:
            formats = {
                (
                    candidate.sample_rate_hz,
                    candidate.channels,
                    candidate.sample_width_bytes,
                )
                for candidate in self.candidates
            }
            if len(formats) != 1 or self.candidates[0].channels != 1:
                raise ValueError(
                    "Concatenated export requires one identical mono PCM format."
                )
            expected_start = 0
            for candidate in self.candidates:
                if candidate.concat_start_frame != expected_start:
                    raise ValueError("Concatenated offsets must be gap-free and ordered.")
                expected_start = candidate.concat_end_frame or -1
        elif any(candidate.concat_start_frame is not None for candidate in self.candidates):
            raise ValueError("Snippet-only export cannot contain concatenated offsets.")
        if canonical_digest(self._unsigned_dict()) != self.snapshot_digest:
            raise ValueError("ExportSnapshot digest does not match its immutable contents.")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "export_id": self.export_id,
            "created_at": self.created_at,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "result_kind": self.result_kind,
            "parent_result_id": self.parent_result_id,
            "parent_result_digest": self.parent_result_digest,
            "selection_revision": self.selection_revision,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "mode": self.mode.value,
            "format_policy": self.format_policy,
            "collision_policy": self.collision_policy,
            "destination_parent": self.destination_parent,
            "directory_name": self.directory_name,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "snapshot_digest": self.snapshot_digest}

    @classmethod
    def from_dict(cls, raw: object) -> ExportSnapshot:
        expected = {
            "schema_version",
            "export_id",
            "snapshot_digest",
            "created_at",
            "result_id",
            "result_digest",
            "result_kind",
            "parent_result_id",
            "parent_result_digest",
            "selection_revision",
            "selected_candidate_ids",
            "mode",
            "format_policy",
            "collision_policy",
            "destination_parent",
            "directory_name",
            "candidates",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw["selected_candidate_ids"], list)
            or not isinstance(raw["candidates"], list)
        ):
            raise ValueError("ExportSnapshot document is invalid.")
        values = dict(raw)
        values["selected_candidate_ids"] = tuple(raw["selected_candidate_ids"])
        values["mode"] = ExportMode(raw["mode"])
        values["candidates"] = tuple(ExportCandidate.from_dict(item) for item in raw["candidates"])
        return cls(**values)


def create_export_snapshot(
    *,
    result: ResultArtifact,
    selection: FrozenResultSelection,
    mode: ExportMode,
    destination_parent: Path,
    source_formats: Mapping[str, SourceWaveFormat],
    export_id: str,
    created_at: str,
) -> ExportSnapshot:
    """Create the pure immutable request after source WAV facts have been inspected."""
    mode = ExportMode(mode)
    if selection.result_id != result.result_id or selection.result_digest != result.result_digest:
        raise ValueError("Frozen selection does not match the chosen immutable Result.")
    expected_kind = "derived" if isinstance(result, DerivedResult) else "original"
    if selection.result_kind != expected_kind:
        raise ValueError("Frozen selection Result kind is inconsistent.")
    if not selection.candidate_ids:
        raise ValueError("Select at least one interval before exporting.")
    selected = set(selection.candidate_ids)
    rows = []
    concat_offset = 0
    selected_formats: list[SourceWaveFormat] = []
    for recording in result.recordings:
        source_format = source_formats.get(recording.recording_ref)
        selected_candidates = [
            candidate for candidate in recording.candidates if candidate.candidate_id in selected
        ]
        if not selected_candidates:
            continue
        if source_format is None:
            raise ValueError("A selected recording has no inspected PCM WAV format.")
        if (
            source_format.sample_rate_hz != recording.sample_rate_hz
            or source_format.channels != recording.channels
        ):
            raise ValueError("Inspected WAV format disagrees with the frozen Result.")
        selected_formats.append(source_format)
        for candidate in selected_candidates:
            length = candidate.end_frame - candidate.start_frame
            start = concat_offset if mode.includes_concat else None
            end = concat_offset + length if mode.includes_concat else None
            if mode.includes_concat:
                concat_offset += length
            rows.append(
                ExportCandidate(
                    candidate.candidate_id,
                    recording.recording_ref,
                    recording.recording_key,
                    recording.source_sha256,
                    recording.sample_rate_hz,
                    recording.frame_count,
                    recording.channels,
                    source_format.sample_width_bytes,
                    candidate.start_frame,
                    candidate.end_frame,
                    candidate.start_time_ns,
                    candidate.end_time_ns,
                    _snippet_name(
                        recording.recording_key,
                        candidate.start_frame,
                        candidate.end_frame,
                        candidate.candidate_id,
                    ),
                    start,
                    end,
                )
            )
    if {candidate.candidate_id for candidate in rows} != selected:
        raise ValueError("Frozen selection refers to a candidate outside the chosen Result.")
    rows.sort(key=lambda item: (item.recording_key, item.source_start_frame, item.source_end_frame))
    if mode.includes_concat:
        comparable = {
            (item.sample_rate_hz, item.channels, item.sample_width_bytes, item.compression)
            for item in selected_formats
        }
        if len(comparable) != 1:
            raise ValueError(
                "Concatenated export requires the same sample rate, channel count, and sample "
                "width for every selected recording. Choose snippets or a uniform selection."
            )
        if selected_formats[0].channels != 1:
            raise ValueError(
                "Raven concatenation currently requires mono PCM. Choose snippets for "
                "multi-channel selections; audio is never silently downmixed."
            )
        offset = 0
        mapped_rows = []
        for candidate in rows:
            mapped_rows.append(
                ExportCandidate(
                    **{
                        **candidate.to_dict(),
                        "concat_start_frame": offset,
                        "concat_end_frame": offset + candidate.output_frame_count,
                    }
                )
            )
            offset += candidate.output_frame_count
        rows = mapped_rows
    unsigned = {
        "schema_version": EXPORT_SNAPSHOT_SCHEMA_VERSION,
        "export_id": export_id,
        "created_at": created_at,
        "result_id": result.result_id,
        "result_digest": result.result_digest,
        "result_kind": expected_kind,
        "parent_result_id": selection.parent_result_id,
        "parent_result_digest": selection.parent_result_digest,
        "selection_revision": selection.selection_revision,
        "selected_candidate_ids": [candidate.candidate_id for candidate in rows],
        "mode": mode.value,
        "format_policy": FORMAT_POLICY,
        "collision_policy": COLLISION_POLICY,
        "destination_parent": str(Path(destination_parent)),
        "directory_name": f"biocall-export-{export_id[4:16]}",
        "candidates": [candidate.to_dict() for candidate in rows],
    }
    return ExportSnapshot(
        **{
            **unsigned,
            "snapshot_digest": canonical_digest(unsigned),
            "selected_candidate_ids": tuple(unsigned["selected_candidate_ids"]),
            "mode": mode,
            "candidates": tuple(rows),
        }
    )


def render_raven_tsv(snapshot: ExportSnapshot) -> tuple[bytes, tuple[RavenRow, ...]]:
    if not snapshot.mode.includes_concat:
        raise ValueError("A snippet-only export has no Raven selection table.")
    sample_rate = snapshot.candidates[0].sample_rate_hz
    high_frequency = _frequency(Decimal(sample_rate) / 2)
    rows = tuple(
        RavenRow(
            selection=index,
            candidate_id=candidate.candidate_id,
            recording_key=candidate.recording_key,
            begin_frame=candidate.concat_start_frame or 0,
            end_frame=candidate.concat_end_frame or 0,
            begin_seconds=frame_seconds(candidate.concat_start_frame or 0, sample_rate),
            end_seconds=frame_seconds(candidate.concat_end_frame or 0, sample_rate),
            low_frequency_hz="0",
            high_frequency_hz=high_frequency,
            source_start_frame=candidate.source_start_frame,
            source_end_frame=candidate.source_end_frame,
            gap_frames=0,
        )
        for index, candidate in enumerate(snapshot.candidates, 1)
    )
    header = (
        "Selection",
        "View",
        "Channel",
        "Begin Time (s)",
        "End Time (s)",
        "Low Freq (Hz)",
        "High Freq (Hz)",
        "Candidate ID",
        "Source File",
        "Source Begin Frame",
        "Source End Frame",
    )
    lines = ["\t".join(header)]
    lines.extend(
        "\t".join(
            (
                str(row.selection),
                "1",
                "1",
                row.begin_seconds,
                row.end_seconds,
                row.low_frequency_hz,
                row.high_frequency_hz,
                row.candidate_id,
                row.recording_key,
                str(row.source_start_frame),
                str(row.source_end_frame),
            )
        )
        for row in rows
    )
    return ("\n".join(lines) + "\n").encode(), rows


def ensure_publish_target_available(
    snapshot: ExportSnapshot, *, source_root: Path | None = None
) -> Path:
    parent = Path(snapshot.destination_parent)
    if parent.is_symlink() or not parent.is_dir():
        raise ExportError("Choose an existing, non-symlink export destination folder.")
    resolved_parent = parent.resolve(strict=True)
    if stat.S_IMODE(resolved_parent.stat().st_mode) & 0o222 == 0 or not os.access(
        resolved_parent, os.W_OK | os.X_OK
    ):
        raise ExportError("The export destination is not writable.")
    if source_root is not None:
        resolved_source = Path(source_root).resolve(strict=True)
        if resolved_parent == resolved_source or resolved_source in resolved_parent.parents:
            raise ExportError(
                "Choose a destination outside the recordings folder to prevent exported audio "
                "from entering later discovery."
            )
    final = resolved_parent / snapshot.directory_name
    if final.exists() or final.is_symlink():
        raise ExportConflictError(
            f"The collision-safe export folder already exists: {snapshot.directory_name}"
        )
    return final


@dataclass(frozen=True, slots=True)
class PublishedFile:
    relative_path: str
    kind: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        _relative_path(self.relative_path, "Published file path")
        if self.kind not in {
            "snapshot",
            "snippet_wav",
            "concatenated_wav",
            "raven_tsv",
        }:
            raise ValueError("Published file kind is invalid.")
        _digest(self.sha256, "Published file digest")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise ValueError("Published file byte size is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "kind": self.kind,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
        }

    @classmethod
    def from_dict(cls, raw: object) -> PublishedFile:
        if not isinstance(raw, dict) or set(raw) != {
            "relative_path",
            "kind",
            "sha256",
            "byte_size",
        }:
            raise ValueError("Published file document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class SnippetMapping:
    candidate_id: str
    recording_key: str
    source_sha256: str
    source_start_frame: int
    source_end_frame: int
    source_start_time_ns: int
    source_end_time_ns: int
    output_relative_path: str
    output_start_frame: int
    output_end_frame: int
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    pcm_sha256: str

    def __post_init__(self) -> None:
        if _CANDIDATE_ID.fullmatch(self.candidate_id) is None:
            raise ValueError("Snippet mapping candidate ID is invalid.")
        _relative_path(self.recording_key, "Snippet source key")
        _relative_path(self.output_relative_path, "Snippet output path")
        _digest(self.source_sha256, "Snippet source digest")
        _digest(self.pcm_sha256, "Snippet PCM digest")
        if (
            type(self.source_start_frame) is not int
            or type(self.source_end_frame) is not int
            or not 0 <= self.source_start_frame < self.source_end_frame
            or self.output_start_frame != 0
            or self.output_end_frame != self.source_end_frame - self.source_start_frame
        ):
            raise ValueError("Snippet frame mapping is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, raw: object) -> SnippetMapping:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Snippet mapping document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ConcatMapping:
    candidate_id: str
    recording_key: str
    source_sha256: str
    source_start_frame: int
    source_end_frame: int
    source_start_time_ns: int
    source_end_time_ns: int
    concat_start_frame: int
    concat_end_frame: int
    raven_selection: int

    def __post_init__(self) -> None:
        if _CANDIDATE_ID.fullmatch(self.candidate_id) is None:
            raise ValueError("Concatenation mapping candidate ID is invalid.")
        _relative_path(self.recording_key, "Concatenation source key")
        _digest(self.source_sha256, "Concatenation source digest")
        if (
            type(self.source_start_frame) is not int
            or type(self.source_end_frame) is not int
            or not 0 <= self.source_start_frame < self.source_end_frame
            or type(self.concat_start_frame) is not int
            or type(self.concat_end_frame) is not int
            or self.concat_start_frame < 0
            or self.concat_end_frame - self.concat_start_frame
            != self.source_end_frame - self.source_start_frame
            or type(self.raven_selection) is not int
            or self.raven_selection <= 0
        ):
            raise ValueError("Concatenation frame mapping is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, raw: object) -> ConcatMapping:
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("Concatenation mapping document is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ExportReceipt:
    schema_version: int
    export_id: str
    receipt_digest: str
    snapshot_digest: str
    result_id: str
    result_digest: str
    parent_result_id: str | None
    parent_result_digest: str | None
    mode: ExportMode
    format_policy: str
    collision_policy: str
    completed_at: str
    final_destination: str
    files: tuple[PublishedFile, ...]
    snippets: tuple[SnippetMapping, ...]
    concat_mappings: tuple[ConcatMapping, ...]
    raven_rows: tuple[RavenRow, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EXPORT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("Unsupported ExportReceipt schema.")
        if _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("ExportReceipt ID is invalid.")
        for value, label in (
            (self.receipt_digest, "ExportReceipt digest"),
            (self.snapshot_digest, "ExportSnapshot digest"),
            (self.result_digest, "ExportReceipt Result digest"),
        ):
            _digest(value, label)
        if _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("ExportReceipt Result ID is invalid.")
        if (self.parent_result_id is None) != (self.parent_result_digest is None):
            raise ValueError("ExportReceipt parent lineage is incomplete.")
        if self.parent_result_id is not None:
            if _RESULT_ID.fullmatch(self.parent_result_id) is None:
                raise ValueError("ExportReceipt parent Result ID is invalid.")
            _digest(self.parent_result_digest, "ExportReceipt parent digest")
        if not isinstance(self.mode, ExportMode):
            raise ValueError("ExportReceipt mode is invalid.")
        if self.format_policy != FORMAT_POLICY or self.collision_policy != COLLISION_POLICY:
            raise ValueError("ExportReceipt policy is unsupported.")
        _utc(self.completed_at, "ExportReceipt completion time")
        if not Path(self.final_destination).is_absolute():
            raise ValueError("ExportReceipt destination must be absolute.")
        file_paths = tuple(item.relative_path for item in self.files)
        if not file_paths or file_paths != tuple(sorted(file_paths)) or len(file_paths) != len(
            set(file_paths)
        ):
            raise ValueError("ExportReceipt files must be unique and sorted.")
        if self.mode.includes_snippets != bool(self.snippets):
            raise ValueError("ExportReceipt snippet mappings disagree with the mode.")
        if self.mode.includes_concat != bool(self.concat_mappings):
            raise ValueError("ExportReceipt concatenation mappings disagree with the mode.")
        if self.mode.includes_concat != bool(self.raven_rows):
            raise ValueError("ExportReceipt Raven rows disagree with the mode.")
        if self.concat_mappings and len(self.concat_mappings) != len(self.raven_rows):
            raise ValueError("ExportReceipt concatenation and Raven mappings disagree.")
        if canonical_digest(self._unsigned_dict()) != self.receipt_digest:
            raise ValueError("ExportReceipt digest does not match its immutable contents.")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "export_id": self.export_id,
            "snapshot_digest": self.snapshot_digest,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "parent_result_id": self.parent_result_id,
            "parent_result_digest": self.parent_result_digest,
            "mode": self.mode.value,
            "format_policy": self.format_policy,
            "collision_policy": self.collision_policy,
            "completed_at": self.completed_at,
            "final_destination": self.final_destination,
            "files": [item.to_dict() for item in self.files],
            "snippets": [item.to_dict() for item in self.snippets],
            "concat_mappings": [item.to_dict() for item in self.concat_mappings],
            "raven_rows": [item.to_dict() for item in self.raven_rows],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "receipt_digest": self.receipt_digest}

    @classmethod
    def from_dict(cls, raw: object) -> ExportReceipt:
        expected = {
            "schema_version",
            "export_id",
            "receipt_digest",
            "snapshot_digest",
            "result_id",
            "result_digest",
            "parent_result_id",
            "parent_result_digest",
            "mode",
            "format_policy",
            "collision_policy",
            "completed_at",
            "final_destination",
            "files",
            "snippets",
            "concat_mappings",
            "raven_rows",
        }
        if not isinstance(raw, dict) or set(raw) != expected or any(
            not isinstance(raw[name], list)
            for name in ("files", "snippets", "concat_mappings", "raven_rows")
        ):
            raise ValueError("ExportReceipt document is invalid.")
        values = dict(raw)
        values["mode"] = ExportMode(raw["mode"])
        values["files"] = tuple(PublishedFile.from_dict(item) for item in raw["files"])
        values["snippets"] = tuple(
            SnippetMapping.from_dict(item) for item in raw["snippets"]
        )
        values["concat_mappings"] = tuple(
            ConcatMapping.from_dict(item) for item in raw["concat_mappings"]
        )
        values["raven_rows"] = tuple(RavenRow.from_dict(item) for item in raw["raven_rows"])
        return cls(**values)


def _source_path(source_root: Path, recording_key: str) -> Path:
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ExportStaleSourceError("The recordings folder is missing or unsafe.")
    resolved_root = root.resolve(strict=True)
    candidate = resolved_root.joinpath(*PurePosixPath(recording_key).parts)
    current = resolved_root
    for part in PurePosixPath(recording_key).parts:
        current /= part
        if current.is_symlink():
            raise ExportStaleSourceError("A selected source path is now a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ExportStaleSourceError("A selected source recording is missing or unsafe.") from exc
    if not resolved.is_file():
        raise ExportStaleSourceError("A selected source recording is missing or unsafe.")
    return resolved


def _inspect_wave(path: Path) -> tuple[SourceWaveFormat, int]:
    try:
        with wave.open(str(path), "rb") as stream:
            source_format = SourceWaveFormat(
                stream.getframerate(),
                stream.getnchannels(),
                stream.getsampwidth(),
                stream.getcomptype(),
            )
            frame_count = stream.getnframes()
            frame_bytes = source_format.channels * source_format.sample_width_bytes
            chunk_frames = max(1, _COPY_BYTES // frame_bytes)
            total_bytes = 0
            remaining = frame_count
            while remaining:
                count = min(remaining, chunk_frames)
                payload = stream.readframes(count)
                total_bytes += len(payload)
                remaining -= count
            if total_bytes != frame_count * frame_bytes:
                raise ExportStaleSourceError("A selected WAV is truncated.")
    except ExportStaleSourceError:
        raise
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise ExportStaleSourceError("A selected source is not a supported PCM WAV.") from exc
    return source_format, frame_count


def _inspect_result_sources(
    result: ResultArtifact,
    selection: FrozenResultSelection,
    source_root: Path,
) -> dict[str, SourceWaveFormat]:
    selected = set(selection.candidate_ids)
    formats: dict[str, SourceWaveFormat] = {}
    for recording in result.recordings:
        if not any(candidate.candidate_id in selected for candidate in recording.candidates):
            continue
        path = _source_path(source_root, recording.recording_key)
        try:
            digest = _sha256_path(path)
        except OSError as exc:
            raise ExportStaleSourceError("A selected source recording cannot be read.") from exc
        source_format, frame_count = _inspect_wave(path)
        if (
            digest != recording.source_sha256
            or source_format.sample_rate_hz != recording.sample_rate_hz
            or source_format.channels != recording.channels
            or frame_count != recording.frame_count
        ):
            raise ExportStaleSourceError(
                f"Source changed after the Result was created: {recording.recording_key}"
            )
        formats[recording.recording_ref] = source_format
    return formats


def freeze_export_snapshot(
    *,
    result: ResultArtifact,
    selection: FrozenResultSelection,
    mode: ExportMode,
    source_root: Path,
    destination_parent: Path,
    export_id: str | None = None,
    created_at: str | None = None,
) -> ExportSnapshot:
    """Inspect current source facts, freeze the request, and validate publication policy."""
    formats = _inspect_result_sources(result, selection, source_root)
    snapshot = create_export_snapshot(
        result=result,
        selection=selection,
        mode=mode,
        destination_parent=Path(destination_parent).resolve(strict=True),
        source_formats=formats,
        export_id=export_id or f"exp_{uuid.uuid4().hex}",
        created_at=created_at or utc_now(),
    )
    ensure_publish_target_available(snapshot, source_root=source_root)
    return snapshot


def _validate_snapshot_sources(snapshot: ExportSnapshot, source_root: Path) -> None:
    checked: set[str] = set()
    for candidate in snapshot.candidates:
        if candidate.recording_ref in checked:
            continue
        path = _source_path(source_root, candidate.recording_key)
        try:
            digest = _sha256_path(path)
        except OSError as exc:
            raise ExportStaleSourceError("A selected source recording cannot be read.") from exc
        source_format, frame_count = _inspect_wave(path)
        if (
            digest != candidate.source_sha256
            or source_format.sample_rate_hz != candidate.sample_rate_hz
            or source_format.channels != candidate.channels
            or source_format.sample_width_bytes != candidate.sample_width_bytes
            or frame_count != candidate.frame_count
        ):
            raise ExportStaleSourceError(
                f"Source changed after export was frozen: {candidate.recording_key}"
            )
        checked.add(candidate.recording_ref)


def _cancelled(cancel_requested: Callable[[], bool] | object | None) -> bool:
    if cancel_requested is None:
        return False
    if callable(cancel_requested):
        return bool(cancel_requested())
    is_set = getattr(cancel_requested, "is_set", None)
    return bool(is_set()) if callable(is_set) else False


def _raise_if_cancelled(cancel_requested: Callable[[], bool] | object | None) -> None:
    if _cancelled(cancel_requested):
        raise ExportCancelledError(
            "Export cancelled. No new output was published; existing files are unchanged."
        )


def _copy_wave_frames(
    reader: wave.Wave_read,
    writer: wave.Wave_write,
    frame_count: int,
    *,
    frame_bytes: int,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    remaining = frame_count
    chunk_frames = max(1, _COPY_BYTES // frame_bytes)
    copied = 0
    while remaining:
        _raise_if_cancelled(cancel_requested)
        count = min(remaining, chunk_frames)
        payload = reader.readframes(count)
        if len(payload) != count * frame_bytes:
            raise ExportStaleSourceError("A selected WAV became truncated during export.")
        writer.writeframesraw(payload)
        copied += len(payload)
        remaining -= count
    if copied != frame_count * frame_bytes:
        raise ExportError("PCM byte count disagrees with the frozen frame mapping.")


def _write_wave_segment(
    source: Path,
    destination: Path,
    candidate: ExportCandidate,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with wave.open(str(source), "rb") as reader, wave.open(str(destination), "wb") as writer:
        writer.setnchannels(candidate.channels)
        writer.setsampwidth(candidate.sample_width_bytes)
        writer.setframerate(candidate.sample_rate_hz)
        reader.setpos(candidate.source_start_frame)
        _copy_wave_frames(
            reader,
            writer,
            candidate.output_frame_count,
            frame_bytes=candidate.channels * candidate.sample_width_bytes,
            cancel_requested=cancel_requested,
        )
    destination.chmod(0o600)


def _write_concat(
    source_root: Path,
    destination: Path,
    snapshot: ExportSnapshot,
    cancel_requested: Callable[[], bool] | object | None,
) -> None:
    first = snapshot.candidates[0]
    with wave.open(str(destination), "wb") as writer:
        writer.setnchannels(first.channels)
        writer.setsampwidth(first.sample_width_bytes)
        writer.setframerate(first.sample_rate_hz)
        for candidate in snapshot.candidates:
            _raise_if_cancelled(cancel_requested)
            source = _source_path(source_root, candidate.recording_key)
            with wave.open(str(source), "rb") as reader:
                reader.setpos(candidate.source_start_frame)
                _copy_wave_frames(
                    reader,
                    writer,
                    candidate.output_frame_count,
                    frame_bytes=candidate.channels * candidate.sample_width_bytes,
                    cancel_requested=cancel_requested,
                )
    destination.chmod(0o600)


def _pcm_digest(path: Path) -> tuple[str, int, SourceWaveFormat]:
    digest = hashlib.sha256()
    frames = 0
    with wave.open(str(path), "rb") as stream:
        source_format = SourceWaveFormat(
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth(),
            stream.getcomptype(),
        )
        frame_bytes = source_format.channels * source_format.sample_width_bytes
        chunk_frames = max(1, _COPY_BYTES // frame_bytes)
        while frames < stream.getnframes():
            count = min(chunk_frames, stream.getnframes() - frames)
            payload = stream.readframes(count)
            if len(payload) != count * frame_bytes:
                raise ExportError("Published WAV PCM is truncated.")
            digest.update(payload)
            frames += count
    return digest.hexdigest(), frames, source_format


def _published_files(root: Path, kinds: Mapping[str, str]) -> tuple[PublishedFile, ...]:
    files = []
    for relative_path, kind in sorted(kinds.items()):
        path = root / relative_path
        files.append(PublishedFile(relative_path, kind, _sha256_path(path), path.stat().st_size))
    return tuple(files)


def _build_receipt(
    snapshot: ExportSnapshot,
    stage: Path,
    final: Path,
    *,
    completed_at: str,
) -> ExportReceipt:
    kinds = {"export-snapshot.json": "snapshot"}
    snippets = []
    if snapshot.mode.includes_snippets:
        for candidate in snapshot.candidates:
            output = stage / candidate.snippet_relative_path
            pcm_digest, frames, source_format = _pcm_digest(output)
            if (
                frames != candidate.output_frame_count
                or source_format.sample_rate_hz != candidate.sample_rate_hz
                or source_format.channels != candidate.channels
                or source_format.sample_width_bytes != candidate.sample_width_bytes
            ):
                raise ExportError("A snippet WAV does not match its frozen source mapping.")
            kinds[candidate.snippet_relative_path] = "snippet_wav"
            snippets.append(
                SnippetMapping(
                    candidate.candidate_id,
                    candidate.recording_key,
                    candidate.source_sha256,
                    candidate.source_start_frame,
                    candidate.source_end_frame,
                    candidate.source_start_time_ns,
                    candidate.source_end_time_ns,
                    candidate.snippet_relative_path,
                    0,
                    candidate.output_frame_count,
                    candidate.sample_rate_hz,
                    candidate.channels,
                    candidate.sample_width_bytes,
                    pcm_digest,
                )
            )
    concat_mappings = ()
    raven_rows = ()
    if snapshot.mode.includes_concat:
        _pcm_digest(stage / "corpus.wav")
        kinds["corpus.wav"] = "concatenated_wav"
        kinds["corpus.Table.1.selections.txt"] = "raven_tsv"
        _tsv, raven_rows = render_raven_tsv(snapshot)
        concat_mappings = tuple(
            ConcatMapping(
                candidate.candidate_id,
                candidate.recording_key,
                candidate.source_sha256,
                candidate.source_start_frame,
                candidate.source_end_frame,
                candidate.source_start_time_ns,
                candidate.source_end_time_ns,
                candidate.concat_start_frame or 0,
                candidate.concat_end_frame or 0,
                index,
            )
            for index, candidate in enumerate(snapshot.candidates, 1)
        )
    unsigned = {
        "schema_version": EXPORT_RECEIPT_SCHEMA_VERSION,
        "export_id": snapshot.export_id,
        "snapshot_digest": snapshot.snapshot_digest,
        "result_id": snapshot.result_id,
        "result_digest": snapshot.result_digest,
        "parent_result_id": snapshot.parent_result_id,
        "parent_result_digest": snapshot.parent_result_digest,
        "mode": snapshot.mode.value,
        "format_policy": snapshot.format_policy,
        "collision_policy": snapshot.collision_policy,
        "completed_at": completed_at,
        "final_destination": str(final),
        "files": [item.to_dict() for item in _published_files(stage, kinds)],
        "snippets": [item.to_dict() for item in snippets],
        "concat_mappings": [item.to_dict() for item in concat_mappings],
        "raven_rows": [item.to_dict() for item in raven_rows],
    }
    return ExportReceipt(
        **{
            **unsigned,
            "receipt_digest": canonical_digest(unsigned),
            "mode": snapshot.mode,
            "files": tuple(PublishedFile.from_dict(item) for item in unsigned["files"]),
            "snippets": tuple(SnippetMapping.from_dict(item) for item in unsigned["snippets"]),
            "concat_mappings": tuple(
                ConcatMapping.from_dict(item) for item in unsigned["concat_mappings"]
            ),
            "raven_rows": tuple(RavenRow.from_dict(item) for item in unsigned["raven_rows"]),
        }
    )


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ExportError("Export metadata is missing, unsafe, or too large.")
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportError("Export metadata is corrupt.") from exc


def _verify_export_directory(root: Path, *, require_destination: bool) -> ExportReceipt:
    if root.is_symlink() or not root.is_dir():
        raise ExportError("Published export folder is missing or unsafe.")
    receipt = ExportReceipt.from_dict(_read_json(root / "export-receipt.json"))
    if require_destination and root.resolve(strict=True) != Path(receipt.final_destination).resolve(
        strict=True
    ):
        raise ExportError("ExportReceipt destination does not match the opened folder.")
    expected = {item.relative_path for item in receipt.files} | {"export-receipt.json"}
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ExportError("Published export contains an unsafe symlink.")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != expected:
        raise ExportError("Published export file set does not match its receipt.")
    for item in receipt.files:
        path = root / item.relative_path
        if path.stat().st_size != item.byte_size or _sha256_path(path) != item.sha256:
            raise ExportError(f"Published export file changed: {item.relative_path}")
    snapshot = ExportSnapshot.from_dict(_read_json(root / "export-snapshot.json"))
    if snapshot.snapshot_digest != receipt.snapshot_digest:
        raise ExportError("ExportSnapshot and ExportReceipt digests disagree.")
    if (
        receipt.export_id != snapshot.export_id
        or receipt.result_id != snapshot.result_id
        or receipt.result_digest != snapshot.result_digest
        or receipt.parent_result_id != snapshot.parent_result_id
        or receipt.parent_result_digest != snapshot.parent_result_digest
        or receipt.mode is not snapshot.mode
        or receipt.format_policy != snapshot.format_policy
        or receipt.collision_policy != snapshot.collision_policy
    ):
        raise ExportError("ExportReceipt provenance disagrees with its frozen snapshot.")
    expected_kinds = {"export-snapshot.json": "snapshot"}
    if snapshot.mode.includes_snippets:
        expected_kinds.update(
            {
                candidate.snippet_relative_path: "snippet_wav"
                for candidate in snapshot.candidates
            }
        )
    if snapshot.mode.includes_concat:
        expected_kinds.update(
            {
                "corpus.wav": "concatenated_wav",
                "corpus.Table.1.selections.txt": "raven_tsv",
            }
        )
    if {item.relative_path: item.kind for item in receipt.files} != expected_kinds:
        raise ExportError("ExportReceipt payload kinds disagree with its frozen snapshot.")
    if receipt.mode.includes_snippets:
        if tuple(mapping.candidate_id for mapping in receipt.snippets) != tuple(
            candidate.candidate_id for candidate in snapshot.candidates
        ):
            raise ExportError("Snippet receipt ordering disagrees with the frozen selection.")
        for mapping, candidate in zip(
            receipt.snippets, snapshot.candidates, strict=True
        ):
            if (
                mapping.recording_key != candidate.recording_key
                or mapping.source_sha256 != candidate.source_sha256
                or mapping.source_start_frame != candidate.source_start_frame
                or mapping.source_end_frame != candidate.source_end_frame
                or mapping.source_start_time_ns != candidate.source_start_time_ns
                or mapping.source_end_time_ns != candidate.source_end_time_ns
                or mapping.output_relative_path != candidate.snippet_relative_path
                or mapping.output_start_frame != 0
                or mapping.output_end_frame != candidate.output_frame_count
                or mapping.sample_rate_hz != candidate.sample_rate_hz
                or mapping.channels != candidate.channels
                or mapping.sample_width_bytes != candidate.sample_width_bytes
            ):
                raise ExportError("Snippet receipt mapping disagrees with its snapshot.")
            pcm_digest, frames, source_format = _pcm_digest(root / mapping.output_relative_path)
            if (
                pcm_digest != mapping.pcm_sha256
                or frames != mapping.output_end_frame
                or source_format.sample_rate_hz != mapping.sample_rate_hz
                or source_format.channels != mapping.channels
                or source_format.sample_width_bytes != mapping.sample_width_bytes
            ):
                raise ExportError("Published snippet no longer matches its receipt.")
    if receipt.mode.includes_concat:
        if tuple(mapping.candidate_id for mapping in receipt.concat_mappings) != tuple(
            candidate.candidate_id for candidate in snapshot.candidates
        ):
            raise ExportError(
                "Concatenation receipt ordering disagrees with the frozen selection."
            )
        for index, (mapping, candidate) in enumerate(
            zip(receipt.concat_mappings, snapshot.candidates, strict=True), 1
        ):
            if (
                mapping.recording_key != candidate.recording_key
                or mapping.source_sha256 != candidate.source_sha256
                or mapping.source_start_frame != candidate.source_start_frame
                or mapping.source_end_frame != candidate.source_end_frame
                or mapping.source_start_time_ns != candidate.source_start_time_ns
                or mapping.source_end_time_ns != candidate.source_end_time_ns
                or mapping.concat_start_frame != candidate.concat_start_frame
                or mapping.concat_end_frame != candidate.concat_end_frame
                or mapping.raven_selection != index
            ):
                raise ExportError(
                    "Concatenation receipt mapping disagrees with its snapshot."
                )
        _digest_value, frames, source_format = _pcm_digest(root / "corpus.wav")
        if (
            frames != (receipt.concat_mappings[-1].concat_end_frame)
            or source_format.sample_rate_hz != snapshot.candidates[0].sample_rate_hz
        ):
            raise ExportError("Published concatenated WAV no longer matches its receipt.")
        expected_tsv, expected_rows = render_raven_tsv(snapshot)
        if (
            (root / "corpus.Table.1.selections.txt").read_bytes() != expected_tsv
            or expected_rows != receipt.raven_rows
        ):
            raise ExportError("Published Raven table no longer matches frame provenance.")
    return receipt


def verify_export_directory(root: Path) -> ExportReceipt:
    """Reopen every file, checksum, WAV mapping and Raven row without rewriting output."""
    return _verify_export_directory(Path(root), require_destination=True)


def _atomic_publish_no_replace(staging: Path, final: Path) -> None:
    if sys.platform == "darwin":
        library = ctypes.CDLL(None, use_errno=True)
        renamex = library.renamex_np
        renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex.restype = ctypes.c_int
        if renamex(os.fsencode(staging), os.fsencode(final), 0x00000004) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise ExportConflictError("The export destination appeared during publication.")
            raise OSError(code, os.strerror(code), str(final))
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise ExportError("This platform lacks atomic no-overwrite directory publication.")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(staging), -100, os.fsencode(final), 1) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise ExportConflictError("The export destination appeared during publication.")
            raise OSError(code, os.strerror(code), str(final))
        return
    if os.name == "nt":
        try:
            os.rename(staging, final)
        except FileExistsError as exc:
            raise ExportConflictError(
                "The export destination appeared during publication."
            ) from exc
        return
    raise ExportError("This platform lacks atomic no-overwrite directory publication.")


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_export(
    snapshot: ExportSnapshot,
    *,
    source_root: Path,
    cancel_requested: Callable[[], bool] | object | None = None,
    completed_at: str | None = None,
) -> ExportReceipt:
    """Materialize privately, verify completely, then atomically publish one directory."""
    _raise_if_cancelled(cancel_requested)
    final = ensure_publish_target_available(snapshot, source_root=source_root)
    _validate_snapshot_sources(snapshot, source_root)
    _raise_if_cancelled(cancel_requested)
    staging = final.parent / f".{snapshot.directory_name}.staging-{uuid.uuid4().hex}"
    if staging.exists() or staging.is_symlink():
        raise ExportConflictError("A private export staging name already exists.")
    published = False
    try:
        staging.mkdir(mode=0o700)
        _raise_if_cancelled(cancel_requested)
        (staging / "export-snapshot.json").write_bytes(_json_bytes(snapshot.to_dict()))
        (staging / "export-snapshot.json").chmod(0o600)
        _raise_if_cancelled(cancel_requested)
        if snapshot.mode.includes_snippets:
            for candidate in snapshot.candidates:
                _write_wave_segment(
                    _source_path(source_root, candidate.recording_key),
                    staging / candidate.snippet_relative_path,
                    candidate,
                    cancel_requested,
                )
        if snapshot.mode.includes_concat:
            _write_concat(
                Path(source_root), staging / "corpus.wav", snapshot, cancel_requested
            )
            tsv, _rows = render_raven_tsv(snapshot)
            (staging / "corpus.Table.1.selections.txt").write_bytes(tsv)
            (staging / "corpus.Table.1.selections.txt").chmod(0o600)
        _raise_if_cancelled(cancel_requested)
        _validate_snapshot_sources(snapshot, source_root)
        _raise_if_cancelled(cancel_requested)
        receipt = _build_receipt(
            snapshot,
            staging,
            final,
            completed_at=completed_at or utc_now(),
        )
        (staging / "export-receipt.json").write_bytes(_json_bytes(receipt.to_dict()))
        (staging / "export-receipt.json").chmod(0o600)
        _verify_export_directory(staging, require_destination=False)
        _fsync_tree(staging)
        _raise_if_cancelled(cancel_requested)
        _atomic_publish_no_replace(staging, final)
        published = True
        try:
            _fsync_directory(final.parent)
        except OSError:
            # The self-contained directory is already atomically visible and fully verified.
            pass
        return verify_export_directory(final)
    except (ExportError, ExportStaleSourceError, ExportCancelledError, ExportConflictError):
        raise
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise ExportError(
            f"Export write failed: {detail}. No partial corpus was published."
        ) from exc
    finally:
        if not published and staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)


__all__ = [
    "COLLISION_POLICY",
    "FORMAT_POLICY",
    "RAVEN_REFERENCE",
    "RAVEN_REFERENCE_URL",
    "ConcatMapping",
    "ExportCancelledError",
    "ExportConflictError",
    "ExportError",
    "ExportMode",
    "ExportReceipt",
    "ExportSnapshot",
    "ExportState",
    "ExportStaleSourceError",
    "PublishedFile",
    "RavenRow",
    "SnippetMapping",
    "SourceWaveFormat",
    "create_export_snapshot",
    "ensure_publish_target_available",
    "frame_seconds",
    "freeze_export_snapshot",
    "publish_export",
    "render_raven_tsv",
    "safe_snippet_relative_path",
    "verify_export_directory",
]
