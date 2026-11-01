"""Frozen, PCM-preserving corpus export and atomic publication."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from enum import StrEnum
from pathlib import Path, PurePosixPath

from biocall_studio.detect.domain import validate_relative_reference
from biocall_studio.detect.domain.result_views import FrozenResultSelection
from biocall_studio.detect.domain.rf_refinement import DerivedResult, ResultArtifact
from biocall_studio.detect.domain.runs import canonical_digest

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
                raise ValueError("Concatenated export requires one identical mono PCM format.")
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
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

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
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

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
        if (
            not file_paths
            or file_paths != tuple(sorted(file_paths))
            or len(file_paths) != len(set(file_paths))
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
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or any(
                not isinstance(raw[name], list)
                for name in ("files", "snippets", "concat_mappings", "raven_rows")
            )
        ):
            raise ValueError("ExportReceipt document is invalid.")
        values = dict(raw)
        values["mode"] = ExportMode(raw["mode"])
        values["files"] = tuple(PublishedFile.from_dict(item) for item in raw["files"])
        values["snippets"] = tuple(SnippetMapping.from_dict(item) for item in raw["snippets"])
        values["concat_mappings"] = tuple(
            ConcatMapping.from_dict(item) for item in raw["concat_mappings"]
        )
        values["raven_rows"] = tuple(RavenRow.from_dict(item) for item in raw["raven_rows"])
        return cls(**values)
