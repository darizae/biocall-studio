"""Safe, recursive, cancellable Detect WAV discovery without source writes."""

from __future__ import annotations

import hashlib
import os
import stat
import struct
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import BinaryIO

from biocall_studio.detect.domain import validate_relative_reference
from biocall_studio.detect.inventory import (
    MAX_INVENTORY_ISSUES,
    ChangeKind,
    DecisionOrigin,
    DecisionRule,
    InclusionDecision,
    InventoryIssue,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
    WavMetadata,
    find_file_identity_conflicts,
    find_portable_path_conflicts,
    resolve_decision,
)

MAX_WAV_HEADER_BYTES = 65_536
MAX_DISCOVERY_ENTRIES = 100_000
MAX_DISCOVERY_DEPTH = 64
HASH_CHUNK_BYTES = 1_048_576


class InventoryScanCancelled(Exception):
    """The active scan was cancelled before a complete snapshot could be published."""


class InventoryScanError(OSError):
    """Traversal could not produce a complete, trustworthy inventory."""


@dataclass(frozen=True, slots=True)
class InventoryScanProgress:
    stage: str
    completed: int
    total: int
    valid: int
    issues: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path
    raw_relative: str
    key: str
    linked: bool
    portable_mismatch: bool
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True, slots=True)
class _ReadFacts:
    size_bytes: int
    mtime_ns: int
    content_sha256: str
    wav: WavMetadata
    file_id: tuple[int, int]


def _cancelled(cancel: Event | Callable[[], bool] | None) -> bool:
    if cancel is None:
        return False
    return cancel.is_set() if isinstance(cancel, Event) else bool(cancel())


def _check_cancel(cancel: Event | Callable[[], bool] | None) -> None:
    if _cancelled(cancel):
        raise InventoryScanCancelled()


def _is_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attributes & flag)


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name or "."


def _enumerate_wavs(
    root: Path,
    *,
    cancel: Event | Callable[[], bool] | None,
) -> tuple[list[_Candidate], list[InventoryIssue]]:
    candidates: list[_Candidate] = []
    issues: list[InventoryIssue] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    entries_seen = 0
    while stack:
        folder, depth = stack.pop()
        _check_cancel(cancel)
        if depth > MAX_DISCOVERY_DEPTH:
            raise InventoryScanError(
                f"Recording folder depth exceeds the {MAX_DISCOVERY_DEPTH}-level limit."
            )
        try:
            resolved_folder = folder.resolve(strict=True)
            if not resolved_folder.is_relative_to(root):
                raise InventoryScanError("A recording folder resolves outside the source root.")
            with os.scandir(folder) as stream:
                entries = sorted(stream, key=lambda entry: entry.name)
        except InventoryScanError:
            raise
        except OSError as exc:
            relative = _relative_display(folder, root)
            raise InventoryScanError(
                f"Cannot completely read {relative or '.'}: {exc.strerror or type(exc).__name__}."
            ) from exc

        child_folders: list[Path] = []
        for entry in entries:
            _check_cancel(cancel)
            entries_seen += 1
            if entries_seen > MAX_DISCOVERY_ENTRIES:
                raise InventoryScanError(
                    f"Recording discovery exceeds the {MAX_DISCOVERY_ENTRIES:,}-entry limit."
                )
            path = Path(entry.path)
            raw_relative = _relative_display(path, root)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                if entry.name.casefold().endswith(".wav"):
                    issues.append(
                        InventoryIssue(
                            "unreadable_path",
                            raw_relative,
                            f"Cannot inspect WAV path: {exc.strerror or type(exc).__name__}.",
                        )
                    )
                continue
            linked = entry.is_symlink() or _is_reparse(info)
            if linked:
                issues.append(
                    InventoryIssue(
                        "symlink_skipped",
                        raw_relative,
                        "Symbolic links and reparse points are not followed.",
                    )
                )
                if entry.name.casefold().endswith(".wav"):
                    try:
                        key = validate_relative_reference(raw_relative)
                    except ValueError:
                        continue
                    candidates.append(
                        _Candidate(
                            path,
                            raw_relative,
                            key,
                            True,
                            key != raw_relative,
                            info.st_size,
                            info.st_mtime_ns,
                        )
                    )
                continue
            if stat.S_ISDIR(info.st_mode):
                child_folders.append(path)
                continue
            if not entry.name.casefold().endswith(".wav"):
                continue
            try:
                key = validate_relative_reference(raw_relative)
            except ValueError as exc:
                issues.append(
                    InventoryIssue(
                        "unsafe_path",
                        raw_relative,
                        f"WAV path is not portable: {exc}",
                    )
                )
                continue
            if key != raw_relative:
                issues.append(
                    InventoryIssue(
                        "non_normalized_path",
                        raw_relative,
                        "WAV path is not NFC-normalized and cannot be used as a portable key.",
                    )
                )
            candidates.append(
                _Candidate(
                    path,
                    raw_relative,
                    key,
                    False,
                    key != raw_relative,
                    info.st_size,
                    info.st_mtime_ns,
                )
            )
        for child in reversed(child_folders):
            stack.append((child, depth + 1))
    return sorted(candidates, key=lambda candidate: candidate.key), issues


@contextmanager
def _open_verified(root: Path, path: Path) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or _is_reparse(before):
        raise ValueError("Symbolic links and reparse points are not followed.")
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("WAV input is not a regular file.")
    if not os.access(path, os.R_OK):
        raise PermissionError("WAV input cannot be read.")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("WAV path resolves outside the source root.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    stream: BinaryIO | None = None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            before.st_dev,
            before.st_ino,
        ) != (opened.st_dev, opened.st_ino):
            raise ValueError("WAV input changed while it was being opened.")
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
        yield stream, opened
    finally:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)


def _read_wav_header(stream: BinaryIO, size_bytes: int) -> WavMetadata:
    stream.seek(0)
    prologue = stream.read(12)
    if len(prologue) != 12 or prologue[:4] != b"RIFF" or prologue[8:] != b"WAVE":
        raise ValueError("Malformed RIFF/WAVE header.")
    consumed = 12
    fmt: tuple[int, int, int, int, int] | None = None
    data_size: int | None = None
    data_offset: int | None = None
    while consumed + 8 <= MAX_WAV_HEADER_BYTES:
        chunk_header = stream.read(8)
        if len(chunk_header) != 8:
            break
        consumed += 8
        chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
        padded_size = chunk_size + (chunk_size & 1)
        if chunk_id == b"fmt ":
            if chunk_size < 16 or consumed + 16 > MAX_WAV_HEADER_BYTES:
                raise ValueError("Malformed WAV format chunk.")
            body = stream.read(16)
            if len(body) != 16:
                raise ValueError("Truncated WAV format chunk.")
            codec, channels, rate, _, block_align, bits = struct.unpack("<HHIIHH", body)
            if bits not in {8, 16, 24, 32}:
                raise ValueError(f"Unsupported PCM sample width: {bits} bits.")
            fmt = (codec, channels, rate, block_align, bits)
            remaining = padded_size - 16
            if consumed + padded_size > MAX_WAV_HEADER_BYTES:
                raise ValueError("WAV header exceeds the 64 KiB read limit.")
            stream.seek(remaining, os.SEEK_CUR)
            consumed += padded_size
        elif chunk_id == b"data":
            data_size = chunk_size
            data_offset = stream.tell()
            break
        else:
            if consumed + padded_size > MAX_WAV_HEADER_BYTES:
                raise ValueError("WAV header exceeds the 64 KiB read limit.")
            stream.seek(padded_size, os.SEEK_CUR)
            consumed += padded_size
    if fmt is None or data_size is None or data_offset is None:
        raise ValueError("WAV format or data chunk is missing from the bounded header.")
    codec, channels, rate, block_align, bits = fmt
    if codec != 1:
        raise ValueError(f"Unsupported WAV codec {codec}; use integer PCM.")
    sample_width = bits // 8
    if channels <= 0 or rate <= 0 or block_align != channels * sample_width:
        raise ValueError("Invalid WAV channel, rate, or block alignment.")
    if data_offset + data_size > size_bytes:
        raise ValueError("WAV data chunk extends beyond the file.")
    if data_size % block_align:
        raise ValueError("WAV data size is not aligned to complete frames.")
    frame_count = data_size // block_align
    if frame_count <= 0:
        raise ValueError("WAV contains no complete audio frames.")
    encoding = "PCM_U8" if bits == 8 else f"PCM_S{bits}LE"
    return WavMetadata(rate, channels, frame_count, encoding)


def _read_facts(
    root: Path,
    path: Path,
    *,
    cancel: Event | Callable[[], bool] | None,
) -> _ReadFacts:
    with _open_verified(root, path) as (stream, before):
        wav = _read_wav_header(stream, before.st_size)
        stream.seek(0)
        digest = hashlib.sha256()
        while True:
            _check_cancel(cancel)
            chunk = stream.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("WAV input changed during the scan.")
        return _ReadFacts(
            size_bytes=after.st_size,
            mtime_ns=after.st_mtime_ns,
            content_sha256=digest.hexdigest(),
            wav=wav,
            file_id=(after.st_dev, after.st_ino),
        )


def _same_source(left: InventoryRecording, right: InventoryRecording) -> bool:
    return (
        left.size_bytes,
        left.mtime_ns,
        left.content_sha256,
        left.wav,
    ) == (
        right.size_bytes,
        right.mtime_ns,
        right.content_sha256,
        right.wav,
    )


def discover_wavs(
    root: Path,
    *,
    collection_id: str,
    binding_revision: int,
    previous: InventorySnapshot | None = None,
    decision_rules: Iterable[DecisionRule] | None = None,
    cancel: Event | Callable[[], bool] | None = None,
    progress: Callable[[InventoryScanProgress], None] | None = None,
    scanned_at: datetime | None = None,
    step_delay_seconds: float = 0.0,
) -> InventorySnapshot:
    """Return a complete immutable snapshot or raise without publishing partial facts."""
    requested = Path(root)
    try:
        resolved_root = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InventoryScanError("The recordings folder is missing or cannot be resolved.") from exc
    if not resolved_root.is_dir() or not os.access(resolved_root, os.R_OK | os.X_OK):
        raise InventoryScanError("The recordings folder cannot be read.")
    _check_cancel(cancel)
    rules = tuple(
        previous.decision_rules
        if decision_rules is None and previous is not None
        else (decision_rules or ())
    )
    candidates, issues = _enumerate_wavs(resolved_root, cancel=cancel)
    if progress is not None:
        progress(InventoryScanProgress("Listing WAV files", 0, len(candidates), 0, len(issues)))

    raw_by_key: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        raw_by_key[candidate.key].append(candidate.raw_relative)
    duplicate_normalized_keys = {
        key for key, raw_values in raw_by_key.items() if len(raw_values) > 1
    }
    for key in sorted(duplicate_normalized_keys):
        for raw in raw_by_key[key]:
            issues.append(
                InventoryIssue(
                    "normalized_path_collision",
                    raw,
                    "Multiple WAV paths normalize to the same portable recording key.",
                )
            )

    old = (
        {}
        if previous is None
        else {
            row.recording_key: row
            for row in previous.recordings
            if row.status is not RecordingStatus.MISSING
        }
    )
    rows: list[InventoryRecording] = []
    file_ids: dict[str, tuple[int, int]] = {}
    valid_count = 0
    processed = 0
    for candidate in candidates:
        _check_cancel(cancel)
        if candidate.key in duplicate_normalized_keys:
            continue
        processed += 1
        if candidate.portable_mismatch:
            continue
        resolution = resolve_decision(candidate.key, rules)
        if candidate.linked:
            row = InventoryRecording(
                candidate.key,
                candidate.size_bytes,
                candidate.mtime_ns,
                None,
                None,
                InclusionDecision.EXCLUDED,
                RecordingStatus.INVALID,
                "Symbolic links and reparse points are not followed",
                DecisionOrigin.CONFLICT,
                candidate.key,
                ChangeKind.ADDED,
            )
        else:
            try:
                facts = _read_facts(resolved_root, candidate.path, cancel=cancel)
            except (OSError, ValueError) as exc:
                row = InventoryRecording(
                    candidate.key,
                    candidate.size_bytes,
                    candidate.mtime_ns,
                    None,
                    None,
                    resolution.decision,
                    RecordingStatus.INVALID,
                    f"Invalid or unreadable WAV: {exc}",
                    resolution.origin,
                    resolution.source_path,
                    ChangeKind.ADDED,
                )
                issues.append(InventoryIssue("invalid_wav", candidate.key, row.reason))
            else:
                row = InventoryRecording(
                    candidate.key,
                    facts.size_bytes,
                    facts.mtime_ns,
                    facts.content_sha256,
                    facts.wav,
                    resolution.decision,
                    RecordingStatus.VALID,
                    resolution.reason,
                    resolution.origin,
                    resolution.source_path,
                    ChangeKind.ADDED,
                )
                previous_row = old.get(candidate.key)
                if previous_row is not None:
                    row = replace(
                        row,
                        change=(
                            ChangeKind.UNCHANGED
                            if _same_source(previous_row, row)
                            else ChangeKind.REPLACED
                        ),
                    )
                file_ids[candidate.key] = facts.file_id
                valid_count += 1
        rows.append(row)
        if progress is not None and (
            len(candidates) <= 64 or processed == len(candidates) or processed % 64 == 0
        ):
            progress(
                InventoryScanProgress(
                    "Reading WAV headers and fingerprints",
                    processed,
                    len(candidates),
                    valid_count,
                    len(issues),
                )
            )
        if step_delay_seconds:
            if isinstance(cancel, Event):
                cancel.wait(step_delay_seconds)
                _check_cancel(cancel)
            else:
                time.sleep(step_delay_seconds)

    rows_by_key = {row.recording_key: row for row in rows}
    path_conflicts = find_portable_path_conflicts(rows_by_key)
    hardlink_conflicts = find_file_identity_conflicts(file_ids)
    for code, groups, message in (
        (
            "portable_path_collision",
            path_conflicts,
            "WAV path collides after Unicode and case normalization.",
        ),
        (
            "hardlink_conflict",
            hardlink_conflicts,
            "Multiple recording paths refer to the same filesystem file.",
        ),
    ):
        for group in groups:
            for key in group:
                existing = rows_by_key[key]
                rows_by_key[key] = replace(
                    existing,
                    decision=InclusionDecision.EXCLUDED,
                    status=RecordingStatus.INVALID,
                    reason=message,
                    decision_origin=DecisionOrigin.CONFLICT,
                    decision_path=group[0],
                )
            issues.append(InventoryIssue(code, group[0], f"{message} {'; '.join(group)}"))

    current_keys = set(rows_by_key)
    for key, old_row in old.items():
        if key in current_keys:
            continue
        rows_by_key[key] = replace(
            old_row,
            status=RecordingStatus.MISSING,
            reason="Recording is missing after rescan",
            change=ChangeKind.REMOVED,
        )

    _check_cancel(cancel)
    if len(issues) > MAX_INVENTORY_ISSUES:
        omitted = len(issues) - MAX_INVENTORY_ISSUES + 1
        issues = sorted(
            issues, key=lambda issue: (issue.relative_path, issue.code, issue.message)
        )[: MAX_INVENTORY_ISSUES - 1]
        issues.append(
            InventoryIssue(
                "issues_truncated",
                ".",
                f"{omitted:,} additional diagnostic issues were omitted from this snapshot.",
            )
        )
    snapshot = InventorySnapshot.create(
        collection_id=collection_id,
        binding_revision=binding_revision,
        recordings=rows_by_key.values(),
        decision_rules=rules,
        issues=issues,
        scanned_at=scanned_at,
    )
    if progress is not None:
        progress(
            InventoryScanProgress(
                "Verifying inventory snapshot",
                len(candidates),
                len(candidates),
                snapshot.counts.included,
                len(snapshot.issues),
            )
        )
    return snapshot


def snapshot_is_quickly_current(root: Path, snapshot: InventorySnapshot) -> bool:
    """Cheap UI freshness check; downstream reads still require full SHA-256 revalidation."""
    try:
        resolved_root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    for row in snapshot.recordings:
        path = resolved_root / row.recording_key
        if row.status is RecordingStatus.MISSING:
            if path.exists() or path.is_symlink():
                return False
            continue
        try:
            info = path.lstat()
            if (
                row.status is RecordingStatus.INVALID
                and row.decision_origin is DecisionOrigin.CONFLICT
                and (stat.S_ISLNK(info.st_mode) or _is_reparse(info))
            ):
                if info.st_size != row.size_bytes or info.st_mtime_ns != row.mtime_ns:
                    return False
                continue
            if (
                stat.S_ISLNK(info.st_mode)
                or _is_reparse(info)
                or not stat.S_ISREG(info.st_mode)
                or path.resolve(strict=True).is_relative_to(resolved_root) is False
                or info.st_size != row.size_bytes
                or info.st_mtime_ns != row.mtime_ns
            ):
                return False
        except (OSError, RuntimeError):
            return False
    return True


def validate_recording_source(
    root: Path,
    row: InventoryRecording,
    *,
    cancel: Event | Callable[[], bool] | None = None,
) -> Path:
    """Revalidate one frozen selected row at the later Worker boundary."""
    if row.status is not RecordingStatus.VALID:
        raise ValueError("Only a valid inventory recording can be used downstream.")
    resolved_root = Path(root).resolve(strict=True)
    path = resolved_root / row.recording_key
    facts = _read_facts(resolved_root, path, cancel=cancel)
    if (
        facts.size_bytes,
        facts.mtime_ns,
        facts.content_sha256,
        facts.wav,
    ) != (
        row.size_bytes,
        row.mtime_ns,
        row.content_sha256,
        row.wav,
    ):
        raise ValueError("Recording changed after the frozen inventory snapshot.")
    return path
