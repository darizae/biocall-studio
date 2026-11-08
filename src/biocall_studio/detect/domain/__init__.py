"""Pure Detect Collection identity, root-state, and portable-reference rules."""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath

DETECT_COLLECTION_SCHEMA_VERSION = 1
DETECT_BINDING_SCHEMA_VERSION = 1
_COLLECTION_ID = re.compile(r"det_[0-9a-f]{32}")
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_UNSAFE_PORTABLE_CHARS = set('<>:"\\|?*')


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Detect Collection timestamps must include a timezone.")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_utc_text(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Detect Collection timestamps must be UTC strings.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Detect Collection timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Detect Collection timestamp is invalid.")
    return value


def validate_collection_id(value: object) -> str:
    if not isinstance(value, str) or _COLLECTION_ID.fullmatch(value) is None:
        raise ValueError("Invalid Detect Collection identifier.")
    return value


def validate_display_label(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Detect Collection label must be text.")
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized or len(normalized) > 120 or any(ord(char) < 32 for char in normalized):
        raise ValueError("Detect Collection label must contain 1 to 120 printable characters.")
    return normalized


@dataclass(frozen=True, slots=True)
class RootEvidence:
    """Root-level filesystem identity, deliberately separate from recording inventory facts."""

    filesystem_id: int
    file_id: int
    evidence_schema: int = 1

    def __post_init__(self) -> None:
        if (
            self.evidence_schema != 1
            or type(self.filesystem_id) is not int
            or type(self.file_id) is not int
            or self.filesystem_id < 0
            or self.file_id <= 0
        ):
            raise ValueError("Root identity evidence is invalid or unavailable.")

    def to_dict(self) -> dict[str, int]:
        return {
            "schema_version": self.evidence_schema,
            "filesystem_id": self.filesystem_id,
            "file_id": self.file_id,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RootEvidence:
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "filesystem_id",
            "file_id",
        }:
            raise ValueError("Root identity evidence is invalid.")
        return cls(
            evidence_schema=raw["schema_version"],
            filesystem_id=raw["filesystem_id"],
            file_id=raw["file_id"],
        )


@dataclass(frozen=True, slots=True)
class DetectCollectionRef:
    """Portable Collection metadata; it never contains a source location."""

    schema_version: int
    collection_id: str
    display_label: str
    created_at: str
    updated_at: str
    binding_revision: int
    root_evidence: RootEvidence
    inventory_revision: str | None
    inventory_binding_revision: int | None

    def __post_init__(self) -> None:
        if self.schema_version != DETECT_COLLECTION_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Detect Collection schema: {self.schema_version!r}.")
        validate_collection_id(self.collection_id)
        normalized = validate_display_label(self.display_label)
        if normalized != self.display_label:
            raise ValueError("Detect Collection label must be normalized.")
        _validate_utc_text(self.created_at)
        _validate_utc_text(self.updated_at)
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Detect Collection binding revision is invalid.")
        if (self.inventory_revision is None) != (self.inventory_binding_revision is None):
            raise ValueError("Detect inventory reference is incomplete.")
        if self.inventory_revision is not None:
            if _INVENTORY_ID.fullmatch(self.inventory_revision) is None:
                raise ValueError("Detect inventory revision is invalid.")
            if (
                type(self.inventory_binding_revision) is not int
                or not 1 <= self.inventory_binding_revision <= self.binding_revision
            ):
                raise ValueError("Detect inventory binding revision is invalid.")

    @classmethod
    def create(
        cls,
        display_label: str,
        root_evidence: RootEvidence,
        *,
        now: datetime | None = None,
    ) -> DetectCollectionRef:
        timestamp = _utc_text(now or datetime.now(UTC))
        return cls(
            schema_version=DETECT_COLLECTION_SCHEMA_VERSION,
            collection_id=f"det_{uuid.uuid4().hex}",
            display_label=validate_display_label(display_label),
            created_at=timestamp,
            updated_at=timestamp,
            binding_revision=1,
            root_evidence=root_evidence,
            inventory_revision=None,
            inventory_binding_revision=None,
        )

    @property
    def inventory_is_stale(self) -> bool:
        return (
            self.inventory_revision is not None
            and self.inventory_binding_revision != self.binding_revision
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "collection_id": self.collection_id,
            "display_label": self.display_label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "binding_revision": self.binding_revision,
            "root_evidence": self.root_evidence.to_dict(),
            "inventory_revision": self.inventory_revision,
            "inventory_binding_revision": self.inventory_binding_revision,
        }

    @classmethod
    def from_public_dict(cls, raw: object) -> DetectCollectionRef:
        expected = {
            "schema_version",
            "collection_id",
            "display_label",
            "created_at",
            "updated_at",
            "binding_revision",
            "root_evidence",
            "inventory_revision",
            "inventory_binding_revision",
        }
        if not isinstance(raw, dict):
            raise ValueError("Detect Collection metadata must be an object.")
        if raw.get("schema_version") != DETECT_COLLECTION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Detect Collection schema: {raw.get('schema_version')!r}."
            )
        if set(raw) != expected:
            raise ValueError("Detect Collection metadata contains unsupported fields.")
        return cls(
            schema_version=raw["schema_version"],
            collection_id=raw["collection_id"],
            display_label=raw["display_label"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            binding_revision=raw["binding_revision"],
            root_evidence=RootEvidence.from_dict(raw["root_evidence"]),
            inventory_revision=raw["inventory_revision"],
            inventory_binding_revision=raw["inventory_binding_revision"],
        )


@dataclass(frozen=True, slots=True)
class DetectRootBinding:
    """Private, machine-local source-root location."""

    collection_id: str
    binding_revision: int
    source_root_uri: str
    schema_version: int = DETECT_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_collection_id(self.collection_id)
        if self.schema_version != DETECT_BINDING_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Detect root binding schema: {self.schema_version!r}.")
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Detect root binding revision is invalid.")
        if not isinstance(self.source_root_uri, str) or not self.source_root_uri.startswith(
            "file:"
        ):
            raise ValueError("Detect root binding must contain a local file URI.")

    def to_private_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "collection_id": self.collection_id,
            "binding_revision": self.binding_revision,
            "source_root_uri": self.source_root_uri,
        }

    @classmethod
    def from_private_dict(cls, raw: object) -> DetectRootBinding:
        expected = {
            "schema_version",
            "collection_id",
            "binding_revision",
            "source_root_uri",
        }
        if not isinstance(raw, dict):
            raise ValueError("Detect root binding must be an object.")
        if raw.get("schema_version") != DETECT_BINDING_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Detect root binding schema: {raw.get('schema_version')!r}."
            )
        if set(raw) != expected:
            raise ValueError("Detect root binding contains unsupported fields.")
        return cls(
            schema_version=raw["schema_version"],
            collection_id=raw["collection_id"],
            binding_revision=raw["binding_revision"],
            source_root_uri=raw["source_root_uri"],
        )


class RootObservationKind(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"


@dataclass(frozen=True, slots=True)
class RootObservation:
    kind: RootObservationKind
    evidence: RootEvidence | None = None

    def __post_init__(self) -> None:
        if (self.kind is RootObservationKind.AVAILABLE) != (self.evidence is not None):
            raise ValueError("Root observation evidence does not match its state.")

    @classmethod
    def available(cls, evidence: RootEvidence) -> RootObservation:
        return cls(RootObservationKind.AVAILABLE, evidence)

    @classmethod
    def missing(cls) -> RootObservation:
        return cls(RootObservationKind.MISSING)

    @classmethod
    def inaccessible(cls) -> RootObservation:
        return cls(RootObservationKind.INACCESSIBLE)


class RootBindingDecision(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"
    CHANGED = "changed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


def decide_root_binding(
    expected: RootEvidence, observation: RootObservation
) -> RootBindingDecision:
    if observation.kind is RootObservationKind.MISSING:
        return RootBindingDecision.MISSING
    if observation.kind is RootObservationKind.INACCESSIBLE:
        return RootBindingDecision.INACCESSIBLE
    return (
        RootBindingDecision.VALID
        if observation.evidence == expected
        else RootBindingDecision.CHANGED
    )


def apply_confirmed_relink(
    current: DetectCollectionRef,
    candidate_evidence: RootEvidence,
    *,
    now: datetime | None = None,
) -> DetectCollectionRef:
    """Advance only a verified same-root binding; inventory provenance stays on its old revision."""
    if candidate_evidence != current.root_evidence:
        raise ValueError("The selected folder is a different source root; create a new Collection.")
    return replace(
        current,
        updated_at=_utc_text(now or datetime.now(UTC)),
        binding_revision=current.binding_revision + 1,
        root_evidence=candidate_evidence,
    )


def detect_workspace_path(application_data_root: Path) -> Path:
    return application_data_root / "detect" / "v1"


def validate_relative_reference(value: str) -> str:
    """Validate a future Detect-owned relative reference without touching a filesystem."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Detect references must use non-empty portable relative paths.")
    if value.startswith("/") or _WINDOWS_DRIVE.match(value) or value.startswith("//"):
        raise ValueError("Detect references cannot be absolute paths.")
    normalized = unicodedata.normalize("NFC", value)
    path = PurePosixPath(normalized)
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts) or path.is_absolute():
        raise ValueError("Detect references cannot contain traversal or empty segments.")
    for part in parts:
        if (
            part.rstrip(" .") != part
            or any(char in _UNSAFE_PORTABLE_CHARS or ord(char) < 32 for char in part)
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        ):
            raise ValueError("Detect reference contains a non-portable path segment.")
    return normalized


def ensure_unique_relative_references(values: list[str]) -> tuple[str, ...]:
    normalized = tuple(validate_relative_reference(value) for value in values)
    identities: set[str] = set()
    for value in normalized:
        identity = value.casefold()
        if identity in identities:
            raise ValueError("Detect references contain a Unicode or casefold collision.")
        identities.add(identity)
    return normalized
