"""Contained atomic persistence for private completed-export history."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from heapq import heappush, heapreplace
from pathlib import Path

from biocall_studio.detect.domain import validate_collection_id
from biocall_studio.detect.domain.export_history import (
    MAX_EXPORT_HISTORY_BYTES,
    MAX_EXPORT_HISTORY_RECORDS,
    ExportHistoryRecord,
)

_RECORD_NAME = re.compile(r"exp_[0-9a-f]{32}\.json")


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
class ExportHistoryLoad:
    records: tuple[ExportHistoryRecord, ...]
    rejected: tuple[Path, ...]


class ExportHistoryStore:
    """One strict record per export below a Collection's existing exports namespace."""

    def __init__(self, collection_root: Path, collection_id: str):
        root = Path(collection_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Detect Collection export-history root is unsafe.")
        self.collection_root = root.resolve(strict=True)
        self.collection_id = validate_collection_id(collection_id)
        self.exports_root = self.collection_root / "exports"
        if self.exports_root.is_symlink() or not self.exports_root.is_dir():
            raise ValueError("Detect export-history storage is missing or unsafe.")
        resolved = self.exports_root.resolve(strict=True)
        if not resolved.is_relative_to(self.collection_root):
            raise ValueError("Detect export-history storage escapes its Collection.")
        self.exports_root = resolved

    def path_for(self, export_id: str) -> Path:
        name = f"{export_id}.json"
        if _RECORD_NAME.fullmatch(name) is None:
            raise ValueError("Export history ID is invalid.")
        return self.exports_root / name

    def _read(self, path: Path) -> ExportHistoryRecord:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Export history record is missing or unsafe.")
        if path.parent.resolve(strict=True) != self.exports_root:
            raise ValueError("Export history record escapes its Collection.")
        descriptor = -1
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            facts = os.fstat(descriptor)
            if not stat.S_ISREG(facts.st_mode):
                raise ValueError("Export history record is missing or unsafe.")
            if facts.st_size > MAX_EXPORT_HISTORY_BYTES:
                raise ValueError("Export history record exceeds 1 MiB.")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                payload = stream.read(MAX_EXPORT_HISTORY_BYTES + 1)
            if len(payload) > MAX_EXPORT_HISTORY_BYTES:
                raise ValueError("Export history record exceeds 1 MiB.")
            raw = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Export history record is corrupt.") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        record = ExportHistoryRecord.from_dict(raw)
        if path.name != f"{record.export_id}.json":
            raise ValueError("Export history filename and identity disagree.")
        if record.collection_id != self.collection_id:
            raise ValueError("Export history record belongs to a different Collection.")
        return record

    def load(self) -> ExportHistoryLoad:
        candidates: list[tuple[int, str, Path]] = []
        rejected: list[Path] = []
        with os.scandir(self.exports_root) as entries:
            for entry in entries:
                if _RECORD_NAME.fullmatch(entry.name) is None:
                    continue
                path = self.exports_root / entry.name
                try:
                    modified = entry.stat(follow_symlinks=False).st_mtime_ns
                except OSError:
                    rejected.append(path)
                    continue
                candidate = (modified, entry.name, path)
                if len(candidates) < MAX_EXPORT_HISTORY_RECORDS:
                    heappush(candidates, candidate)
                elif candidate > candidates[0]:
                    heapreplace(candidates, candidate)
        candidates.sort(reverse=True)
        records: list[ExportHistoryRecord] = []
        for _modified, _name, path in candidates:
            try:
                records.append(self._read(path))
            except (OSError, ValueError):
                rejected.append(path)
        records.sort(key=lambda item: (item.completed_at, item.export_id), reverse=True)
        rejected.sort(key=lambda item: item.name)
        return ExportHistoryLoad(tuple(records), tuple(rejected))

    def save(self, record: ExportHistoryRecord) -> None:
        if record.collection_id != self.collection_id:
            raise ValueError("Export history record belongs to a different Collection.")
        path = self.path_for(record.export_id)
        if path.exists() or path.is_symlink():
            try:
                existing = self._read(path)
            except (OSError, ValueError) as exc:
                raise ValueError("Existing export history identity is unsafe or corrupt.") from exc
            if existing == record:
                return
            raise ValueError("Export ID already identifies a different completed export.")
        encoded = (
            json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if len(encoded) > MAX_EXPORT_HISTORY_BYTES:
            raise ValueError("Export history record exceeds 1 MiB.")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.exports_root,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path, follow_symlinks=False)
            temporary.unlink()
            temporary = None
            path.chmod(0o600)
            _fsync_directory(self.exports_root)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


__all__ = ["ExportHistoryLoad", "ExportHistoryStore"]
