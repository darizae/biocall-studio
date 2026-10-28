"""Contained staging and atomic immutable publication for Detect Worker artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

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
        if self.artifact_kind != "lifecycle_fixture":
            raise ValueError("Publication artifact kind is not owned by this stage.")
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
        published_at: str | None = None,
    ) -> PublicationIdentity:
        moment = published_at or utc_now()
        unsigned = {
            "schema_version": PUBLICATION_IDENTITY_SCHEMA_VERSION,
            "run_id": request.run_id,
            "request_id": request.request_id,
            "launch_id": request.launch_id,
            "artifact_id": request.artifact_id,
            "artifact_kind": "lifecycle_fixture",
            "files": [item.to_dict() for item in files],
            "published_at": moment,
        }
        return cls(
            PUBLICATION_IDENTITY_SCHEMA_VERSION,
            request.run_id,
            request.request_id,
            request.launch_id,
            request.artifact_id,
            "lifecycle_fixture",
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
    return identity


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
    publications = _validate_directory(
        collection, collection / "publications", label="Publication root"
    )
    destination = publications / request.artifact_id
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("The immutable Detect publication already exists.")
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
    publications = _validate_directory(
        collection, collection / "publications", label="Publication root"
    )
    directory = publications / artifact_id
    _validate_directory(publications, directory, label="Publication")
    identity = _load_identity(directory)
    if identity.artifact_id != artifact_id:
        raise ValueError("Publication directory and identity disagree.")
    return identity


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
