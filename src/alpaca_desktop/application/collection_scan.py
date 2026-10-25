"""Bounded, cancellable Collection directory and WAV-header scanning."""

from __future__ import annotations

import hashlib
import os
import stat as stat_module
import struct
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event

from alpaca_desktop.domain.collection import (
    CollectionIssue,
    Fingerprint,
    InventoryEntry,
    PositiveExample,
    ScanResult,
    SourceRecording,
    WavHeader,
    ensure_unique_interval,
    parse_positive_filename,
    validate_interval,
    validate_source_match,
    validate_wav_header,
)
from alpaca_desktop.domain.paths import validate_relative_path

MAX_WAV_HEADER_BYTES = 65_536


class CollectionScanCancelled(Exception):
    """The user cancelled a Collection Scan before publication."""


@dataclass(frozen=True)
class ScanProgress:
    stage: str
    completed: int
    total: int
    recordings: int
    positives: int
    issues: int


def _issue(code: str, path: str, message: str, correction: str) -> CollectionIssue:
    return CollectionIssue(code, path, message, correction)


def _portable_identity(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _source_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode()).hexdigest()[:16]
    return f"source-{digest}"


def _read_wav_header(path: Path) -> WavHeader:
    """Read RIFF structure only, rejecting headers that exceed a fixed budget."""
    size_bytes = path.stat().st_size
    with path.open("rb") as stream:
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
                if bits % 8:
                    raise ValueError("Unsupported WAV sample width.")
                sample_width = bits // 8
                fmt = (codec, channels, rate, block_align, sample_width)
                remaining = padded_size - 16
                if consumed + padded_size > MAX_WAV_HEADER_BYTES and chunk_id != b"data":
                    raise ValueError("WAV header exceeds the 64 KiB read budget.")
                stream.seek(remaining, os.SEEK_CUR)
                consumed += padded_size
            elif chunk_id == b"data":
                data_size = chunk_size
                data_offset = stream.tell()
                break
            else:
                if consumed + padded_size > MAX_WAV_HEADER_BYTES:
                    raise ValueError("WAV header exceeds the 64 KiB read budget.")
                stream.seek(padded_size, os.SEEK_CUR)
                consumed += padded_size
        if fmt is None or data_size is None or data_offset is None:
            raise ValueError("WAV format or data chunk is missing from the bounded header.")
        codec, channels, rate, block_align, sample_width = fmt
        if data_offset + data_size > size_bytes:
            raise ValueError("WAV data chunk extends beyond the file.")
        if codec != 1:
            raise ValueError(f"Unsupported WAV codec {codec}; use PCM.")
        if channels <= 0 or block_align <= 0 or block_align != channels * sample_width:
            raise ValueError("Invalid WAV channel or block alignment.")
        if data_size % block_align:
            raise ValueError("WAV data size is not aligned to complete frames.")
        header = WavHeader("PCM", channels, rate, sample_width, data_size // block_align)
        validate_wav_header(header)
        return header


def _cancelled(cancel: Event | Callable[[], bool] | None) -> bool:
    if cancel is None:
        return False
    return cancel.is_set() if isinstance(cancel, Event) else bool(cancel())


def _check_cancel(cancel: Event | Callable[[], bool] | None) -> None:
    if _cancelled(cancel):
        raise CollectionScanCancelled()


def _enumerate_entries(
    root: Path, cancel: Event | Callable[[], bool] | None = None
) -> tuple[list[Path], list[CollectionIssue]]:
    entries: list[Path] = []
    issues: list[CollectionIssue] = []
    for folder_name in ("recordings", "positives"):
        folder = root / folder_name
        if not folder.is_dir():
            issues.append(
                _issue(
                    "missing_folder",
                    f"{folder_name}/",
                    f"Required folder {folder_name}/ is missing.",
                    f"Create {folder_name}/ directly inside the selected Collection.",
                )
            )
            continue
        try:
            resolved_folder = folder.resolve(strict=True)
        except OSError as exc:
            issues.append(
                _issue(
                    "unreadable_path",
                    f"{folder_name}/",
                    f"Cannot resolve required folder: {exc.strerror or type(exc).__name__}",
                    "Repair the folder path, then rescan the Collection.",
                )
            )
            continue
        if not resolved_folder.is_relative_to(root):
            issues.append(
                _issue(
                    "symlink_escape",
                    f"{folder_name}/",
                    "Required folder resolves outside the selected Collection.",
                    f"Replace {folder_name}/ with a folder inside this Collection.",
                )
            )
            continue
        try:
            children = []
            for child in folder.iterdir():
                _check_cancel(cancel)
                children.append(child)
            children.sort(key=lambda item: item.name)
        except OSError as exc:
            issues.append(
                _issue(
                    "permission_denied",
                    f"{folder_name}/",
                    f"Cannot list folder: {exc}",
                    "Allow read access, then rescan the Collection.",
                )
            )
            continue
        entries.extend(children)
    return entries, issues


def _current_inventory(root: Path) -> tuple[dict[str, InventoryEntry], list[CollectionIssue]]:
    entries, issues = _enumerate_entries(root)
    inventory: dict[str, InventoryEntry] = {}
    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        try:
            resolved = entry.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("Path resolves outside the selected Collection.")
            stat = entry.stat()
        except (OSError, ValueError) as exc:
            issues.append(
                _issue(
                    "permission_denied",
                    relative,
                    f"Cannot inspect path: {exc}",
                    "Allow read access or remove the path, then rescan.",
                )
            )
            continue
        inventory[relative] = InventoryEntry(relative, stat.st_size, stat.st_mtime_ns)
    return inventory, issues


def scan_collection(
    root: Path,
    *,
    cached: ScanResult | None = None,
    cancel: Event | Callable[[], bool] | None = None,
    progress: Callable[[ScanProgress], None] | None = None,
    step_delay_seconds: float = 0.0,
) -> ScanResult:
    """Scan direct input children, reading at most one bounded header per stale WAV."""
    root = Path(root)
    if not root.is_dir():
        return ScanResult(
            root.name or str(root),
            (),
            (),
            (
                _issue(
                    "missing_collection",
                    ".",
                    "Selected Collection folder does not exist.",
                    "Choose an existing folder containing recordings/ and positives/.",
                ),
            ),
            (),
        )
    root = root.resolve(strict=True)
    entries, issues = _enumerate_entries(root, cancel)
    inventory: list[InventoryEntry] = []
    old_inventory = {entry.relative_path: entry for entry in cached.inventory} if cached else {}
    old_facts: dict[str, Fingerprint] = {}
    if cached:
        old_facts.update({record.relative_path: record.fingerprint for record in cached.records})
        old_facts.update(
            {
                positive.relative_path: positive.fingerprint
                for positive in cached.positives
                if positive.fingerprint is not None
            }
        )
    headers: dict[str, Fingerprint] = {}
    positive_candidates: set[str] = set()
    header_reads = 0
    portable: dict[str, str] = {}
    total = len(entries)
    recordings_seen = 0
    positives_seen = 0
    if progress:
        progress(ScanProgress("Listing files", 0, total, 0, 0, len(issues)))

    for completed, entry in enumerate(entries, 1):
        _check_cancel(cancel)
        relative = entry.relative_to(root).as_posix()
        try:
            validate_relative_path(relative)
        except ValueError as exc:
            issues.append(
                _issue(
                    "unsafe_path",
                    relative,
                    str(exc),
                    "Rename this entry to a portable filename without reserved or unsafe parts.",
                )
            )
        identity = _portable_identity(relative)
        if identity in portable and portable[identity] != relative:
            issues.append(
                _issue(
                    "name_collision",
                    relative,
                    f"Name collides with {portable[identity]} after Unicode/case normalization.",
                    "Rename one path so the names are distinct on macOS and Windows.",
                )
            )
        else:
            portable[identity] = relative
        try:
            path_stat = entry.lstat()
        except OSError as exc:
            issues.append(
                _issue(
                    "permission_denied",
                    relative,
                    f"Cannot inspect path: {exc}",
                    "Allow read access or remove the path, then rescan.",
                )
            )
            continue
        try:
            resolved = entry.resolve(strict=True)
        except OSError as exc:
            issues.append(
                _issue(
                    "unreadable_path",
                    relative,
                    f"Cannot resolve path: {exc}",
                    "Repair or remove the broken path, then rescan.",
                )
            )
            continue
        if not resolved.is_relative_to(root):
            inventory.append(InventoryEntry(relative, path_stat.st_size, path_stat.st_mtime_ns))
            issues.append(
                _issue(
                    "symlink_escape",
                    relative,
                    "Path resolves outside the selected Collection.",
                    "Replace the symlink with a WAV stored inside this Collection.",
                )
            )
            continue
        try:
            entry_stat = entry.stat()
        except OSError as exc:
            issues.append(
                _issue(
                    "permission_denied",
                    relative,
                    f"Cannot inspect file: {exc}",
                    "Allow read access or remove the file, then rescan.",
                )
            )
            continue
        if stat_module.S_ISDIR(entry_stat.st_mode):
            inventory.append(InventoryEntry(relative, entry_stat.st_size, entry_stat.st_mtime_ns))
            issues.append(
                _issue(
                    "unexpected_entry",
                    relative,
                    "Nested folders are not scanned.",
                    "Place WAV files directly in recordings/ or positives/.",
                )
            )
            continue
        if not stat_module.S_ISREG(entry_stat.st_mode):
            inventory.append(InventoryEntry(relative, entry_stat.st_size, entry_stat.st_mtime_ns))
            issues.append(
                _issue(
                    "unexpected_entry",
                    relative,
                    "Only regular files are scanned.",
                    "Remove this special filesystem entry from the Collection input folder.",
                )
            )
            continue
        current = InventoryEntry(relative, entry_stat.st_size, entry_stat.st_mtime_ns)
        inventory.append(current)
        if entry.suffix.casefold() != ".wav":
            issues.append(
                _issue(
                    "unsupported_file",
                    relative,
                    "Only WAV files are accepted in Collection input folders.",
                    "Remove, relocate, or convert this file to supported PCM WAV.",
                )
            )
            continue
        if relative.startswith("recordings/"):
            recordings_seen += 1
        else:
            positives_seen += 1
            positive_candidates.add(relative)
        cached_entry = old_inventory.get(relative)
        if cached_entry == current and relative in old_facts:
            headers[relative] = old_facts[relative]
        else:
            header_reads += 1
            try:
                header = _read_wav_header(entry)
                headers[relative] = Fingerprint(entry_stat.st_size, entry_stat.st_mtime_ns, header)
            except (OSError, ValueError) as exc:
                issues.append(
                    _issue(
                        "invalid_wav",
                        relative,
                        f"Invalid or unsupported WAV: {exc}",
                        "Re-export this file as nonempty mono or stereo PCM WAV.",
                    )
                )
        if progress and (total <= 64 or completed == total or completed % 64 == 0):
            progress(
                ScanProgress(
                    "Reading WAV headers",
                    completed,
                    total,
                    recordings_seen,
                    positives_seen,
                    len(issues),
                )
            )
        if step_delay_seconds:
            if isinstance(cancel, Event):
                cancel.wait(step_delay_seconds)
                _check_cancel(cancel)
            else:
                time.sleep(step_delay_seconds)

    _check_cancel(cancel)
    records = [
        SourceRecording(_source_id(path), path, fingerprint)
        for path, fingerprint in sorted(headers.items())
        if path.startswith("recordings/")
    ]
    if not records:
        issues.append(
            _issue(
                "no_recordings",
                "recordings/",
                "No usable Source Recordings were found.",
                "Add at least one supported PCM WAV directly under recordings/.",
            )
        )
    exact_sources: dict[str, str | tuple[str, ...]] = {}
    for record in records:
        existing = exact_sources.get(record.stem)
        if existing is None:
            exact_sources[record.stem] = record.id
        elif isinstance(existing, tuple):
            exact_sources[record.stem] = (*existing, record.id)
        else:
            exact_sources[record.stem] = (existing, record.id)
    records_by_id = {record.id: record for record in records}
    positive_counts = {record.id: 0 for record in records}
    seen_intervals: set[tuple[str, int, int]] = set()
    positives: list[PositiveExample] = []
    positive_paths = sorted(
        (entry for entry in inventory if entry.relative_path in positive_candidates),
        key=lambda entry: entry.relative_path,
    )
    # Iterate from the inventory rather than headers so malformed WAVs still receive name guidance.
    for entry_info in positive_paths:
        relative = entry_info.relative_path
        if not relative.casefold().endswith(".wav"):
            continue
        fingerprint = headers.get(relative)
        parsed = None
        source_id = None
        basename = relative.rsplit("/", 1)[-1]
        try:
            parsed = parse_positive_filename(basename)
        except ValueError as exc:
            message = str(exc)
            if "__start-" not in basename.casefold() or "__end-" not in basename.casefold():
                message = "Positive has no timestamps."
            issues.append(
                _issue(
                    "malformed_positive_name",
                    relative,
                    message,
                    "Rename it to SOURCE__start-Nms__end-Nms__LABEL.wav.",
                )
            )
        if parsed is not None:
            try:
                source_id = str(validate_source_match(parsed.source_stem, exact_sources))
            except ValueError as exc:
                issues.append(
                    _issue(
                        "unknown_source" if str(exc).startswith("Unknown") else "ambiguous_source",
                        relative,
                        str(exc),
                        "Use the exact complete stem of one WAV under recordings/.",
                    )
                )
            if source_id is not None and fingerprint is not None:
                try:
                    validate_interval(
                        parsed.start_ms,
                        parsed.end_ms,
                        records_by_id[source_id].fingerprint.header,
                        fingerprint.header,
                    )
                    ensure_unique_interval(
                        source_id, parsed.start_ms, parsed.end_ms, seen_intervals
                    )
                except ValueError as exc:
                    message = str(exc)
                    if "Duplicate" in message:
                        code = "duplicate_interval"
                    elif "outside" in message:
                        code = "interval_out_of_bounds"
                    elif "duration disagrees" in message:
                        code = "duration_mismatch"
                    else:
                        code = "invalid_interval"
                    issues.append(
                        _issue(
                            code,
                            relative,
                            str(exc),
                            "Correct the source-time bounds or re-export the positive WAV.",
                        )
                    )
                    source_id = None
                else:
                    positive_counts[source_id] += 1
        positives.append(
            PositiveExample(
                relative,
                source_id,
                parsed.start_ms if parsed else None,
                parsed.end_ms if parsed else None,
                parsed.label if parsed else None,
                fingerprint,
            )
        )
    if not positives:
        issues.append(
            _issue(
                "no_positives",
                "positives/",
                "No Positive Examples were found.",
                "Add at least one timestamped PCM WAV directly under positives/.",
            )
        )
    records = [replace(record, positive_count=positive_counts[record.id]) for record in records]
    if progress:
        progress(
            ScanProgress(
                "Checking filenames and timestamps",
                total,
                total,
                recordings_seen,
                positives_seen,
                len(issues),
            )
        )
    return ScanResult(
        root.name,
        tuple(records),
        tuple(positives),
        tuple(issues),
        tuple(sorted(inventory, key=lambda entry: entry.relative_path)),
        header_reads,
        cached.collection_id if cached else None,
    )


def inputs_match_scan(root: Path, result: ScanResult) -> bool:
    """Compare the cheap complete inventory used for Build readiness gating."""
    root = Path(root)
    if not root.is_dir():
        return False
    current, issues = _current_inventory(root.resolve(strict=True))
    if issues:
        return False
    cached = {entry.relative_path: entry for entry in result.inventory}
    return current == cached
