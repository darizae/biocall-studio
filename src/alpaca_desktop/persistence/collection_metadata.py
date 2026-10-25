"""Versioned, atomically published Collection metadata."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

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
    validate_wav_header,
)
from alpaca_desktop.domain.paths import ensure_unique_portable_paths, validate_relative_path

SCHEMA_VERSION = 2
MAX_PARTITION_ROWS = 10_000
MAX_PARTITION_BYTES = 16 * 1024 * 1024


def _metadata_root(root: Path, *, create: bool) -> Path:
    alpaca = root / ".alpaca"
    if alpaca.is_symlink():
        raise ValueError("Collection metadata folder .alpaca/ cannot be a symlink.")
    if create:
        alpaca.mkdir(exist_ok=True)
    resolved = alpaca.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("Collection metadata folder escapes the selected Collection.")
    return resolved


def _metadata_directory(alpaca: Path, name: str) -> Path:
    directory = alpaca / name
    if directory.is_symlink():
        raise ValueError(f"Collection metadata folder {name}/ cannot be a symlink.")
    directory.mkdir(exist_ok=True)
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(alpaca):
        raise ValueError(f"Collection metadata folder {name}/ escapes .alpaca/.")
    return resolved


def validate_collection_manifest(raw: object) -> dict:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported Collection metadata schema.")
    required = {
        "collection_id",
        "collection_name",
        "scanned_at",
        "valid",
        "summary",
        "inventory",
        "record_partitions",
        "positive_partitions",
        "partition_sha256",
        "header_reads",
    }
    if not required.issubset(raw) or raw["valid"] is not True:
        raise ValueError("Invalid Collection metadata manifest.")
    if not isinstance(raw["collection_id"], str) or not raw["collection_id"]:
        raise ValueError("Invalid Collection identity in metadata manifest.")
    if (
        not isinstance(raw["collection_name"], str)
        or not raw["collection_name"]
        or not isinstance(raw["scanned_at"], str)
        or not raw["scanned_at"]
        or type(raw["header_reads"]) is not int
        or raw["header_reads"] < 0
    ):
        raise ValueError("Invalid Collection metadata manifest facts.")
    try:
        datetime.fromisoformat(raw["scanned_at"])
    except ValueError as exc:
        raise ValueError("Invalid Collection metadata manifest facts.") from exc
    references: list[str] = []
    for key, prefix in (
        ("record_partitions", "records/"),
        ("positive_partitions", "positives/"),
    ):
        values = raw[key]
        if not isinstance(values, list):
            raise ValueError(f"Invalid {key} in Collection metadata manifest.")
        for value in values:
            try:
                safe = validate_relative_path(value)
            except ValueError as exc:
                raise ValueError(f"Unsafe partition reference: {value!r}") from exc
            if not safe.startswith(prefix) or not safe.endswith(".jsonl"):
                raise ValueError(f"Invalid partition reference: {value!r}")
            references.append(safe)
    if len(references) != len(set(references)):
        raise ValueError("Duplicate Collection metadata partition reference.")
    digests = raw["partition_sha256"]
    if (
        not isinstance(digests, dict)
        or set(digests) != set(references)
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in digests.values()
        )
    ):
        raise ValueError("Invalid Collection metadata partition digest map.")
    if not isinstance(raw["inventory"], list) or not isinstance(raw["summary"], dict):
        raise ValueError("Invalid Collection inventory or summary.")
    return raw


def _json_line(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _write_partitioned(
    directory: Path, prefix: str, rows: Iterable[dict]
) -> tuple[list[str], list[Path], dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    relative_paths: list[str] = []
    created: list[Path] = []
    digests: dict[str, str] = {}
    partition: list[bytes] = []
    byte_count = 0

    def flush() -> None:
        nonlocal partition, byte_count
        if not partition:
            return
        number = len(relative_paths) + 1
        relative = f"{directory.name}/{prefix}-part-{number:05d}.jsonl"
        target = directory.parent / relative
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite Collection metadata partition: {target}")
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            for line in partition:
                stream.write(line)
                digest.update(line)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        relative_paths.append(relative)
        created.append(target)
        digests[relative] = digest.hexdigest()
        partition = []
        byte_count = 0

    try:
        for row in rows:
            line = _json_line(row)
            if len(line) > MAX_PARTITION_BYTES:
                raise ValueError(
                    "One Collection metadata row exceeds the 16 MiB partition ceiling."
                )
            if partition and (
                len(partition) >= MAX_PARTITION_ROWS or byte_count + len(line) > MAX_PARTITION_BYTES
            ):
                flush()
            partition.append(line)
            byte_count += len(line)
        flush()
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return relative_paths, created, digests


def _write_manifest_atomic(path: Path, raw: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as stream:
        temporary = Path(stream.name)
        json.dump(raw, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fingerprint_json(fingerprint: Fingerprint) -> dict:
    return {
        "size_bytes": fingerprint.size_bytes,
        "mtime_ns": fingerprint.mtime_ns,
        "header": asdict(fingerprint.header),
    }


def _load_manifest(alpaca: Path) -> dict:
    manifest_path = alpaca / "collection.json"
    if manifest_path.is_symlink():
        raise ValueError("Collection metadata manifest cannot be a symlink.")
    try:
        with manifest_path.open(encoding="utf-8") as stream:
            return validate_collection_manifest(json.load(stream))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Collection metadata at {manifest_path}") from exc


def _validate_result_facts(result: ScanResult) -> dict[str, InventoryEntry]:
    """Enforce canonical Scan facts once at the metadata trust boundary."""
    if not result.valid or not result.records or not result.positives:
        raise ValueError("Only a complete valid Collection Scan can be published.")
    if not result.root_name or not result.scanned_at or result.header_reads < 0:
        raise ValueError("Collection Scan identity or counters are invalid.")
    try:
        datetime.fromisoformat(result.scanned_at)
    except ValueError as exc:
        raise ValueError("Collection Scan timestamp is invalid.") from exc
    if result.collection_id is not None and not result.collection_id:
        raise ValueError("Collection Scan identity is invalid.")

    inventory: dict[str, InventoryEntry] = {}
    for entry in result.inventory:
        path = validate_relative_path(entry.relative_path)
        if path in inventory or path.count("/") != 1:
            raise ValueError("Collection inventory paths must be unique direct children.")
        if not path.startswith(("recordings/", "positives/")) or entry.size_bytes < 0:
            raise ValueError("Collection inventory contains an invalid input path or size.")
        inventory[path] = entry
    ensure_unique_portable_paths(list(inventory))

    records_by_id: dict[str, SourceRecording] = {}
    input_paths: set[str] = set()
    for record in result.records:
        path = validate_relative_path(record.relative_path)
        if (
            not record.id
            or record.id in records_by_id
            or not path.startswith("recordings/")
            or path.count("/") != 1
        ):
            raise ValueError("Collection Scan contains an invalid Source Recording.")
        entry = inventory.get(path)
        if entry is None or (entry.size_bytes, entry.mtime_ns) != (
            record.fingerprint.size_bytes,
            record.fingerprint.mtime_ns,
        ):
            raise ValueError("Source Recording fingerprint does not match the inventory.")
        validate_wav_header(record.fingerprint.header)
        records_by_id[record.id] = record
        input_paths.add(path)

    positive_counts = {record_id: 0 for record_id in records_by_id}
    seen_intervals: set[tuple[str, int, int]] = set()
    for positive in result.positives:
        path = validate_relative_path(positive.relative_path)
        if (
            path in input_paths
            or not path.startswith("positives/")
            or path.count("/") != 1
            or positive.fingerprint is None
            or positive.source_recording_id not in records_by_id
            or type(positive.start_ms) is not int
            or type(positive.end_ms) is not int
            or not positive.label
        ):
            raise ValueError("Collection Scan contains an invalid Positive Example.")
        entry = inventory.get(path)
        if entry is None or (entry.size_bytes, entry.mtime_ns) != (
            positive.fingerprint.size_bytes,
            positive.fingerprint.mtime_ns,
        ):
            raise ValueError("Positive Example fingerprint does not match the inventory.")
        validate_wav_header(positive.fingerprint.header)
        source = records_by_id[positive.source_recording_id]
        parsed = parse_positive_filename(path.rsplit("/", 1)[-1])
        if (
            parsed.source_stem != source.stem
            or parsed.start_ms != positive.start_ms
            or parsed.end_ms != positive.end_ms
            or parsed.label != positive.label
        ):
            raise ValueError("Positive Example facts do not match its filename.")
        validate_interval(
            positive.start_ms,
            positive.end_ms,
            source.fingerprint.header,
            positive.fingerprint.header,
        )
        ensure_unique_interval(
            positive.source_recording_id,
            positive.start_ms,
            positive.end_ms,
            seen_intervals,
        )
        positive_counts[positive.source_recording_id] += 1
        input_paths.add(path)

    if input_paths != set(inventory) or any(
        record.positive_count != positive_counts[record.id] for record in result.records
    ):
        raise ValueError("Collection Scan facts do not match its complete inventory.")
    return inventory


def _current_input_inventory(root: Path) -> dict[str, InventoryEntry]:
    inventory: dict[str, InventoryEntry] = {}
    for folder_name in ("recordings", "positives"):
        folder = root / folder_name
        if not folder.is_dir():
            raise ValueError(
                f"Required input folder changed after the Collection Scan: {folder_name}/"
            )
        resolved_folder = folder.resolve(strict=True)
        if not resolved_folder.is_relative_to(root):
            raise ValueError(f"Input folder escaped after the Collection Scan: {folder_name}/")
        for entry in folder.iterdir():
            relative = entry.relative_to(root).as_posix()
            validate_relative_path(relative)
            resolved = entry.resolve(strict=True)
            if not resolved.is_relative_to(root) or not entry.is_file():
                raise ValueError(f"Input path changed after the Collection Scan: {relative}")
            stat = entry.stat()
            inventory[relative] = InventoryEntry(relative, stat.st_size, stat.st_mtime_ns)
    ensure_unique_portable_paths(list(inventory))
    return inventory


def publish_collection_metadata(root: Path, result: ScanResult) -> ScanResult:
    """Publish partition files first and the authoritative manifest last."""
    root = root.resolve(strict=True)
    expected_inventory = _validate_result_facts(result)
    if result.root_name != root.name or _current_input_inventory(root) != expected_inventory:
        raise ValueError("Collection inputs changed after the Collection Scan; rescan required.")
    alpaca = _metadata_root(root, create=True)
    records_directory = _metadata_directory(alpaca, "records")
    positives_directory = _metadata_directory(alpaca, "positives")
    collection_id = result.collection_id
    if collection_id is None:
        try:
            collection_id = str(_load_manifest(alpaca)["collection_id"])
        except (FileNotFoundError, OSError, ValueError):
            collection_id = f"collection-{uuid.uuid4()}"
    published = replace(result, collection_id=collection_id)
    token = uuid.uuid4().hex
    created: list[Path] = []
    try:
        record_rows = (
            {
                "id": record.id,
                "relative_path": record.relative_path,
                "fingerprint": _fingerprint_json(record.fingerprint),
                "positive_count": record.positive_count,
            }
            for record in published.records
        )
        positive_rows = (
            {
                "relative_path": positive.relative_path,
                "source_recording_id": positive.source_recording_id,
                "start_ms": positive.start_ms,
                "end_ms": positive.end_ms,
                "label": positive.label,
                "fingerprint": (
                    _fingerprint_json(positive.fingerprint) if positive.fingerprint else None
                ),
            }
            for positive in published.positives
        )
        record_refs, record_files, record_digests = _write_partitioned(
            records_directory, token, record_rows
        )
        positive_refs, positive_files, positive_digests = _write_partitioned(
            positives_directory, token, positive_rows
        )
        created.extend(record_files)
        created.extend(positive_files)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "collection_id": collection_id,
            "collection_name": published.root_name,
            "scanned_at": published.scanned_at,
            "valid": True,
            "summary": {
                "recordings": published.recording_count,
                "positives": published.positive_count,
                "duration_seconds": published.duration_seconds,
            },
            "inventory": [asdict(entry) for entry in published.inventory],
            "record_partitions": record_refs,
            "positive_partitions": positive_refs,
            "partition_sha256": record_digests | positive_digests,
            "header_reads": published.header_reads,
        }
        validate_collection_manifest(manifest)
        if _current_input_inventory(root) != expected_inventory:
            raise ValueError(
                "Collection inputs changed after the Collection Scan; rescan required."
            )
        _write_manifest_atomic(alpaca / "collection.json", manifest)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    try:
        _remove_unreferenced_partitions(alpaca, set(record_refs + positive_refs))
    except OSError:
        # Unreferenced cache generations are harmless and can be removed on a later refresh.
        pass
    return published


def _remove_unreferenced_partitions(alpaca: Path, referenced: set[str]) -> None:
    for directory_name in ("records", "positives"):
        directory = alpaca / directory_name
        if not directory.exists():
            continue
        for path in directory.glob("*.jsonl"):
            if path.relative_to(alpaca).as_posix() not in referenced:
                path.unlink()


def _load_rows(alpaca: Path, references: list[str], digests: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    root = alpaca.resolve(strict=True)
    for reference in references:
        candidate = alpaca / reference
        if candidate.is_symlink():
            raise ValueError(f"Collection metadata partition cannot be a symlink: {reference}")
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError(f"Collection metadata partition escapes .alpaca/: {reference}")
        if path.stat().st_size > MAX_PARTITION_BYTES:
            raise ValueError(f"Collection metadata partition exceeds 16 MiB: {reference}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for number, line in enumerate(stream, 1):
                if number > MAX_PARTITION_ROWS or len(line) > MAX_PARTITION_BYTES:
                    raise ValueError(f"Collection metadata partition exceeds limits: {reference}")
                digest.update(line)
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ValueError(f"Invalid JSONL row {number} in {reference}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"Invalid JSONL row {number} in {reference}")
                rows.append(value)
        if digest.hexdigest() != digests[reference]:
            raise ValueError(f"Collection metadata partition digest mismatch: {reference}")
    return rows


def _fingerprint_from_json(raw: dict) -> Fingerprint:
    header = raw["header"]
    fingerprint = Fingerprint(
        int(raw["size_bytes"]),
        int(raw["mtime_ns"]),
        WavHeader(
            str(header["codec"]),
            int(header["channels"]),
            int(header["sample_rate_hz"]),
            int(header["sample_width_bytes"]),
            int(header["frame_count"]),
        ),
    )
    if fingerprint.size_bytes < 0:
        raise ValueError("Invalid cached WAV size.")
    validate_wav_header(fingerprint.header)
    return fingerprint


def load_collection_metadata(root: Path) -> ScanResult:
    root = root.resolve(strict=True)
    alpaca = _metadata_root(root, create=False)
    try:
        manifest = _load_manifest(alpaca)
        records = tuple(
            SourceRecording(
                str(row["id"]),
                validate_relative_path(row["relative_path"]),
                _fingerprint_from_json(row["fingerprint"]),
                int(row["positive_count"]),
            )
            for row in _load_rows(
                alpaca, manifest["record_partitions"], manifest["partition_sha256"]
            )
        )
        positives = tuple(
            PositiveExample(
                validate_relative_path(row["relative_path"]),
                str(row["source_recording_id"]),
                int(row["start_ms"]),
                int(row["end_ms"]),
                str(row["label"]),
                _fingerprint_from_json(row["fingerprint"]),
            )
            for row in _load_rows(
                alpaca, manifest["positive_partitions"], manifest["partition_sha256"]
            )
        )
        inventory = tuple(
            InventoryEntry(
                validate_relative_path(row["relative_path"]),
                int(row["size_bytes"]),
                int(row["mtime_ns"]),
            )
            for row in manifest["inventory"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Collection metadata contents.") from exc
    result = ScanResult(
        str(manifest["collection_name"]),
        records,
        positives,
        tuple[CollectionIssue, ...](),
        inventory,
        int(manifest.get("header_reads", 0)),
        str(manifest["collection_id"]),
        str(manifest["scanned_at"]),
    )
    try:
        _validate_result_facts(result)
        summary = manifest["summary"]
        if (
            summary.get("recordings") != result.recording_count
            or summary.get("positives") != result.positive_count
            or summary.get("duration_seconds") != result.duration_seconds
        ):
            raise ValueError("Collection metadata summary does not match its partitions.")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Collection metadata contents.") from exc
    return result
