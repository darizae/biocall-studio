"""Verified immutable Dataset reopen, listing, and explicit deletion."""

from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from biocall_studio_train.domain.dataset import validate_dataset_manifest, validate_snippet_record
from biocall_studio_train.domain.paths import validate_relative_path
from biocall_studio_train.persistence.integrity import sha256_file

MAX_ENTRY_ROWS = 10_000
MAX_ENTRY_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class DatasetArtifact:
    root: Path
    manifest: dict
    snippets: tuple[dict, ...]

    @property
    def dataset_id(self) -> str:
        return self.manifest["dataset_id"]

    @property
    def label(self) -> str:
        return self.manifest["label"]


@dataclass(frozen=True)
class DatasetDeletion:
    dataset_id: str
    dependent_model_ids: tuple[str, ...]


def _dataset_root(collection_root: Path, dataset_id: str) -> Path:
    safe_id = validate_relative_path(dataset_id)
    if "/" in safe_id:
        raise ValueError("Dataset ID must be one portable path segment.")
    collection = collection_root.resolve(strict=True)
    alpaca = collection / ".alpaca"
    datasets = alpaca / "datasets"
    if alpaca.is_symlink() or datasets.is_symlink():
        raise ValueError("Dataset storage cannot use symlinks.")
    if datasets.exists() and not datasets.resolve(strict=True).is_relative_to(collection):
        raise ValueError("Dataset storage escapes the selected Collection.")
    candidate = datasets / safe_id
    if candidate.is_symlink():
        raise ValueError("Dataset directory cannot be a symlink.")
    return candidate


def _contained_file(root: Path, reference: str) -> Path:
    safe = validate_relative_path(reference)
    candidate = root / safe
    if candidate.is_symlink():
        raise ValueError(f"Dataset file cannot be a symlink: {safe}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise ValueError(f"Dataset reference escapes its immutable directory: {safe}")
    return resolved


def _read_manifest(root: Path) -> dict:
    path = _contained_file(root, "dataset.json")
    if path.stat().st_size > MAX_ENTRY_BYTES:
        raise ValueError("Dataset manifest exceeds 16 MiB.")
    try:
        with path.open(encoding="utf-8") as stream:
            return validate_dataset_manifest(json.load(stream))
    except json.JSONDecodeError as exc:
        raise ValueError("Dataset manifest is invalid JSON.") from exc


def _read_entries(root: Path, references: list[dict]) -> tuple[dict, ...]:
    rows: list[dict] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for reference in references:
        path = _contained_file(root, reference["path"])
        if path.stat().st_size > MAX_ENTRY_BYTES:
            raise ValueError(f"Dataset entry partition exceeds 16 MiB: {reference['path']}")
        if sha256_file(path) != reference["sha256"]:
            raise ValueError(f"Dataset entry partition digest mismatch: {reference['path']}")
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if line_number > MAX_ENTRY_ROWS:
                    raise ValueError(
                        f"Dataset entry partition exceeds 10000 rows: {reference['path']}"
                    )
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid Dataset Snippet row {line_number}: {reference['path']}"
                    ) from exc
                if not isinstance(row, dict):
                    raise ValueError("Dataset Snippet row must be an object.")
                validate_snippet_record(row)
                snippet_id = row["snippet_id"]
                relative = validate_relative_path(row["relative_path"])
                if (
                    not isinstance(snippet_id, str)
                    or not snippet_id
                    or snippet_id in seen_ids
                    or relative in seen_paths
                    or row["label"] not in {"target", "noise"}
                    or row["split"] not in {"train", "val"}
                ):
                    raise ValueError("Dataset Snippet identity, label, or Split is invalid.")
                snippet_path = _contained_file(root, relative)
                if sha256_file(snippet_path) != row["sha256"]:
                    raise ValueError(f"Dataset Snippet digest mismatch: {relative}")
                seen_ids.add(snippet_id)
                seen_paths.add(relative)
                rows.append(row)
    return tuple(rows)


def _validate_splits(root: Path, manifest: dict, snippets: tuple[dict, ...]) -> None:
    expected = {split: [] for split in ("train", "val")}
    for row in snippets:
        expected[row["split"]].append(
            (row["snippet_id"], row["relative_path"], row["label"], row["source_recording_id"])
        )
    for split in ("train", "val"):
        reference = manifest["splits"][split]
        path = _contained_file(root, reference["path"])
        if sha256_file(path) != reference["sha256"]:
            raise ValueError(f"Dataset Split digest mismatch: {reference['path']}")
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != [
                "snippet_id",
                "relative_path",
                "label",
                "source_recording_id",
            ]:
                raise ValueError(f"Dataset Split columns are invalid: {reference['path']}")
            actual = [
                (row["snippet_id"], row["relative_path"], row["label"], row["source_recording_id"])
                for row in reader
            ]
        if actual != expected[split]:
            raise ValueError(f"Dataset Split membership disagrees with Snippet entries: {split}")


def load_dataset(collection_root: Path, dataset_id: str) -> DatasetArtifact:
    root = _dataset_root(collection_root, dataset_id)
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset does not exist: {dataset_id}")
    return load_dataset_directory(root, dataset_id)


def load_dataset_directory(root: Path, expected_dataset_id: str) -> DatasetArtifact:
    """Verify a contained published or private staged Dataset directory."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Dataset directory is missing or unsafe.")
    root = root.resolve(strict=True)
    manifest = _read_manifest(root)
    if manifest["dataset_id"] != expected_dataset_id:
        raise ValueError("Dataset directory identity does not match its manifest.")
    snippets = _read_entries(root, manifest["entries"])
    counts = manifest["counts"]
    sources = {
        source["id"]: (source["relative_path"], source["sha256"])
        for source in manifest["selected_sources"]
    }
    positives = {positive["relative_path"]: positive for positive in manifest["positive_inputs"]}
    for snippet in snippets:
        source = sources.get(snippet["source_recording_id"])
        if (
            source is None
            or (snippet["source_ref"], snippet["source_sha256"]) != source
            or snippet["split"] != manifest["source_groups"][snippet["source_recording_id"]]
        ):
            raise ValueError("Dataset Snippet disagrees with its source provenance or Split.")
        if snippet["label"] == "target":
            positive = positives.get(snippet["producing_positive_ref"])
            if (
                positive is None
                or positive["source_recording_id"] != snippet["source_recording_id"]
                or positive["start_ms"] != snippet["start_ms"]
                or positive["end_ms"] != snippet["end_ms"]
            ):
                raise ValueError("Target Snippet disagrees with its Positive Example provenance.")
    target_positive_refs = [
        snippet["producing_positive_ref"] for snippet in snippets if snippet["label"] == "target"
    ]
    if len(target_positive_refs) != len(positives) or set(target_positive_refs) != set(positives):
        raise ValueError("Dataset targets must map one-to-one to its Positive Example provenance.")
    if (
        sum(row["label"] == "target" for row in snippets) != counts["target"]
        or sum(row["label"] == "noise" for row in snippets) != counts["noise"]
        or len(snippets) != counts["total"]
        or any(
            sum(row["label"] == label and row["split"] == split for row in snippets)
            != counts[split][label]
            for split in ("train", "val")
            for label in ("target", "noise")
        )
    ):
        raise ValueError("Dataset manifest counts disagree with Snippet entries.")
    _validate_splits(root, manifest, snippets)
    return DatasetArtifact(root, manifest, snippets)


def list_datasets(collection_root: Path) -> tuple[DatasetArtifact, ...]:
    root = collection_root.resolve(strict=True) / ".alpaca" / "datasets"
    if not root.exists():
        return ()
    if (
        root.is_symlink()
        or not root.is_dir()
        or not root.resolve(strict=True).is_relative_to(collection_root.resolve(strict=True))
    ):
        raise ValueError("Dataset storage must be a contained directory.")
    artifacts = [
        load_dataset(collection_root, path.name) for path in root.iterdir() if path.is_dir()
    ]
    artifacts.sort(key=lambda item: item.manifest["created_at"], reverse=True)
    return tuple(artifacts)


def _dependent_model_ids(collection_root: Path, dataset_id: str) -> tuple[str, ...]:
    models = collection_root.resolve(strict=True) / ".alpaca" / "models"
    if not models.exists():
        return ()
    dependencies: list[str] = []
    for path in models.iterdir():
        manifest = path / "model.json"
        if (
            path.is_symlink()
            or not path.is_dir()
            or manifest.is_symlink()
            or not manifest.is_file()
        ):
            continue
        try:
            with manifest.open(encoding="utf-8") as stream:
                raw = json.load(stream)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and raw.get("dataset_id") == dataset_id:
            dependencies.append(str(raw.get("model_id") or path.name))
    return tuple(sorted(dependencies))


def dataset_dependents(collection_root: Path, dataset_id: str) -> tuple[str, ...]:
    """Return retained Models whose provenance names this Dataset."""
    load_dataset(collection_root, dataset_id)
    return _dependent_model_ids(collection_root, dataset_id)


def delete_dataset(
    collection_root: Path,
    dataset_id: str,
    *,
    reserved_dataset_ids: set[str] | frozenset[str] = frozenset(),
) -> DatasetDeletion:
    if dataset_id in reserved_dataset_ids:
        raise ValueError("Cannot delete a Dataset reserved by the Active Run.")
    artifact = load_dataset(collection_root, dataset_id)
    dependencies = _dependent_model_ids(collection_root, dataset_id)
    shutil.rmtree(artifact.root)
    try:
        descriptor = os.open(artifact.root.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass
    return DatasetDeletion(dataset_id, dependencies)
