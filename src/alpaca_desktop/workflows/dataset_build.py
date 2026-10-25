"""Verified staged Dataset Build from one published Collection Scan handoff."""

from __future__ import annotations

import csv
import json
import os
import shutil
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alpaca_desktop.computation.audio import (
    AUDIO_TRANSFORM_POLICY,
    extract_pcm_segment,
    sha256_file,
)
from alpaca_desktop.domain.collection import (
    Fingerprint,
    PositiveExample,
    ScanResult,
    SourceRecording,
)
from alpaca_desktop.domain.dataset import (
    BuildConfig,
    Interval,
    MiningSource,
    assign_source_splits,
    plan_noise_windows,
    protected_intervals,
    validate_dataset_manifest,
)
from alpaca_desktop.domain.paths import validate_relative_path
from alpaca_desktop.persistence.datasets import (
    MAX_ENTRY_BYTES,
    MAX_ENTRY_ROWS,
    DatasetArtifact,
    load_dataset,
    load_dataset_directory,
)

SCIENTIFIC_REFERENCE = "alpaca-pipelines@91af5287dc18313f88902dc9696e8756274736b3"


class DatasetBuildError(RuntimeError):
    pass


class DatasetBuildUnderfill(DatasetBuildError):
    pass


class DatasetBuildCancelled(DatasetBuildError):
    pass


@dataclass(frozen=True)
class DatasetBuildRequest:
    run_id: str
    request_id: str
    collection_root: str
    collection_id: str
    config: BuildConfig
    dataset_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "collection_root": self.collection_root,
            "collection_id": self.collection_id,
            "config": self.config.to_dict(),
            "dataset_id": self.dataset_id,
        }

    @classmethod
    def from_dict(cls, raw: object) -> DatasetBuildRequest:
        if not isinstance(raw, dict) or raw.get("schema_version") != 2:
            raise ValueError("Unsupported Dataset Build request schema.")
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "collection_root",
            "collection_id",
            "config",
            "dataset_id",
        }
        if set(raw) != expected:
            raise ValueError("Dataset Build request fields do not match its schema.")
        identity = (
            raw.get("run_id"),
            raw.get("request_id"),
            raw.get("collection_root"),
            raw.get("collection_id"),
            raw.get("dataset_id"),
        )
        if any(not isinstance(value, str) or not value for value in identity):
            raise ValueError("Invalid Dataset Build request identity.")
        return cls(
            raw["run_id"],
            raw["request_id"],
            raw["collection_root"],
            raw["collection_id"],
            BuildConfig.from_dict(raw.get("config")),
            raw["dataset_id"],
        )


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise DatasetBuildCancelled("Dataset Build cancelled before publication.")


def _resolve_input(root: Path, relative_path: str) -> Path:
    safe = validate_relative_path(relative_path)
    candidate = root / safe
    if candidate.is_symlink():
        raise DatasetBuildError(f"Collection input changed to a symlink: {safe}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DatasetBuildError(f"Collection input is missing or changed: {safe}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise DatasetBuildError(f"Collection input escapes its selected folder: {safe}")
    return resolved


def _matches_fingerprint(path: Path, fingerprint: Fingerprint) -> bool:
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns) == (fingerprint.size_bytes, fingerprint.mtime_ns)


def _hash_verified_input(
    root: Path,
    relative_path: str,
    fingerprint: Fingerprint,
    cancelled: Callable[[], bool] | None,
) -> tuple[Path, str]:
    path = _resolve_input(root, relative_path)
    if not _matches_fingerprint(path, fingerprint):
        raise DatasetBuildError(f"Collection input changed after validation: {relative_path}")
    digest = sha256_file(path, cancelled=cancelled)
    if not _matches_fingerprint(path, fingerprint):
        raise DatasetBuildError(f"Collection input changed while hashing: {relative_path}")
    return path, digest


def _selected_inputs(
    root: Path,
    scan: ScanResult,
    config: BuildConfig,
    cancelled: Callable[[], bool] | None,
) -> tuple[
    tuple[SourceRecording, ...],
    tuple[PositiveExample, ...],
    dict[str, Path],
    dict[str, str],
    dict[str, str],
]:
    if not scan.valid or scan.collection_id is None:
        raise DatasetBuildError("Dataset Build requires a currently validated Collection.")
    selected_ids = set(config.selected_recording_ids)
    records_by_id = {record.id: record for record in scan.records}
    if selected_ids != selected_ids & records_by_id.keys():
        raise DatasetBuildError(
            "Selected Source Recording no longer exists in Collection metadata."
        )
    records = tuple(record for record in scan.records if record.id in selected_ids)
    positives = tuple(
        positive for positive in scan.positives if positive.source_recording_id in selected_ids
    )
    if len(records) < 2:
        raise DatasetBuildError(
            "Select at least two Source Recordings for a source-grouped train/val Split."
        )
    if not positives:
        raise DatasetBuildError("Selected Source Recordings contain no target Annotations.")

    paths: dict[str, Path] = {}
    source_hashes: dict[str, str] = {}
    positive_hashes: dict[str, str] = {}
    for record in records:
        path, digest = _hash_verified_input(
            root, record.relative_path, record.fingerprint, cancelled
        )
        paths[record.relative_path] = path
        source_hashes[record.id] = digest
    for positive in positives:
        if positive.fingerprint is None:
            raise DatasetBuildError(
                f"Positive Example lacks a validated fingerprint: {positive.relative_path}"
            )
        path, digest = _hash_verified_input(
            root, positive.relative_path, positive.fingerprint, cancelled
        )
        paths[positive.relative_path] = path
        positive_hashes[positive.relative_path] = digest
    return records, positives, paths, source_hashes, positive_hashes


def _mining_plan(
    records: tuple[SourceRecording, ...],
    positives: tuple[PositiveExample, ...],
    config: BuildConfig,
):
    sources: list[MiningSource] = []
    for record in records:
        annotations = tuple(
            Interval(positive.start_ms, positive.end_ms)
            for positive in positives
            if positive.source_recording_id == record.id
            and positive.start_ms is not None
            and positive.end_ms is not None
        )
        duration_ms = (
            record.fingerprint.header.frame_count
            * 1_000
            // record.fingerprint.header.sample_rate_hz
        )
        sources.append(
            MiningSource(
                record.id,
                duration_ms,
                protected_intervals(
                    annotations, duration_ms=duration_ms, margin_ms=config.margin_ms
                ),
                len(annotations),
            )
        )
    target_durations = tuple(
        positive.end_ms - positive.start_ms
        for positive in positives
        if positive.start_ms is not None and positive.end_ms is not None
    )
    requested = config.requested_negative_count(len(target_durations))
    if requested <= 0:
        raise DatasetBuildError("Request at least one noise Snippet for Dataset Build.")
    durations = tuple(target_durations[index % len(target_durations)] for index in range(requested))
    plan = plan_noise_windows(
        tuple(sources),
        window_durations_ms=durations,
        allocation=config.allocation,
        seed=config.seed,
        attempts_per_slot=config.attempts_per_slot,
    )
    if plan.underfill:
        record_names = {record.id: record.name for record in records}
        evidence = ", ".join(
            f"{record_names[source_id]}: {milliseconds} ms"
            for source_id, milliseconds in plan.eligible_ms_by_source.items()
        )
        raise DatasetBuildUnderfill(
            f"Negative Mining underfill: requested {plan.requested}, produced "
            f"{len(plan.windows)} after {plan.attempts} bounded attempts. "
            f"Eligible source-time by recording: {evidence}."
        )
    return plan


def estimate_dataset_build(scan: ScanResult, config: BuildConfig) -> dict[str, Any]:
    """Return the same deterministic count/mining/Split decisions used by the Worker."""
    selected_ids = set(config.selected_recording_ids)
    records = tuple(record for record in scan.records if record.id in selected_ids)
    positives = tuple(
        positive for positive in scan.positives if positive.source_recording_id in selected_ids
    )
    result: dict[str, Any] = {
        "source_count": len(records),
        "target": len(positives),
        "noise_requested": config.requested_negative_count(len(positives)),
        "noise_available": 0,
        "underfill": 0,
        "split": None,
        "error": "",
    }
    if len(records) < 2:
        result["error"] = (
            "Select at least two Source Recordings for a source-grouped train/val Split."
        )
        return result
    if not positives or result["noise_requested"] <= 0:
        result["error"] = "Select positives and request at least one noise Snippet."
        return result
    try:
        plan = _mining_plan(records, positives, config)
        noise_counts = Counter(window.source_recording_id for window in plan.windows)
        target_counts = Counter(positive.source_recording_id for positive in positives)
        groups = {
            record.id: {"target": target_counts[record.id], "noise": noise_counts[record.id]}
            for record in records
        }
        split = assign_source_splits(
            groups,
            train_percent=config.train_percent,
            seed=config.seed,
            balance_classes=config.balance_classes,
        )
    except DatasetBuildUnderfill as exc:
        result["underfill"] = result["noise_requested"]
        result["error"] = str(exc)
        return result
    except (ValueError, DatasetBuildError) as exc:
        result["error"] = str(exc)
        return result
    result["noise_available"] = len(plan.windows)
    result["split"] = split
    return result


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite staged Dataset file: {path}")
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_entry_partitions(stage: Path, snippets: list[dict]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    partition: list[bytes] = []
    size = 0

    def flush() -> None:
        nonlocal partition, size
        if not partition:
            return
        reference = f"entries/snippets-{len(references) + 1:05d}.jsonl"
        path = stage / reference
        _write_bytes(path, b"".join(partition))
        references.append({"path": reference, "sha256": sha256_file(path)})
        partition = []
        size = 0

    for snippet in snippets:
        line = (json.dumps(snippet, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(line) > MAX_ENTRY_BYTES:
            raise DatasetBuildError("One Dataset Snippet entry exceeds the 16 MiB ceiling.")
        if partition and (len(partition) >= MAX_ENTRY_ROWS or size + len(line) > MAX_ENTRY_BYTES):
            flush()
        partition.append(line)
        size += len(line)
    flush()
    return references


def _write_split(stage: Path, split: str, snippets: list[dict]) -> dict[str, str]:
    relative = f"splits/{split}.csv"
    path = stage / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["snippet_id", "relative_path", "label", "source_recording_id"],
            lineterminator="\n",
        )
        writer.writeheader()
        for snippet in snippets:
            if snippet["split"] == split:
                writer.writerow({field: snippet[field] for field in writer.fieldnames})
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": relative, "sha256": sha256_file(path)}


def _recheck_hashes(
    paths: dict[str, Path],
    expected: dict[str, str],
    cancelled: Callable[[], bool] | None,
) -> None:
    for key, digest in expected.items():
        path = paths[key]
        if sha256_file(path, cancelled=cancelled) != digest:
            raise DatasetBuildError(f"Collection input changed during Dataset Build: {key}")


def _publish(stage: Path, final: Path) -> None:
    final.parent.mkdir(parents=True, exist_ok=True)
    lock = final.parent / ".publish.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.fsync(descriptor)
        if final.exists():
            raise FileExistsError(f"Dataset already exists: {final.name}")
        os.rename(stage, final)
        try:
            directory = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def _owned_directory(parent: Path, name: str) -> Path:
    directory = parent / name
    if directory.is_symlink():
        raise DatasetBuildError(f"App-owned Dataset path cannot be a symlink: {name}")
    directory.mkdir(exist_ok=True)
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(parent.resolve(strict=True)):
        raise DatasetBuildError(f"App-owned Dataset path escapes .alpaca/: {name}")
    return resolved


def build_dataset(
    collection_root: Path,
    scan: ScanResult,
    config: BuildConfig,
    *,
    dataset_id: str | None = None,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    run_id: str | None = None,
    request_id: str | None = None,
) -> DatasetArtifact:
    """Materialize, verify, and exclusively publish one immutable Dataset."""
    root = collection_root.resolve(strict=True)
    dataset_id = dataset_id or f"dataset-{uuid.uuid4()}"
    safe_id = validate_relative_path(dataset_id)
    if "/" in safe_id:
        raise ValueError("Dataset ID must be one portable path segment.")
    alpaca = root / ".alpaca"
    if alpaca.is_symlink() or not alpaca.is_dir():
        raise DatasetBuildError("Validated Collection metadata folder is missing or unsafe.")
    staging_root = _owned_directory(alpaca, ".staging")
    datasets_root = _owned_directory(alpaca, "datasets")
    final = datasets_root / dataset_id
    if final.exists():
        raise FileExistsError(f"Dataset already exists: {dataset_id}")
    stage = staging_root / f"{dataset_id}-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        if progress is not None:
            progress(0, 2, "Validating Collection inputs")
        _check_cancelled(cancelled)
        records, positives, paths, source_hashes, positive_hashes = _selected_inputs(
            root, scan, config, cancelled
        )
        if progress is not None:
            progress(0, 18, "Validated Collection inputs")
        noise_plan = _mining_plan(records, positives, config)
        noise_counts = Counter(window.source_recording_id for window in noise_plan.windows)
        target_counts = Counter(positive.source_recording_id for positive in positives)
        groups = {
            record.id: {"target": target_counts[record.id], "noise": noise_counts[record.id]}
            for record in records
        }
        split = assign_source_splits(
            groups,
            train_percent=config.train_percent,
            seed=config.seed,
            balance_classes=config.balance_classes,
        )
        if progress is not None:
            progress(1, 35, "Mined negative Snippet windows")
        records_by_id = {record.id: record for record in records}
        snippets: list[dict] = []
        if progress is not None:
            progress(2, 45, "Writing target and noise Snippets")
        for index, positive in enumerate(
            sorted(
                positives,
                key=lambda item: (
                    item.source_recording_id or "",
                    item.start_ms or 0,
                    item.end_ms or 0,
                    item.relative_path,
                ),
            ),
            1,
        ):
            _check_cancelled(cancelled)
            if (
                positive.source_recording_id is None
                or positive.start_ms is None
                or positive.end_ms is None
            ):
                raise DatasetBuildError("Positive Example is missing source-time provenance.")
            record = records_by_id[positive.source_recording_id]
            relative = f"snippets/target/target-{index:06d}.wav"
            transform = extract_pcm_segment(
                paths[record.relative_path],
                stage / relative,
                start_ms=positive.start_ms,
                end_ms=positive.end_ms,
                cancelled=cancelled,
            )
            snippets.append(
                {
                    "snippet_id": f"target-{index:06d}",
                    "relative_path": relative,
                    "label": "target",
                    "source_recording_id": record.id,
                    "source_ref": record.relative_path,
                    "source_sha256": source_hashes[record.id],
                    "start_ms": positive.start_ms,
                    "end_ms": positive.end_ms,
                    "producing_positive_ref": positive.relative_path,
                    "split": split.assignments[record.id],
                    "transform": transform.to_dict(),
                    "sha256": sha256_file(stage / relative),
                }
            )
        for index, window in enumerate(noise_plan.windows, 1):
            _check_cancelled(cancelled)
            record = records_by_id[window.source_recording_id]
            relative = f"snippets/noise/noise-{index:06d}.wav"
            transform = extract_pcm_segment(
                paths[record.relative_path],
                stage / relative,
                start_ms=window.start_ms,
                end_ms=window.end_ms,
                cancelled=cancelled,
            )
            snippets.append(
                {
                    "snippet_id": f"noise-{index:06d}",
                    "relative_path": relative,
                    "label": "noise",
                    "source_recording_id": record.id,
                    "source_ref": record.relative_path,
                    "source_sha256": source_hashes[record.id],
                    "start_ms": window.start_ms,
                    "end_ms": window.end_ms,
                    "producing_positive_ref": None,
                    "split": split.assignments[record.id],
                    "transform": transform.to_dict(),
                    "sha256": sha256_file(stage / relative),
                }
            )

        if progress is not None:
            progress(2, 75, "Wrote train and val Snippets")

        entries = _write_entry_partitions(stage, snippets)
        split_refs = {name: _write_split(stage, name, snippets) for name in ("train", "val")}
        selected_sources = [
            {
                "id": record.id,
                "relative_path": record.relative_path,
                "sha256": source_hashes[record.id],
                "fingerprint": {
                    "size_bytes": record.fingerprint.size_bytes,
                    "mtime_ns": record.fingerprint.mtime_ns,
                    "sample_rate_hz": record.fingerprint.header.sample_rate_hz,
                    "channels": record.fingerprint.header.channels,
                    "sample_width_bytes": record.fingerprint.header.sample_width_bytes,
                    "frame_count": record.fingerprint.header.frame_count,
                },
            }
            for record in records
        ]
        positive_inputs = [
            {
                "relative_path": positive.relative_path,
                "source_recording_id": positive.source_recording_id,
                "start_ms": positive.start_ms,
                "end_ms": positive.end_ms,
                "sha256": positive_hashes[positive.relative_path],
            }
            for positive in positives
        ]
        counts = {
            "target": len(positives),
            "noise": len(noise_plan.windows),
            "total": len(snippets),
            "train": split.counts["train"],
            "val": split.counts["val"],
        }
        manifest = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "label": f"{scan.root_name} · Dataset",
            "collection_id": scan.collection_id,
            "collection_label": scan.root_name,
            "created_at": datetime.now(UTC).isoformat(),
            "config": config.to_dict(),
            "source_policy": {
                "audio_transform": AUDIO_TRANSFORM_POLICY,
                "scientific_reference": SCIENTIFIC_REFERENCE,
                "adaptation": (
                    "Protected integer-ms source windows and Source Recording grouped Splits; "
                    "pipeline orchestration/schema not reused."
                ),
            },
            "selected_sources": selected_sources,
            "positive_inputs": positive_inputs,
            "entries": entries,
            "splits": split_refs,
            "source_groups": split.assignments,
            "counts": counts,
        }
        if run_id is not None or request_id is not None:
            if not run_id or not request_id:
                raise ValueError("Dataset Run provenance requires Run and request IDs.")
            manifest["run"] = {"run_id": run_id, "request_id": request_id}
        validate_dataset_manifest(manifest)
        _write_bytes(
            stage / "dataset.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(),
        )
        combined_paths = {
            **{record.id: paths[record.relative_path] for record in records},
            **{positive.relative_path: paths[positive.relative_path] for positive in positives},
        }
        _recheck_hashes(
            combined_paths,
            source_hashes | positive_hashes,
            cancelled,
        )
        if progress is not None:
            progress(3, 88, "Verifying staged Dataset")
        _check_cancelled(cancelled)
        load_dataset_directory(stage, dataset_id)
        if progress is not None:
            progress(3, 96, "Publishing verified Dataset")
        _check_cancelled(cancelled)
        _publish(stage, final)
        return load_dataset(root, dataset_id)
    except InterruptedError as exc:
        raise DatasetBuildCancelled("Dataset Build cancelled before publication.") from exc
    finally:
        if stage.exists():
            shutil.rmtree(stage)
