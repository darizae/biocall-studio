"""Immutable, portable Detect recording inventory contracts and pure decisions."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from biocall_studio.detect.domain import validate_collection_id, validate_relative_reference

INVENTORY_SCHEMA_VERSION = 1
FRESHNESS_STRATEGY = (
    "Each scan records size_bytes, mtime_ns, a full-file SHA-256, and a bounded WAV header. "
    "UI freshness checks use size and mtime; every downstream read must reopen without following "
    "links, revalidate root containment, size, mtime, and SHA-256 before processing."
)
CONFLICT_POLICY = (
    "Rows are ordered by NFC relative path and never collapsed. Casefold/NFC collisions and "
    "multiple paths to one filesystem file are invalid and excluded. Symlinks and reparse points "
    "are not followed. A rescan keeps removed prior rows as missing and identifies replacement by "
    "SHA-256 even when size and mtime are unchanged."
)
_INVENTORY_ID = re.compile(r"inv_[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_POLICY_SEGMENTS = frozenset(
    {".alpaca", "positives", "datasets", "snippets", "exports", "results", "runs", "models"}
)
MAX_INVENTORY_ISSUES = 1_000
MAX_DECISION_RULES = 1_000


class InclusionDecision(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNDECIDED = "undecided"


class RecordingStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    STALE = "stale"


class DecisionOrigin(StrEnum):
    DEFAULT = "default"
    POLICY = "policy"
    EXPLICIT_FOLDER = "explicit_folder"
    EXPLICIT_FILE = "explicit_file"
    CONFLICT = "conflict"


class ChangeKind(StrEnum):
    ADDED = "added"
    UNCHANGED = "unchanged"
    REPLACED = "replaced"
    REMOVED = "removed"


class StaleInventoryRevisionError(ValueError):
    """Raised when a decision was prepared from a superseded inventory."""


class BulkInclusionConfirmationRequired(ValueError):
    """Raised before replacing one or more explicit exclusions."""

    def __init__(self, exclusion_count: int):
        self.exclusion_count = exclusion_count
        super().__init__(
            f"Confirm replacement of {exclusion_count} explicitly excluded recording"
            f"{'s' if exclusion_count != 1 else ''}."
        )


def portable_identity(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


@dataclass(frozen=True, slots=True)
class DecisionRule:
    path: str
    is_folder: bool
    decision: InclusionDecision

    def __post_init__(self) -> None:
        normalized = validate_relative_reference(self.path.rstrip("/"))
        if normalized != self.path.rstrip("/"):
            raise ValueError("Decision paths must already be NFC-normalized relative paths.")
        if not isinstance(self.is_folder, bool):
            raise ValueError("Decision rule kind is invalid.")
        if self.is_folder and normalized.casefold().endswith(".wav"):
            raise ValueError("A folder decision cannot target a WAV file.")
        if not self.is_folder and not normalized.casefold().endswith(".wav"):
            raise ValueError("A file decision must target a WAV file.")
        object.__setattr__(self, "path", normalized)
        if not isinstance(self.decision, InclusionDecision):
            raise ValueError("Decision rule value is invalid.")
        if self.decision is InclusionDecision.UNDECIDED:
            raise ValueError("Remove a rule to restore an undecided default.")

    @classmethod
    def folder(cls, path: str, decision: InclusionDecision) -> DecisionRule:
        return cls(path.rstrip("/"), True, decision)

    @classmethod
    def file(cls, path: str, decision: InclusionDecision) -> DecisionRule:
        return cls(path, False, decision)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": "folder" if self.is_folder else "file",
            "decision": self.decision.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> DecisionRule:
        if not isinstance(raw, dict) or set(raw) != {"path", "kind", "decision"}:
            raise ValueError("Inventory decision rule is invalid.")
        if raw["kind"] not in {"folder", "file"}:
            raise ValueError("Inventory decision rule kind is invalid.")
        return cls(
            path=raw["path"],
            is_folder=raw["kind"] == "folder",
            decision=InclusionDecision(raw["decision"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionResolution:
    decision: InclusionDecision
    origin: DecisionOrigin
    source_path: str
    reason: str


def _policy_excluded(path: str) -> str | None:
    parts = path.split("/")[:-1]
    for part in parts:
        if portable_identity(part) in _POLICY_SEGMENTS:
            return part
    return None


def resolve_decision(path: str, rules: Iterable[DecisionRule]) -> DecisionResolution:
    key = validate_relative_reference(path)
    identity = portable_identity(key)
    file_matches = [
        rule for rule in rules if not rule.is_folder and portable_identity(rule.path) == identity
    ]
    if file_matches:
        rule = sorted(file_matches, key=lambda item: item.path)[0]
        return DecisionResolution(
            rule.decision,
            DecisionOrigin.EXPLICIT_FILE,
            rule.path,
            "Explicit file decision",
        )

    policy = _policy_excluded(key)
    if policy is not None:
        return DecisionResolution(
            InclusionDecision.EXCLUDED,
            DecisionOrigin.POLICY,
            f"{policy}/",
            "Recognized generated or labeled-data folder",
        )

    folder_matches = []
    for rule in rules:
        if not rule.is_folder:
            continue
        folder_identity = portable_identity(rule.path)
        if identity.startswith(folder_identity + "/"):
            folder_matches.append(rule)
    if folder_matches:
        rule = max(folder_matches, key=lambda item: (len(item.path.split("/")), item.path))
        return DecisionResolution(
            rule.decision,
            DecisionOrigin.EXPLICIT_FOLDER,
            f"{rule.path}/",
            "Inherited explicit folder decision",
        )

    if identity.startswith("recordings/"):
        return DecisionResolution(
            InclusionDecision.INCLUDED,
            DecisionOrigin.DEFAULT,
            "recordings/",
            "Recognized recordings/ folder",
        )
    return DecisionResolution(
        InclusionDecision.UNDECIDED,
        DecisionOrigin.DEFAULT,
        "",
        "WAV is outside a recognized recordings/ folder",
    )


@dataclass(frozen=True, slots=True)
class WavMetadata:
    sample_rate_hz: int
    channels: int
    frame_count: int
    encoding: str

    def __post_init__(self) -> None:
        if type(self.sample_rate_hz) is not int or self.sample_rate_hz <= 0:
            raise ValueError("WAV sample rate is invalid.")
        if type(self.channels) is not int or self.channels <= 0:
            raise ValueError("WAV channel count is invalid.")
        if type(self.frame_count) is not int or self.frame_count < 0:
            raise ValueError("WAV frame count is invalid.")
        if not isinstance(self.encoding, str) or not self.encoding:
            raise ValueError("WAV encoding is invalid.")

    @property
    def duration_frames(self) -> int:
        return self.frame_count

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "frame_count": self.frame_count,
            "encoding": self.encoding,
            "duration_frames": self.duration_frames,
        }

    @classmethod
    def from_dict(cls, raw: object) -> WavMetadata:
        expected = {
            "sample_rate_hz",
            "channels",
            "frame_count",
            "encoding",
            "duration_frames",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("WAV inventory metadata is invalid.")
        if raw["duration_frames"] != raw["frame_count"]:
            raise ValueError("WAV duration in frames is inconsistent.")
        return cls(
            sample_rate_hz=raw["sample_rate_hz"],
            channels=raw["channels"],
            frame_count=raw["frame_count"],
            encoding=raw["encoding"],
        )


@dataclass(frozen=True, slots=True)
class InventoryIssue:
    code: str
    relative_path: str
    message: str

    def __post_init__(self) -> None:
        for value in (self.code, self.relative_path, self.message):
            if not isinstance(value, str) or not value or len(value) > 1_000:
                raise ValueError("Inventory issue is invalid.")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "relative_path": self.relative_path,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, raw: object) -> InventoryIssue:
        if not isinstance(raw, dict) or set(raw) != {"code", "relative_path", "message"}:
            raise ValueError("Inventory issue is invalid.")
        return cls(raw["code"], raw["relative_path"], raw["message"])


@dataclass(frozen=True, slots=True)
class InventoryRecording:
    recording_key: str
    size_bytes: int | None
    mtime_ns: int | None
    content_sha256: str | None
    wav: WavMetadata | None
    decision: InclusionDecision
    status: RecordingStatus
    reason: str
    decision_origin: DecisionOrigin
    decision_path: str
    change: ChangeKind

    def __post_init__(self) -> None:
        key = validate_relative_reference(self.recording_key)
        if key != self.recording_key or not key.casefold().endswith(".wav"):
            raise ValueError("Inventory recording key must be a normalized relative WAV path.")
        if self.size_bytes is not None and (
            type(self.size_bytes) is not int or self.size_bytes < 0
        ):
            raise ValueError("Inventory recording size is invalid.")
        if self.mtime_ns is not None and type(self.mtime_ns) is not int:
            raise ValueError("Inventory recording change token is invalid.")
        if self.content_sha256 is not None and _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError("Inventory recording fingerprint is invalid.")
        if self.status is RecordingStatus.VALID and (
            self.size_bytes is None
            or self.mtime_ns is None
            or self.content_sha256 is None
            or self.wav is None
        ):
            raise ValueError("A valid inventory recording requires complete WAV facts.")
        if not isinstance(self.reason, str) or not self.reason or len(self.reason) > 1_000:
            raise ValueError("Inventory recording reason is invalid.")
        if not isinstance(self.decision_path, str) or len(self.decision_path) > 1_000:
            raise ValueError("Inventory recording decision source is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_key": self.recording_key,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "content_sha256": self.content_sha256,
            "wav": None if self.wav is None else self.wav.to_dict(),
            "decision": self.decision.value,
            "status": self.status.value,
            "reason": self.reason,
            "decision_origin": self.decision_origin.value,
            "decision_path": self.decision_path,
            "change": self.change.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> InventoryRecording:
        expected = {
            "recording_key",
            "size_bytes",
            "mtime_ns",
            "content_sha256",
            "wav",
            "decision",
            "status",
            "reason",
            "decision_origin",
            "decision_path",
            "change",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Inventory recording row is invalid.")
        return cls(
            recording_key=raw["recording_key"],
            size_bytes=raw["size_bytes"],
            mtime_ns=raw["mtime_ns"],
            content_sha256=raw["content_sha256"],
            wav=None if raw["wav"] is None else WavMetadata.from_dict(raw["wav"]),
            decision=InclusionDecision(raw["decision"]),
            status=RecordingStatus(raw["status"]),
            reason=raw["reason"],
            decision_origin=DecisionOrigin(raw["decision_origin"]),
            decision_path=raw["decision_path"],
            change=ChangeKind(raw["change"]),
        )


@dataclass(frozen=True, slots=True)
class InventoryCounts:
    included: int = 0
    undecided: int = 0
    excluded: int = 0
    invalid: int = 0
    missing: int = 0
    stale: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "included": self.included,
            "undecided": self.undecided,
            "excluded": self.excluded,
            "invalid": self.invalid,
            "missing": self.missing,
            "stale": self.stale,
        }


def summarize_inventory(rows: Iterable[InventoryRecording]) -> InventoryCounts:
    values = dict.fromkeys(InventoryCounts.__dataclass_fields__, 0)
    for row in rows:
        if row.status is RecordingStatus.INVALID:
            values["invalid"] += 1
        elif row.status is RecordingStatus.MISSING:
            values["missing"] += 1
        elif row.status is RecordingStatus.STALE:
            values["stale"] += 1
        elif row.decision is InclusionDecision.INCLUDED:
            values["included"] += 1
        elif row.decision is InclusionDecision.EXCLUDED:
            values["excluded"] += 1
        else:
            values["undecided"] += 1
    return InventoryCounts(**values)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Inventory scan timestamp must include a timezone.")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Inventory scan timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Inventory scan timestamp is invalid.") from exc
    return parsed


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    schema_version: int
    collection_id: str
    binding_revision: int
    inventory_id: str
    digest: str
    scanned_at: str
    freshness_strategy: str
    conflict_policy: str
    decision_rules: tuple[DecisionRule, ...]
    recordings: tuple[InventoryRecording, ...]
    issues: tuple[InventoryIssue, ...]

    def __post_init__(self) -> None:
        if self.schema_version != INVENTORY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported InventorySnapshot schema: {self.schema_version!r}.")
        validate_collection_id(self.collection_id)
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise ValueError("Inventory binding revision is invalid.")
        if _INVENTORY_ID.fullmatch(self.inventory_id) is None:
            raise ValueError("Inventory identifier is invalid.")
        if _SHA256.fullmatch(self.digest) is None:
            raise ValueError("Inventory digest is invalid.")
        _parse_utc(self.scanned_at)
        keys = [row.recording_key for row in self.recordings]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError(
                "Inventory recording keys must be uniquely and deterministically ordered."
            )
        if len(self.decision_rules) > MAX_DECISION_RULES:
            raise ValueError("Inventory has too many explicit decision rules.")
        rule_keys = [(portable_identity(rule.path), rule.is_folder) for rule in self.decision_rules]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("Inventory contains conflicting duplicate decision rules.")
        if len(self.issues) > MAX_INVENTORY_ISSUES:
            raise ValueError("Inventory has too many diagnostic issues.")

    @property
    def counts(self) -> InventoryCounts:
        return summarize_inventory(self.recordings)

    @property
    def included_keys(self) -> tuple[str, ...]:
        return tuple(
            row.recording_key
            for row in self.recordings
            if row.status is RecordingStatus.VALID and row.decision is InclusionDecision.INCLUDED
        )

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "collection_id": self.collection_id,
            "binding_revision": self.binding_revision,
            "scanned_at": self.scanned_at,
            "freshness_strategy": self.freshness_strategy,
            "conflict_policy": self.conflict_policy,
            "decision_rules": [rule.to_dict() for rule in self.decision_rules],
            "recordings": [row.to_dict() for row in self.recordings],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._unsigned_dict(),
            "inventory_id": self.inventory_id,
            "digest": self.digest,
            "counts": self.counts.to_dict(),
        }

    @classmethod
    def create(
        cls,
        *,
        collection_id: str,
        binding_revision: int,
        recordings: Iterable[InventoryRecording],
        decision_rules: Iterable[DecisionRule] = (),
        issues: Iterable[InventoryIssue] = (),
        scanned_at: datetime | None = None,
    ) -> InventorySnapshot:
        ordered_rows = tuple(sorted(recordings, key=lambda row: row.recording_key))
        ordered_rules = tuple(
            sorted(
                decision_rules,
                key=lambda rule: (portable_identity(rule.path), not rule.is_folder, rule.path),
            )
        )
        ordered_issues = tuple(
            sorted(issues, key=lambda issue: (issue.relative_path, issue.code, issue.message))
        )
        placeholder = cls(
            schema_version=INVENTORY_SCHEMA_VERSION,
            collection_id=collection_id,
            binding_revision=binding_revision,
            inventory_id="inv_" + "0" * 32,
            digest="0" * 64,
            scanned_at=_utc_text(scanned_at or datetime.now(UTC)),
            freshness_strategy=FRESHNESS_STRATEGY,
            conflict_policy=CONFLICT_POLICY,
            decision_rules=ordered_rules,
            recordings=ordered_rows,
            issues=ordered_issues,
        )
        digest = hashlib.sha256(_canonical_bytes(placeholder._unsigned_dict())).hexdigest()
        return replace(placeholder, inventory_id=f"inv_{digest[:32]}", digest=digest)

    @classmethod
    def from_dict(cls, raw: object) -> InventorySnapshot:
        expected = {
            "schema_version",
            "collection_id",
            "binding_revision",
            "inventory_id",
            "digest",
            "scanned_at",
            "freshness_strategy",
            "conflict_policy",
            "decision_rules",
            "recordings",
            "issues",
            "counts",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("InventorySnapshot document is invalid.")
        if not isinstance(raw["recordings"], list) or not isinstance(raw["issues"], list):
            raise ValueError("InventorySnapshot rows are invalid.")
        if not isinstance(raw["decision_rules"], list):
            raise ValueError("InventorySnapshot decisions are invalid.")
        created = cls.create(
            collection_id=raw["collection_id"],
            binding_revision=raw["binding_revision"],
            recordings=(InventoryRecording.from_dict(row) for row in raw["recordings"]),
            decision_rules=(DecisionRule.from_dict(rule) for rule in raw["decision_rules"]),
            issues=(InventoryIssue.from_dict(issue) for issue in raw["issues"]),
            scanned_at=_parse_utc(raw["scanned_at"]),
        )
        if raw["schema_version"] != INVENTORY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported InventorySnapshot schema: {raw['schema_version']!r}.")
        if raw["freshness_strategy"] != FRESHNESS_STRATEGY:
            raise ValueError("Inventory freshness strategy is unsupported.")
        if raw["conflict_policy"] != CONFLICT_POLICY:
            raise ValueError("Inventory conflict policy is unsupported.")
        if raw["inventory_id"] != created.inventory_id or raw["digest"] != created.digest:
            raise ValueError("InventorySnapshot digest does not match its contents.")
        if raw["counts"] != created.counts.to_dict():
            raise ValueError("InventorySnapshot counts do not match its rows.")
        return created


@dataclass(frozen=True, slots=True)
class BulkInclusionPlan:
    """One revision-checked replacement of the complete inventory decision set."""

    expected_inventory_id: str
    replaced_exclusion_count: int
    snapshot: InventorySnapshot


def plan_include_all_valid_recordings(
    snapshot: InventorySnapshot,
    *,
    expected_inventory_id: str,
    exclusions_confirmed: bool,
) -> BulkInclusionPlan:
    """Include every valid WAV while preserving unavailable rows and source facts."""

    if expected_inventory_id != snapshot.inventory_id:
        raise StaleInventoryRevisionError(
            "The recording inventory changed; review it before including recordings."
        )
    replaced_exclusions = sum(
        row.status is RecordingStatus.VALID
        and row.decision is InclusionDecision.EXCLUDED
        and row.decision_origin in {DecisionOrigin.EXPLICIT_FILE, DecisionOrigin.EXPLICIT_FOLDER}
        for row in snapshot.recordings
    )
    if replaced_exclusions and not exclusions_confirmed:
        raise BulkInclusionConfirmationRequired(replaced_exclusions)

    valid_identities = {
        portable_identity(row.recording_key)
        for row in snapshot.recordings
        if row.status is RecordingStatus.VALID
    }
    rules = [
        rule
        for rule in snapshot.decision_rules
        if rule.is_folder or portable_identity(rule.path) not in valid_identities
    ]
    rules.extend(
        DecisionRule.file(row.recording_key, InclusionDecision.INCLUDED)
        for row in snapshot.recordings
        if row.status is RecordingStatus.VALID
    )
    rows = tuple(
        replace(
            row,
            decision=InclusionDecision.INCLUDED,
            reason="Explicit file decision",
            decision_origin=DecisionOrigin.EXPLICIT_FILE,
            decision_path=row.recording_key,
        )
        if row.status is RecordingStatus.VALID
        else row
        for row in snapshot.recordings
    )
    replacement = InventorySnapshot.create(
        collection_id=snapshot.collection_id,
        binding_revision=snapshot.binding_revision,
        recordings=rows,
        decision_rules=rules,
        issues=snapshot.issues,
        scanned_at=_parse_utc(snapshot.scanned_at),
    )
    return BulkInclusionPlan(
        expected_inventory_id=snapshot.inventory_id,
        replaced_exclusion_count=replaced_exclusions,
        snapshot=replacement,
    )


@dataclass(frozen=True, slots=True)
class InventoryDelta:
    added: frozenset[str]
    removed: frozenset[str]
    replaced: frozenset[str]
    unchanged: frozenset[str]


def _present(snapshot: InventorySnapshot) -> dict[str, InventoryRecording]:
    return {
        row.recording_key: row
        for row in snapshot.recordings
        if row.status is not RecordingStatus.MISSING
    }


def compare_snapshots(previous: InventorySnapshot, current: InventorySnapshot) -> InventoryDelta:
    old = _present(previous)
    new = _present(current)
    old_keys = set(old)
    new_keys = set(new)
    shared = old_keys & new_keys
    unchanged = {
        key
        for key in shared
        if (
            old[key].size_bytes,
            old[key].mtime_ns,
            old[key].content_sha256,
            old[key].wav,
        )
        == (
            new[key].size_bytes,
            new[key].mtime_ns,
            new[key].content_sha256,
            new[key].wav,
        )
    }
    return InventoryDelta(
        added=frozenset(new_keys - old_keys),
        removed=frozenset(old_keys - new_keys),
        replaced=frozenset(shared - unchanged),
        unchanged=frozenset(unchanged),
    )


def find_portable_path_conflicts(paths: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    normalized_paths = tuple(paths)
    groups: dict[str, list[str]] = defaultdict(list)
    parent_spellings: dict[str, set[str]] = defaultdict(set)
    parent_members: dict[str, set[str]] = defaultdict(set)
    for path in normalized_paths:
        validate_relative_reference(path)
        groups[portable_identity(path)].append(path)
        parts = path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            parent = "/".join(parts[:index])
            identity = portable_identity(parent)
            parent_spellings[identity].add(parent)
            parent_members[identity].add(path)
    conflicts = {tuple(sorted(values)) for values in groups.values() if len(values) > 1}
    for identity, spellings in parent_spellings.items():
        if len(spellings) <= 1:
            continue
        matching = tuple(sorted(parent_members[identity]))
        if len(matching) > 1:
            conflicts.add(matching)
    return tuple(sorted(conflicts, key=lambda values: values[0]))


def find_file_identity_conflicts(
    file_ids: Mapping[str, tuple[int, int]],
) -> tuple[tuple[str, ...], ...]:
    groups: dict[tuple[int, int], list[str]] = defaultdict(list)
    for path, file_id in file_ids.items():
        validate_relative_reference(path)
        groups[file_id].append(path)
    return tuple(
        sorted(
            (tuple(sorted(values)) for values in groups.values() if len(values) > 1),
            key=lambda values: values[0],
        )
    )


def revise_decision(
    snapshot: InventorySnapshot,
    rule: DecisionRule,
    *,
    scanned_at: datetime | None = None,
) -> InventorySnapshot:
    rules = [
        existing
        for existing in snapshot.decision_rules
        if not (
            existing.is_folder == rule.is_folder
            and portable_identity(existing.path) == portable_identity(rule.path)
        )
    ]
    rules.append(rule)
    rows = []
    for row in snapshot.recordings:
        if row.decision_origin is DecisionOrigin.CONFLICT:
            rows.append(row)
            continue
        resolution = resolve_decision(row.recording_key, rules)
        rows.append(
            replace(
                row,
                decision=resolution.decision,
                reason=resolution.reason,
                decision_origin=resolution.origin,
                decision_path=resolution.source_path,
            )
        )
    return InventorySnapshot.create(
        collection_id=snapshot.collection_id,
        binding_revision=snapshot.binding_revision,
        recordings=rows,
        decision_rules=rules,
        issues=snapshot.issues,
        scanned_at=scanned_at or _parse_utc(snapshot.scanned_at),
    )


def clear_decision(
    snapshot: InventorySnapshot,
    path: str,
    *,
    is_folder: bool,
    scanned_at: datetime | None = None,
) -> InventorySnapshot:
    normalized = validate_relative_reference(path.rstrip("/"))
    rules = [
        rule
        for rule in snapshot.decision_rules
        if not (
            rule.is_folder == is_folder
            and portable_identity(rule.path) == portable_identity(normalized)
        )
    ]
    rows = []
    for row in snapshot.recordings:
        if row.decision_origin is DecisionOrigin.CONFLICT:
            rows.append(row)
            continue
        resolution = resolve_decision(row.recording_key, rules)
        rows.append(
            replace(
                row,
                decision=resolution.decision,
                reason=resolution.reason,
                decision_origin=resolution.origin,
                decision_path=resolution.source_path,
            )
        )
    return InventorySnapshot.create(
        collection_id=snapshot.collection_id,
        binding_revision=snapshot.binding_revision,
        recordings=rows,
        decision_rules=rules,
        issues=snapshot.issues,
        scanned_at=scanned_at or _parse_utc(snapshot.scanned_at),
    )
