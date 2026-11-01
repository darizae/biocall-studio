"""Private, versioned index records for completed external exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from biocall_studio.detect.domain import validate_collection_id
from biocall_studio.detect.domain.exports import ExportMode, ExportReceipt

EXPORT_HISTORY_SCHEMA_VERSION = 1
MAX_EXPORT_HISTORY_RECORDS = 10_000
MAX_EXPORT_HISTORY_BYTES = 1_048_576

_EXPORT_ID = re.compile(r"exp_[0-9a-f]{32}")
_RESULT_ID = re.compile(r"pub_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ExportAvailability(StrEnum):
    UNSELECTED = "unselected"
    VERIFYING = "verifying"
    AVAILABLE = "available"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"
    CHANGED = "changed"


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid.")
    return value


def _utc(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Export history completion time must be UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Export history completion time is invalid.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Export history completion time must include UTC.")
    return value


def destination_path_from_uri(value: str) -> Path:
    if not isinstance(value, str):
        raise ValueError("Export history destination URI is invalid.")
    parsed = urlparse(value)
    if (
        parsed.scheme != "file"
        or parsed.netloc not in {"", "localhost"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Export history destination URI is invalid.")
    path = Path(url2pathname(unquote(parsed.path)))
    if not path.is_absolute():
        raise ValueError("Export history destination URI must be absolute.")
    return path


@dataclass(frozen=True, slots=True)
class ExportHistoryRecord:
    schema_version: int
    collection_id: str
    export_id: str
    receipt_digest: str
    snapshot_digest: str
    result_id: str
    result_digest: str
    mode: ExportMode
    completed_at: str
    selected_call_count: int
    published_file_count: int
    destination_uri: str

    def __post_init__(self) -> None:
        if self.schema_version != EXPORT_HISTORY_SCHEMA_VERSION:
            raise ValueError("Unsupported export-history schema.")
        validate_collection_id(self.collection_id)
        if not isinstance(self.export_id, str) or _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("Export history ID is invalid.")
        _digest(self.receipt_digest, "Export history receipt digest")
        _digest(self.snapshot_digest, "Export history snapshot digest")
        if not isinstance(self.result_id, str) or _RESULT_ID.fullmatch(self.result_id) is None:
            raise ValueError("Export history Result ID is invalid.")
        _digest(self.result_digest, "Export history Result digest")
        if not isinstance(self.mode, ExportMode):
            raise ValueError("Export history mode is invalid.")
        _utc(self.completed_at)
        for value, label in (
            (self.selected_call_count, "selected-call count"),
            (self.published_file_count, "published-file count"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"Export history {label} is invalid.")
        destination_path_from_uri(self.destination_uri)

    @property
    def destination_path(self) -> Path:
        return destination_path_from_uri(self.destination_uri)

    @classmethod
    def from_receipt(
        cls,
        collection_id: str,
        receipt: ExportReceipt,
        *,
        selected_call_count: int,
    ) -> ExportHistoryRecord:
        return cls(
            EXPORT_HISTORY_SCHEMA_VERSION,
            collection_id,
            receipt.export_id,
            receipt.receipt_digest,
            receipt.snapshot_digest,
            receipt.result_id,
            receipt.result_digest,
            receipt.mode,
            receipt.completed_at,
            selected_call_count,
            len(receipt.files),
            Path(receipt.final_destination).as_uri(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "collection_id": self.collection_id,
            "export_id": self.export_id,
            "receipt_digest": self.receipt_digest,
            "snapshot_digest": self.snapshot_digest,
            "result_id": self.result_id,
            "result_digest": self.result_digest,
            "mode": self.mode.value,
            "completed_at": self.completed_at,
            "selected_call_count": self.selected_call_count,
            "published_file_count": self.published_file_count,
            "destination_uri": self.destination_uri,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ExportHistoryRecord:
        expected = {
            "schema_version",
            "collection_id",
            "export_id",
            "receipt_digest",
            "snapshot_digest",
            "result_id",
            "result_digest",
            "mode",
            "completed_at",
            "selected_call_count",
            "published_file_count",
            "destination_uri",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Export history document is invalid.")
        values = dict(raw)
        try:
            values["mode"] = ExportMode(values["mode"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Export history mode is invalid.") from exc
        return cls(**values)


__all__ = [
    "EXPORT_HISTORY_SCHEMA_VERSION",
    "MAX_EXPORT_HISTORY_BYTES",
    "MAX_EXPORT_HISTORY_RECORDS",
    "ExportAvailability",
    "ExportHistoryRecord",
    "destination_path_from_uri",
]
