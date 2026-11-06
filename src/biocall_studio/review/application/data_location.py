"""Versioned, fail-closed relocation of Review-owned application data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from biocall_studio.review.persistence.export_history import ReviewExportHistoryStore
from biocall_studio.review.persistence.sessions import ReviewSessionStore
from biocall_studio.shared.storage import (
    ByteEstimate,
    EstimateConfidence,
    StorageEstimate,
    assess_storage,
    query_filesystem_capacity,
    require_storage_admission,
    storage_input_digest,
)

_PREFERENCE_SCHEMA_VERSION = 1
_MAX_PREFERENCE_BYTES = 16 * 1024
_MAX_FILES = 1_000_000
_MAX_TOTAL_BYTES = 2**63 - 1
_COPY_CHUNK_BYTES = 1024 * 1024


class ReviewDataLocationError(RuntimeError):
    """Review data cannot be selected or moved without risking authoritative state."""


@dataclass(frozen=True, slots=True)
class ReviewDataFile:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ReviewDataMovePlan:
    source_root: Path
    target_root: Path
    files: tuple[ReviewDataFile, ...]
    total_bytes: int
    input_digest: str
    storage_estimate: StorageEstimate


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _reject_symlink_chain(path: Path) -> None:
    candidate = path
    while True:
        if candidate.is_symlink():
            raise ReviewDataLocationError("Review data folders cannot use symbolic links.")
        parent = candidate.parent
        if parent == candidate:
            return
        candidate = parent


def _resolved_absolute(path: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ReviewDataLocationError(f"{label} must be an absolute folder without traversal.")
    _reject_symlink_chain(candidate)
    return candidate.resolve(strict=False)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directories(root: Path) -> None:
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in reversed(directories):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _inventory(root: Path) -> tuple[ReviewDataFile, ...]:
    if root.is_symlink() or not root.is_dir():
        raise ReviewDataLocationError("The current Review data folder is unavailable or unsafe.")
    files: list[ReviewDataFile] = []
    total = 0
    for directory, names, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        if directory_path == root and "leases" in names:
            names.remove("leases")
        names.sort()
        filenames.sort()
        for name in names:
            child = directory_path / name
            if child.is_symlink():
                raise ReviewDataLocationError("Review data cannot contain symbolic links.")
        for name in filenames:
            path = directory_path / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise ReviewDataLocationError("Review data contains an unsupported file type.")
            if len(files) >= _MAX_FILES:
                raise ReviewDataLocationError("Review data contains too many files to move safely.")
            total += metadata.st_size
            if total > _MAX_TOTAL_BYTES:
                raise ReviewDataLocationError("Review data is too large to move safely.")
            files.append(
                ReviewDataFile(
                    path.relative_to(root).as_posix(),
                    metadata.st_size,
                    _file_digest(path),
                )
            )
    return tuple(files)


class ReviewDataLocationManager:
    """Keep the location preference outside the data it selects and move atomically."""

    def __init__(self, suite_data_root: Path):
        self.suite_data_root = _resolved_absolute(
            Path(suite_data_root), label="Suite application-data root"
        )
        self.default_root = self.suite_data_root / "review" / "v1"
        self.preference_path = (
            self.suite_data_root / "settings" / "review-data-location-v1.json"
        )

    def current_root(self) -> Path:
        path = self.preference_path
        if not path.exists() and not path.is_symlink():
            return self.default_root
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_PREFERENCE_BYTES:
            raise ReviewDataLocationError("Review data-folder settings are unsafe or corrupt.")
        try:
            raw = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewDataLocationError("Review data-folder settings are corrupt.") from exc
        if (
            not isinstance(raw, dict)
            or set(raw) != {"schema_version", "review_data_root"}
            or raw.get("schema_version") != _PREFERENCE_SCHEMA_VERSION
            or not isinstance(raw.get("review_data_root"), str)
        ):
            raise ReviewDataLocationError("Review data-folder settings are unsupported.")
        return self._validate_target(Path(raw["review_data_root"]), forbidden_roots=())

    def _validate_target(
        self, target: Path, *, forbidden_roots: tuple[Path, ...]
    ) -> Path:
        resolved = _resolved_absolute(target, label="Review data folder")
        protected = (
            self.suite_data_root / "train",
            self.suite_data_root / "detect",
            self.suite_data_root / "settings",
        )
        if any(_overlaps(resolved, root.resolve(strict=False)) for root in protected):
            raise ReviewDataLocationError(
                "Review data cannot overlap BioCall Studio Train or Detect data."
            )
        for root in forbidden_roots:
            forbidden = _resolved_absolute(Path(root), label="Protected data folder")
            if _overlaps(resolved, forbidden):
                raise ReviewDataLocationError(
                    "Review data cannot overlap recordings or an export destination."
                )
        return resolved

    def plan_move(
        self, target: Path, *, forbidden_roots: tuple[Path, ...] = ()
    ) -> ReviewDataMovePlan:
        source = self.current_root()
        target_root = self._validate_target(Path(target), forbidden_roots=forbidden_roots)
        if target_root == source:
            raise ReviewDataLocationError("This is already the Review data folder.")
        if _overlaps(target_root, source):
            raise ReviewDataLocationError(
                "The new Review data folder cannot contain the current folder or be inside it."
            )
        if target_root.exists():
            if not target_root.is_dir():
                raise ReviewDataLocationError("The selected Review data path is not a folder.")
            if any(target_root.iterdir()):
                raise ReviewDataLocationError(
                    "The selected folder already contains data. Choose an empty folder."
                )
        files = _inventory(source)
        total = sum(item.size_bytes for item in files)
        facts = {
            "schema_version": _PREFERENCE_SCHEMA_VERSION,
            "source_root": str(source),
            "target_root": str(target_root),
            "files": [
                {
                    "relative_path": item.relative_path,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in files
            ],
        }
        digest = storage_input_digest(facts)
        capacity = query_filesystem_capacity(target_root, "Review data folder")
        estimate = assess_storage(
            operation="Move Review data",
            input_digest=digest,
            expected_final=ByteEstimate.exact(total),
            target_peaks={"Review data folder": total},
            capacities={"Review data folder": capacity},
            confidence=EstimateConfidence.ARITHMETIC,
            basis="Exact current Review-owned file sizes and checksums.",
        )
        return ReviewDataMovePlan(source, target_root, files, total, digest, estimate)

    def _write_preference(self, root: Path) -> None:
        parent = self.preference_path.parent
        _reject_symlink_chain(parent)
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if parent.is_symlink() or self.preference_path.is_symlink():
            raise OSError("Review data-folder preference path is unsafe.")
        previous = self.preference_path.read_bytes() if self.preference_path.exists() else None
        payload = json.dumps(
            {
                "schema_version": _PREFERENCE_SCHEMA_VERSION,
                "review_data_root": str(root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = parent / f".{self.preference_path.name}.{uuid.uuid4().hex}.tmp"
        replaced = False
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.preference_path)
            replaced = True
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except Exception:
            if replaced:
                if previous is None:
                    self.preference_path.unlink(missing_ok=True)
                else:
                    rollback = parent / f".{self.preference_path.name}.{uuid.uuid4().hex}.rollback"
                    try:
                        with rollback.open("xb") as stream:
                            stream.write(previous)
                            stream.flush()
                            os.fsync(stream.fileno())
                        rollback.chmod(0o600)
                        os.replace(rollback, self.preference_path)
                    finally:
                        if rollback.exists() and not rollback.is_symlink():
                            rollback.unlink()
            raise
        finally:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()

    @staticmethod
    def _validate_copy(root: Path, expected: tuple[ReviewDataFile, ...]) -> None:
        actual = _inventory(root)
        if actual != expected:
            raise ReviewDataLocationError("The copied Review data failed checksum validation.")
        database = root / "sessions.sqlite3"
        if database.is_file():
            store = ReviewSessionStore(root)
            sessions = store.list_sessions()
            for session in sessions:
                if session.final_snapshot_digest is not None and not store.verify_finalization(
                    session.session_id
                ):
                    raise ReviewDataLocationError(
                        "The copied Review finalization snapshot is inconsistent."
                    )
        history_root = root / "export-history"
        if history_root.exists():
            history = ReviewExportHistoryStore(root).load()
            if history.ignored_corrupt_count:
                raise ReviewDataLocationError("The copied Review export history is corrupt.")

    def move(
        self,
        plan: ReviewDataMovePlan,
        *,
        confirm_storage: bool = False,
        cancel_requested: threading.Event | None = None,
    ) -> None:
        if not isinstance(plan, ReviewDataMovePlan):
            raise TypeError("Review data move plan is invalid.")
        cancel_requested = cancel_requested or threading.Event()
        try:
            current = self.plan_move(plan.target_root)
        except ReviewDataLocationError:
            raise
        if current.input_digest != plan.input_digest or current.files != plan.files:
            raise ReviewDataLocationError("Review data changed. Check the folder again.")
        try:
            require_storage_admission(plan.storage_estimate, confirmed=confirm_storage)
        except ValueError as exc:
            raise ReviewDataLocationError(str(exc)) from exc
        if cancel_requested.is_set():
            raise ReviewDataLocationError("Review data move was cancelled.")

        target = plan.target_root
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        _reject_symlink_chain(target.parent)
        staging = target.parent / f".{target.name}.biocall-stage-{uuid.uuid4().hex}"
        promoted = False
        try:
            staging.mkdir(mode=0o700)
            for item in plan.files:
                if cancel_requested.is_set():
                    raise ReviewDataLocationError("Review data move was cancelled.")
                source_file = plan.source_root / item.relative_path
                destination_file = staging / item.relative_path
                destination_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                with source_file.open("rb") as source_stream, destination_file.open(
                    "xb"
                ) as destination_stream:
                    while chunk := source_stream.read(_COPY_CHUNK_BYTES):
                        if cancel_requested.is_set():
                            raise ReviewDataLocationError("Review data move was cancelled.")
                        destination_stream.write(chunk)
                    destination_stream.flush()
                    os.fsync(destination_stream.fileno())
                destination_file.chmod(stat.S_IMODE(source_file.stat().st_mode) & 0o700 or 0o600)
            self._validate_copy(staging, plan.files)
            _fsync_directories(staging)
            if target.exists():
                target.rmdir()
            os.replace(staging, target)
            promoted = True
            descriptor = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._write_preference(target)
        except ReviewDataLocationError:
            raise
        except (OSError, ValueError) as exc:
            raise ReviewDataLocationError(
                "Couldn't move Review data. Your original folder is unchanged."
            ) from exc
        finally:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging, ignore_errors=True)
            if (
                promoted
                and self.current_root() != target
                and target.exists()
                and not target.is_symlink()
            ):
                shutil.rmtree(target, ignore_errors=True)

        try:
            shutil.rmtree(plan.source_root)
        except OSError:
            # The selected target is already authoritative. A harmless old copy is safer than
            # rolling the preference back after a verified promotion.
            pass


__all__ = [
    "ReviewDataFile",
    "ReviewDataLocationError",
    "ReviewDataLocationManager",
    "ReviewDataMovePlan",
]
