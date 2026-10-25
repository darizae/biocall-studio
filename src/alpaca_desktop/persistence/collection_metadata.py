"""Versioned, atomically published Collection metadata."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import asdict, replace
from pathlib import Path

from alpaca_desktop.domain.collection import (
    CollectionIssue,
    Fingerprint,
    InventoryEntry,
    PositiveExample,
    ScanResult,
    SourceRecording,
    WavHeader,
)
from alpaca_desktop.domain.paths import validate_relative_path

SCHEMA_VERSION = 1
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
    }
    if not required.issubset(raw) or raw["valid"] is not True:
        raise ValueError("Invalid Collection metadata manifest.")
    if not isinstance(raw["collection_id"], str) or not raw["collection_id"]:
        raise ValueError("Invalid Collection identity in metadata manifest.")
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
    if not isinstance(raw["inventory"], list) or not isinstance(raw["summary"], dict):
        raise ValueError("Invalid Collection inventory or summary.")
    return raw


def _json_line(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _write_partitioned(
    directory: Path, prefix: str, rows: Iterable[dict]
) -> tuple[list[str], list[Path]]:
    directory.mkdir(parents=True, exist_ok=True)
    relative_paths: list[str] = []
    created: list[Path] = []
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
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            for line in partition:
                stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        relative_paths.append(relative)
        created.append(target)
        partition = []
        byte_count = 0

    for row in rows:
        line = _json_line(row)
        if len(line) > MAX_PARTITION_BYTES:
            raise ValueError("One Collection metadata row exceeds the 16 MiB partition ceiling.")
        if partition and (
            len(partition) >= MAX_PARTITION_ROWS or byte_count + len(line) > MAX_PARTITION_BYTES
        ):
            flush()
        partition.append(line)
        byte_count += len(line)
    flush()
    return relative_paths, created


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


def publish_collection_metadata(root: Path, result: ScanResult) -> ScanResult:
    """Publish partition files first and the authoritative manifest last."""
    root = root.resolve(strict=True)
    if not result.valid:
        raise ValueError("Invalid Collection Scan results cannot be published.")
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
        record_refs, record_files = _write_partitioned(records_directory, token, record_rows)
        positive_refs, positive_files = _write_partitioned(
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
            "header_reads": published.header_reads,
        }
        validate_collection_manifest(manifest)
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


def _load_rows(alpaca: Path, references: list[str]) -> list[dict]:
    rows: list[dict] = []
    root = alpaca.resolve(strict=True)
    for reference in references:
        candidate = alpaca / reference
        if candidate.is_symlink():
            raise ValueError(f"Collection metadata partition cannot be a symlink: {reference}")
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError(f"Collection metadata partition escapes .alpaca/: {reference}")
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL row {number} in {reference}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"Invalid JSONL row {number} in {reference}")
                rows.append(value)
    return rows


def _fingerprint_from_json(raw: dict) -> Fingerprint:
    header = raw["header"]
    return Fingerprint(
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
            for row in _load_rows(alpaca, manifest["record_partitions"])
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
            for row in _load_rows(alpaca, manifest["positive_partitions"])
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
    return ScanResult(
        str(manifest["collection_name"]),
        records,
        positives,
        tuple[CollectionIssue, ...](),
        inventory,
        int(manifest.get("header_reads", 0)),
        str(manifest["collection_id"]),
        str(manifest["scanned_at"]),
    )
