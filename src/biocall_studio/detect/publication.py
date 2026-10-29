"""Contained staging and atomic immutable publication for Detect Worker artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from biocall_studio.detect.results import DetectionResult
from biocall_studio.detect.rf_refinement import DerivedResult, ResultArtifact
from biocall_studio.detect.runs import (
    DetectRunRequest,
    PublicationReceipt,
    canonical_digest,
    utc_now,
)

PUBLICATION_IDENTITY_SCHEMA_VERSION = 1
MAX_PUBLICATION_FILES = 1_000
MAX_PUBLICATION_BYTES = 64 * 1024 * 1024
_ARTIFACT_ID = re.compile(r"pub_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,127}")
_ARTIFACT_KINDS = frozenset(
    {"lifecycle_fixture", "detection_result", "derived_result"}
)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


@dataclass(frozen=True, slots=True)
class PublicationFile:
    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if _FILE_NAME.fullmatch(self.path) is None or self.path == "publication.json":
            raise ValueError("Publication file name is invalid.")
        if type(self.size_bytes) is not int or not 0 <= self.size_bytes <= MAX_PUBLICATION_BYTES:
            raise ValueError("Publication file size is invalid.")
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("Publication file digest is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, raw: object) -> PublicationFile:
        if not isinstance(raw, dict) or set(raw) != {"path", "size_bytes", "sha256"}:
            raise ValueError("Publication file entry is invalid.")
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class PublicationIdentity:
    schema_version: int
    run_id: str
    request_id: str
    launch_id: str
    artifact_id: str
    artifact_kind: str
    files: tuple[PublicationFile, ...]
    artifact_digest: str
    published_at: str

    def __post_init__(self) -> None:
        if self.schema_version != PUBLICATION_IDENTITY_SCHEMA_VERSION:
            raise ValueError("Unsupported publication identity schema.")
        if _ARTIFACT_ID.fullmatch(self.artifact_id) is None:
            raise ValueError("Publication artifact ID is invalid.")
        if self.artifact_kind not in _ARTIFACT_KINDS:
            raise ValueError("Publication artifact kind is unsupported.")
        if not self.files or len(self.files) > MAX_PUBLICATION_FILES:
            raise ValueError("Publication file index is invalid.")
        if tuple(sorted(self.files, key=lambda item: item.path)) != self.files:
            raise ValueError("Publication files must be uniquely and canonically ordered.")
        if len({item.path for item in self.files}) != len(self.files):
            raise ValueError("Publication file index contains duplicates.")
        if sum(item.size_bytes for item in self.files) > MAX_PUBLICATION_BYTES:
            raise ValueError("Publication exceeds its byte budget.")
        if _SHA256.fullmatch(self.artifact_digest) is None:
            raise ValueError("Publication digest is invalid.")
        expected = canonical_digest(self._unsigned_dict())
        if expected != self.artifact_digest:
            raise ValueError("Publication digest does not match its identity.")
        PublicationReceipt(
            schema_version=1,
            run_id=self.run_id,
            request_id=self.request_id,
            launch_id=self.launch_id,
            artifact_id=self.artifact_id,
            artifact_kind=self.artifact_kind,
            artifact_digest=self.artifact_digest,
            published_at=self.published_at,
        )

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "launch_id": self.launch_id,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "files": [item.to_dict() for item in self.files],
            "published_at": self.published_at,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "artifact_digest": self.artifact_digest}

    @classmethod
    def create(
        cls,
        request: DetectRunRequest,
        files: tuple[PublicationFile, ...],
        *,
        artifact_kind: str = "lifecycle_fixture",
        published_at: str | None = None,
    ) -> PublicationIdentity:
        moment = published_at or utc_now()
        unsigned = {
            "schema_version": PUBLICATION_IDENTITY_SCHEMA_VERSION,
            "run_id": request.run_id,
            "request_id": request.request_id,
            "launch_id": request.launch_id,
            "artifact_id": request.artifact_id,
            "artifact_kind": artifact_kind,
            "files": [item.to_dict() for item in files],
            "published_at": moment,
        }
        return cls(
            PUBLICATION_IDENTITY_SCHEMA_VERSION,
            request.run_id,
            request.request_id,
            request.launch_id,
            request.artifact_id,
            artifact_kind,
            files,
            canonical_digest(unsigned),
            moment,
        )

    @classmethod
    def from_dict(cls, raw: object) -> PublicationIdentity:
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "launch_id",
            "artifact_id",
            "artifact_kind",
            "files",
            "artifact_digest",
            "published_at",
        }
        if not isinstance(raw, dict) or set(raw) != expected or not isinstance(
            raw["files"], list
        ):
            raise ValueError("Publication identity document is invalid.")
        return cls(
            schema_version=raw["schema_version"],
            run_id=raw["run_id"],
            request_id=raw["request_id"],
            launch_id=raw["launch_id"],
            artifact_id=raw["artifact_id"],
            artifact_kind=raw["artifact_kind"],
            files=tuple(PublicationFile.from_dict(item) for item in raw["files"]),
            artifact_digest=raw["artifact_digest"],
            published_at=raw["published_at"],
        )

    def receipt(self) -> PublicationReceipt:
        return PublicationReceipt(
            schema_version=1,
            run_id=self.run_id,
            request_id=self.request_id,
            launch_id=self.launch_id,
            artifact_id=self.artifact_id,
            artifact_kind=self.artifact_kind,
            artifact_digest=self.artifact_digest,
            published_at=self.published_at,
        )


def _read_json(path: Path, *, limit: int = 1_048_576) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Publication metadata is missing or unsafe.")
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Publication metadata is corrupt.") from exc


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > 1_048_576:
        raise ValueError("Publication metadata exceeds 1 MiB.")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_directory(root: Path, candidate: Path, *, label: str) -> Path:
    if candidate.is_symlink():
        raise ValueError(f"{label} cannot be a symlink.")
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} is not contained in Detect storage.")
    return resolved


def stage_lifecycle_artifact(
    collection_root: Path,
    staging_path: Path,
    request: DetectRunRequest,
) -> PublicationIdentity:
    """Create a non-scientific artifact that proves only the publication boundary."""
    collection = Path(collection_root).resolve(strict=True)
    staging_root = _validate_directory(collection, collection / ".staging", label="Staging root")
    stage = Path(staging_path)
    if stage.exists() or stage.is_symlink():
        raise FileExistsError("The launch staging directory already exists.")
    if stage.parent.resolve(strict=True) != staging_root:
        raise ValueError("The launch staging directory is not contained.")
    stage.mkdir(mode=0o700)
    payload_path = stage / "lifecycle.json"
    payload = {
        "schema_version": 1,
        "purpose": "qprocess_lifecycle_boundary",
        "run_id": request.run_id,
        "request_id": request.request_id,
        "launch_id": request.launch_id,
        "scientific_result": False,
    }
    _write_new_json(payload_path, payload)
    payload_bytes = payload_path.read_bytes()
    files = (
        PublicationFile(
            "lifecycle.json",
            len(payload_bytes),
            hashlib.sha256(payload_bytes).hexdigest(),
        ),
    )
    identity = PublicationIdentity.create(request, files)
    _write_new_json(stage / "publication.json", identity.to_dict())
    _fsync_directory(stage)
    return identity


def stage_detection_result(
    collection_root: Path,
    staging_path: Path,
    request: DetectRunRequest,
    result: DetectionResult,
) -> PublicationIdentity:
    """Stage one complete metadata-only Result and its checksum index."""
    if (
        result.result_id != request.artifact_id
        or result.run_id != request.run_id
        or result.request_id != request.request_id
        or result.collection_id != request.collection_id
        or result.binding_revision != request.binding_revision
        or result.inventory_id != request.inventory_id
        or result.inventory_digest != request.inventory_digest
        or result.model_snapshot_id != request.model_snapshot_id
        or result.model_snapshot_digest != request.model_digest
        or result.settings.to_mapping() != dict(request.settings)
    ):
        raise ValueError("DetectionResult does not match its frozen Run request.")
    collection = Path(collection_root).resolve(strict=True)
    staging_root = _validate_directory(collection, collection / ".staging", label="Staging root")
    stage = Path(staging_path)
    if stage.exists() or stage.is_symlink():
        raise FileExistsError("The launch staging directory already exists.")
    if stage.parent.resolve(strict=True) != staging_root:
        raise ValueError("The launch staging directory is not contained.")
    stage.mkdir(mode=0o700)
    payload_path = stage / "result.json"
    payload = (
        json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if len(payload) > MAX_PUBLICATION_BYTES:
        raise ValueError("DetectionResult exceeds the publication byte limit.")
    descriptor = os.open(payload_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    files = (
        PublicationFile("result.json", len(payload), hashlib.sha256(payload).hexdigest()),
    )
    identity = PublicationIdentity.create(
        request,
        files,
        artifact_kind="detection_result",
    )
    _write_new_json(stage / "publication.json", identity.to_dict())
    _fsync_directory(stage)
    return identity


def stage_derived_result(
    collection_root: Path,
    staging_path: Path,
    request: DetectRunRequest,
    result: DerivedResult,
) -> PublicationIdentity:
    """Stage one complete immutable child Result without touching its parent."""
    settings = dict(request.settings)
    if (
        settings != {
            "parent_result_digest": result.parent_result_digest,
            "parent_result_id": result.parent_result_id,
            "run_kind": "rf_refinement",
        }
        or result.result_id != request.artifact_id
        or result.run_id != request.run_id
        or result.request_id != request.request_id
        or result.collection_id != request.collection_id
        or result.binding_revision != request.binding_revision
        or result.inventory_id != request.inventory_id
        or result.inventory_digest != request.inventory_digest
        or result.rf_model_snapshot_id != request.model_snapshot_id
        or result.rf_model_snapshot_digest != request.model_digest
    ):
        raise ValueError("DerivedResult does not match its frozen Run request.")
    collection = Path(collection_root).resolve(strict=True)
    staging_root = _validate_directory(collection, collection / ".staging", label="Staging root")
    stage = Path(staging_path)
    if stage.exists() or stage.is_symlink():
        raise FileExistsError("The launch staging directory already exists.")
    if stage.parent.resolve(strict=True) != staging_root:
        raise ValueError("The launch staging directory is not contained.")
    stage.mkdir(mode=0o700)
    payload_path = stage / "result.json"
    payload = (
        json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if len(payload) > MAX_PUBLICATION_BYTES:
        raise ValueError("DerivedResult exceeds the publication byte limit.")
    descriptor = os.open(payload_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    files = (
        PublicationFile("result.json", len(payload), hashlib.sha256(payload).hexdigest()),
    )
    identity = PublicationIdentity.create(
        request,
        files,
        artifact_kind="derived_result",
    )
    _write_new_json(stage / "publication.json", identity.to_dict())
    _fsync_directory(stage)
    return identity


def _load_identity(directory: Path) -> PublicationIdentity:
    identity = PublicationIdentity.from_dict(_read_json(directory / "publication.json"))
    expected_names = {"publication.json", *(item.path for item in identity.files)}
    actual_names: set[str] = set()
    for child in directory.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError("Publication contains an unsafe entry.")
        actual_names.add(child.name)
    if actual_names != expected_names:
        raise ValueError("Publication file index is incomplete or contains extra files.")
    for item in identity.files:
        path = directory / item.path
        if path.stat().st_size != item.size_bytes:
            raise ValueError("Publication file size changed.")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.sha256:
            raise ValueError("Publication file checksum changed.")
    if identity.artifact_kind == "detection_result":
        if tuple(item.path for item in identity.files) != ("result.json",):
            raise ValueError("Detection Result publication file index is invalid.")
        result = DetectionResult.from_dict(
            _read_json(directory / "result.json", limit=MAX_PUBLICATION_BYTES)
        )
        if (
            result.result_id != identity.artifact_id
            or result.run_id != identity.run_id
            or result.request_id != identity.request_id
        ):
            raise ValueError("Detection Result and publication identity disagree.")
    elif identity.artifact_kind == "derived_result":
        if tuple(item.path for item in identity.files) != ("result.json",):
            raise ValueError("Derived Result publication file index is invalid.")
        result = DerivedResult.from_dict(
            _read_json(directory / "result.json", limit=MAX_PUBLICATION_BYTES)
        )
        if (
            result.result_id != identity.artifact_id
            or result.run_id != identity.run_id
            or result.request_id != identity.request_id
        ):
            raise ValueError("Derived Result and publication identity disagree.")
    return identity


def _publication_root(collection: Path, artifact_kind: str) -> Path:
    name = (
        "results"
        if artifact_kind in {"detection_result", "derived_result"}
        else "publications"
    )
    return _validate_directory(collection, collection / name, label="Publication root")


def publish_staged_artifact(
    collection_root: Path,
    staging_path: Path,
    request: DetectRunRequest,
) -> PublicationIdentity:
    collection = Path(collection_root).resolve(strict=True)
    stage = _validate_directory(collection / ".staging", Path(staging_path), label="Staging")
    identity = _load_identity(stage)
    if (
        identity.run_id != request.run_id
        or identity.request_id != request.request_id
        or identity.launch_id != request.launch_id
        or identity.artifact_id != request.artifact_id
    ):
        raise ValueError("Staged publication identity does not match its Run request.")
    roots = tuple(
        _publication_root(collection, artifact_kind)
        for artifact_kind in ("detection_result", "lifecycle_fixture")
    )
    if any(
        (root / request.artifact_id).exists()
        or (root / request.artifact_id).is_symlink()
        for root in roots
    ):
        raise FileExistsError("The immutable Detect publication already exists.")
    publications = _publication_root(collection, identity.artifact_kind)
    destination = publications / request.artifact_id
    os.rename(stage, destination)
    _fsync_directory(publications)
    return _load_identity(destination)


def load_publication_identity(
    collection_root: Path,
    artifact_id: str,
) -> PublicationIdentity:
    if _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ValueError("Publication artifact ID is invalid.")
    collection = Path(collection_root).resolve(strict=True)
    candidates: list[tuple[Path, Path]] = []
    for artifact_kind in ("detection_result", "lifecycle_fixture"):
        root = _publication_root(collection, artifact_kind)
        candidate = root / artifact_id
        if candidate.exists() or candidate.is_symlink():
            candidates.append((root, candidate))
    if len(candidates) != 1:
        raise ValueError("Publication is missing or has an ambiguous storage location.")
    publications, directory = candidates[0]
    _validate_directory(publications, directory, label="Publication")
    identity = _load_identity(directory)
    if identity.artifact_id != artifact_id:
        raise ValueError("Publication directory and identity disagree.")
    return identity


def load_detection_result(collection_root: Path, artifact_id: str) -> DetectionResult:
    """Reopen a checksum-valid Result from its app-owned immutable namespace."""
    identity = load_publication_identity(collection_root, artifact_id)
    if identity.artifact_kind != "detection_result":
        raise ValueError("The published artifact is not a Detection Result.")
    collection = Path(collection_root).resolve(strict=True)
    result = DetectionResult.from_dict(
        _read_json(
            collection / "results" / artifact_id / "result.json",
            limit=MAX_PUBLICATION_BYTES,
        )
    )
    if result.result_id != artifact_id:
        raise ValueError("Detection Result identity does not match its directory.")
    return result


def load_derived_result(collection_root: Path, artifact_id: str) -> DerivedResult:
    """Reopen a checksum-valid child and verify its original parent independently."""
    identity = load_publication_identity(collection_root, artifact_id)
    if identity.artifact_kind != "derived_result":
        raise ValueError("The published artifact is not a Derived Result.")
    collection = Path(collection_root).resolve(strict=True)
    result = DerivedResult.from_dict(
        _read_json(
            collection / "results" / artifact_id / "result.json",
            limit=MAX_PUBLICATION_BYTES,
        )
    )
    if result.result_id != artifact_id:
        raise ValueError("Derived Result identity does not match its directory.")
    parent = load_detection_result(collection, result.parent_result_id)
    result.verify_parent(parent)
    return result


def load_result_artifact(collection_root: Path, artifact_id: str) -> ResultArtifact:
    identity = load_publication_identity(collection_root, artifact_id)
    if identity.artifact_kind == "detection_result":
        return load_detection_result(collection_root, artifact_id)
    if identity.artifact_kind == "derived_result":
        return load_derived_result(collection_root, artifact_id)
    raise ValueError("The published artifact is not a scientific Result.")


def publication_matches_request(
    collection_root: Path,
    request: DetectRunRequest,
) -> PublicationIdentity | None:
    try:
        identity = load_publication_identity(collection_root, request.artifact_id)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if (
        identity.run_id != request.run_id
        or identity.request_id != request.request_id
        or identity.launch_id != request.launch_id
        or identity.artifact_id != request.artifact_id
    ):
        return None
    return identity


def discard_staging(collection_root: Path, launch_id: str) -> None:
    collection = Path(collection_root).resolve(strict=True)
    root = _validate_directory(collection, collection / ".staging", label="Staging root")
    candidate = root / launch_id
    if not candidate.exists() and not candidate.is_symlink():
        return
    if candidate.is_symlink():
        candidate.unlink()
        return
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir() or resolved.parent != root:
        raise ValueError("Staging cleanup target is unsafe.")
    shutil.rmtree(resolved)
    _fsync_directory(root)
