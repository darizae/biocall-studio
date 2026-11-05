"""Contained, atomic Review-owned completed-export history."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from biocall_studio.review.domain.exports import (
    MAX_COMPACT_DOCUMENT_BYTES,
    ReviewExportHistoryRecord,
    canonical_json_bytes,
)

_EXPORT_ID = re.compile(r"rexp_[0-9a-f]{32}")


@dataclass(frozen=True, slots=True)
class ReviewExportHistoryLoad:
    records: tuple[ReviewExportHistoryRecord, ...]
    ignored_corrupt_count: int


class ReviewExportHistoryStore:
    """One app-owned file per export; publications themselves remain immutable."""

    def __init__(self, review_root: Path):
        requested = Path(review_root).expanduser()
        if requested.is_symlink():
            raise ValueError("Review application-data root cannot be a symlink.")
        self.root = requested.resolve(strict=False) / "export-history"

    def _ensure_root(self) -> None:
        if self.root.parent.is_symlink() or self.root.is_symlink():
            raise ValueError("Review export history path cannot be a symlink.")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.root.chmod(0o700)

    def path_for(self, export_id: str) -> Path:
        if not isinstance(export_id, str) or _EXPORT_ID.fullmatch(export_id) is None:
            raise ValueError("Review export history ID is invalid.")
        return self.root / f"{export_id}.json"

    def _read(self, path: Path) -> ReviewExportHistoryRecord:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_COMPACT_DOCUMENT_BYTES
        ):
            raise ValueError("Review export history entry is missing, unsafe, or too large.")
        try:
            raw = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Review export history entry is corrupt.") from exc
        record = ReviewExportHistoryRecord.from_dict(raw)
        if path != self.path_for(record.export_id):
            raise ValueError("Review export history identity is inconsistent.")
        return record

    def load(self) -> ReviewExportHistoryLoad:
        self._ensure_root()
        records: list[ReviewExportHistoryRecord] = []
        ignored = 0
        for path in self.root.iterdir():
            if path.is_symlink():
                ignored += 1
                continue
            if not path.is_file() or not path.name.endswith(".json"):
                continue
            try:
                records.append(self._read(path))
            except ValueError:
                ignored += 1
        records.sort(key=lambda item: (item.completed_at, item.export_id), reverse=True)
        return ReviewExportHistoryLoad(tuple(records), ignored)

    def save(self, record: ReviewExportHistoryRecord) -> None:
        if not isinstance(record, ReviewExportHistoryRecord):
            raise TypeError("Review export history record is invalid.")
        self._ensure_root()
        target = self.path_for(record.export_id)
        payload = canonical_json_bytes(record.to_dict())
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                raise ValueError("Review export history target is unsafe.")
            existing = self._read(target)
            if existing == record:
                return
            raise ValueError("Review export history identity already belongs to another output.")
        temporary = self.root / f".{record.export_id}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.link(temporary, target)
            target.chmod(0o600)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except FileExistsError as exc:
            if target.exists() and not target.is_symlink() and self._read(target) == record:
                return
            raise ValueError("Review export history identity already exists.") from exc
        finally:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()


__all__ = [
    "ReviewExportHistoryLoad",
    "ReviewExportHistoryStore",
]
