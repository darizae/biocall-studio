"""Qt-free, bounded output-size and destination-capacity decisions.

The service deliberately knows nothing about Collections, Runs, Workers, or
scientific settings.  Workflow adapters provide frozen-input digests and byte
bounds; this module validates them, applies one reserve policy per filesystem,
and produces the admission decision shown by native workflow UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, localcontext
from enum import StrEnum
from pathlib import Path

KIB = 1_024
MIB = KIB**2
GIB = KIB**3
TIB = KIB**4
MAX_ESTIMATE_BYTES = 2**63 - 1
STORAGE_ESTIMATE_SCHEMA_VERSION = 1
MINIMUM_RESERVE_BYTES = 512 * MIB
RESERVE_PERCENT = 10
_SHA256_LENGTH = 64


class EstimateKind(StrEnum):
    EXACT = "exact"
    RANGE = "range"
    UNAVAILABLE = "unavailable"


class EstimateConfidence(StrEnum):
    ARITHMETIC = "arithmetic"
    MEASURED = "measured"
    INSUFFICIENT_EVIDENCE = "insufficient evidence"


class StorageDecision(StrEnum):
    READY = "ready"
    TIGHT = "tight"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"
    STALE = "stale"


class StoragePreflightError(ValueError):
    """The latest estimate does not admit the disk-writing operation."""


def _bounded_bytes(value: int, label: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive " if positive else "nonnegative "
        raise ValueError(f"{label} must be a {qualifier}integer byte count.")
    if value > MAX_ESTIMATE_BYTES:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return value


@dataclass(frozen=True, slots=True)
class ByteEstimate:
    kind: EstimateKind
    low_bytes: int | None
    high_bytes: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EstimateKind):
            raise ValueError("Output-size estimate kind is invalid.")
        if self.kind is EstimateKind.UNAVAILABLE:
            if self.low_bytes is not None or self.high_bytes is not None:
                raise ValueError("Unavailable output size cannot contain byte bounds.")
            return
        if self.low_bytes is None or self.high_bytes is None:
            raise ValueError("Available output size requires lower and upper byte bounds.")
        _bounded_bytes(self.low_bytes, "Estimated output lower bound")
        _bounded_bytes(self.high_bytes, "Estimated output upper bound")
        if self.low_bytes > self.high_bytes:
            raise ValueError("Estimated output byte range is reversed.")
        if self.kind is EstimateKind.EXACT and self.low_bytes != self.high_bytes:
            raise ValueError("Exact output size requires one byte value.")
        if self.kind is EstimateKind.RANGE and self.low_bytes == self.high_bytes:
            raise ValueError("Output-size range must contain distinct bounds.")

    @classmethod
    def exact(cls, size_bytes: int) -> ByteEstimate:
        return cls(EstimateKind.EXACT, size_bytes, size_bytes)

    @classmethod
    def range(cls, low_bytes: int, high_bytes: int) -> ByteEstimate:
        return cls(EstimateKind.RANGE, low_bytes, high_bytes)

    @classmethod
    def unavailable(cls) -> ByteEstimate:
        return cls(EstimateKind.UNAVAILABLE, None, None)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "low_bytes": self.low_bytes,
            "high_bytes": self.high_bytes,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ByteEstimate:
        if not isinstance(raw, dict) or set(raw) != {"kind", "low_bytes", "high_bytes"}:
            raise ValueError("Output-size estimate document is invalid.")
        return cls(EstimateKind(raw["kind"]), raw["low_bytes"], raw["high_bytes"])


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    target_label: str
    volume_id: str
    free_bytes: int | None
    observed_at: datetime
    error: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.target_label, str) or not self.target_label.strip():
            raise ValueError("Capacity target label is required.")
        if not isinstance(self.volume_id, str) or not self.volume_id:
            raise ValueError("Capacity volume identity is required.")
        if self.free_bytes is not None:
            _bounded_bytes(self.free_bytes, "Observed free space")
            if self.error:
                raise ValueError("Known capacity cannot also contain a query error.")
        elif not self.error:
            raise ValueError("Unknown capacity requires a privacy-safe reason.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Capacity observation time must include a timezone.")
        if len(self.error) > 120 or any(ord(character) < 32 for character in self.error):
            raise ValueError("Capacity query reason is invalid.")


@dataclass(frozen=True, slots=True)
class VolumeAssessment:
    target_label: str
    volume_id: str
    peak_bytes: int | None
    reserve_bytes: int | None
    required_bytes: int | None
    free_bytes: int | None
    observed_at: datetime
    decision: StorageDecision

    def __post_init__(self) -> None:
        if not self.target_label or not self.volume_id:
            raise ValueError("Storage volume label and identity are required.")
        for value, label in (
            (self.peak_bytes, "Peak additional space"),
            (self.reserve_bytes, "Reserved headroom"),
            (self.required_bytes, "Required storage"),
            (self.free_bytes, "Observed free space"),
        ):
            if value is not None:
                _bounded_bytes(value, label)
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Storage observation time must include a timezone.")
        if not isinstance(self.decision, StorageDecision):
            raise ValueError("Storage volume decision is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "target_label": self.target_label,
            "volume_id": self.volume_id,
            "peak_bytes": self.peak_bytes,
            "reserve_bytes": self.reserve_bytes,
            "required_bytes": self.required_bytes,
            "free_bytes": self.free_bytes,
            "observed_at": self.observed_at.isoformat(),
            "decision": self.decision.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> VolumeAssessment:
        expected = {
            "target_label",
            "volume_id",
            "peak_bytes",
            "reserve_bytes",
            "required_bytes",
            "free_bytes",
            "observed_at",
            "decision",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("Storage volume assessment document is invalid.")
        try:
            observed_at = datetime.fromisoformat(raw["observed_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Storage observation time is invalid.") from exc
        return cls(
            target_label=raw["target_label"],
            volume_id=raw["volume_id"],
            peak_bytes=raw["peak_bytes"],
            reserve_bytes=raw["reserve_bytes"],
            required_bytes=raw["required_bytes"],
            free_bytes=raw["free_bytes"],
            observed_at=observed_at,
            decision=StorageDecision(raw["decision"]),
        )


@dataclass(frozen=True, slots=True)
class StorageEstimate:
    schema_version: int
    operation: str
    input_digest: str
    expected_final: ByteEstimate
    volumes: tuple[VolumeAssessment, ...]
    confidence: EstimateConfidence
    basis: str
    decision: StorageDecision
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != STORAGE_ESTIMATE_SCHEMA_VERSION:
            raise ValueError("Unsupported StorageEstimate version.")
        if not isinstance(self.operation, str) or not self.operation:
            raise ValueError("Storage operation is required.")
        if (
            not isinstance(self.input_digest, str)
            or len(self.input_digest) != _SHA256_LENGTH
            or any(character not in "0123456789abcdef" for character in self.input_digest)
        ):
            raise ValueError("Storage input digest is invalid.")
        if not self.volumes:
            raise ValueError("StorageEstimate requires at least one destination volume.")
        if not isinstance(self.confidence, EstimateConfidence):
            raise ValueError("Storage estimate confidence is invalid.")
        if not isinstance(self.basis, str) or not self.basis or len(self.basis) > 500:
            raise ValueError("Storage estimate basis is invalid.")
        if not isinstance(self.decision, StorageDecision) or not self.reason:
            raise ValueError("Storage decision and reason are required.")

    @property
    def peak_bytes(self) -> int | None:
        """Return the sole-volume peak, avoiding false aggregation across volumes."""
        return self.volumes[0].peak_bytes if len(self.volumes) == 1 else None

    @property
    def reserve_bytes(self) -> int | None:
        """Return the sole-volume reserve, avoiding false aggregation across volumes."""
        return self.volumes[0].reserve_bytes if len(self.volumes) == 1 else None

    @property
    def requires_confirmation(self) -> bool:
        return self.decision in {StorageDecision.TIGHT, StorageDecision.UNKNOWN}

    @property
    def can_start(self) -> bool:
        return self.decision not in {StorageDecision.INSUFFICIENT, StorageDecision.STALE}

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "input_digest": self.input_digest,
            "expected_final": self.expected_final.to_dict(),
            "volumes": [volume.to_dict() for volume in self.volumes],
            "confidence": self.confidence.value,
            "basis": self.basis,
            "decision": self.decision.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: object) -> StorageEstimate:
        expected = {
            "schema_version",
            "operation",
            "input_digest",
            "expected_final",
            "volumes",
            "confidence",
            "basis",
            "decision",
            "reason",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != expected
            or not isinstance(raw["volumes"], list)
        ):
            raise ValueError("StorageEstimate document is invalid.")
        return cls(
            schema_version=raw["schema_version"],
            operation=raw["operation"],
            input_digest=raw["input_digest"],
            expected_final=ByteEstimate.from_dict(raw["expected_final"]),
            volumes=tuple(VolumeAssessment.from_dict(item) for item in raw["volumes"]),
            confidence=EstimateConfidence(raw["confidence"]),
            basis=raw["basis"],
            decision=StorageDecision(raw["decision"]),
            reason=raw["reason"],
        )


@dataclass(frozen=True, slots=True)
class OperationSizePlan:
    expected_final: ByteEstimate
    peak_bytes: int | None
    confidence: EstimateConfidence
    basis: str
    user_note: str = ""

    def __post_init__(self) -> None:
        if self.peak_bytes is not None:
            _bounded_bytes(self.peak_bytes, "Peak additional space")
            if (
                self.expected_final.high_bytes is not None
                and self.peak_bytes < self.expected_final.high_bytes
            ):
                raise ValueError("Peak additional space cannot be below final output size.")
        if self.expected_final.kind is EstimateKind.UNAVAILABLE and self.peak_bytes is not None:
            raise ValueError("Unavailable output sizing cannot claim a bounded peak.")
        if not self.basis:
            raise ValueError("Size-plan basis is required.")


def storage_input_digest(frozen_inputs: object) -> str:
    """Hash canonical privacy-safe frozen facts without accepting NaN/Infinity."""
    try:
        encoded = json.dumps(
            frozen_inputs,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Storage estimate inputs are not canonical JSON facts.") from exc
    return hashlib.sha256(encoded).hexdigest()


def pcm_wav_bytes(frame_count: int, *, channels: int, sample_width_bytes: int) -> int:
    """Exact standard PCM WAV bytes produced by the verified Python WAV writers."""
    _bounded_bytes(frame_count, "PCM frame count")
    if type(channels) is not int or channels not in {1, 2}:
        raise ValueError("PCM channel count must be one or two.")
    if type(sample_width_bytes) is not int or sample_width_bytes not in {1, 2, 3, 4}:
        raise ValueError("PCM sample width must be from one to four bytes.")
    payload = frame_count * channels * sample_width_bytes
    if payload > MAX_ESTIMATE_BYTES - 44:
        raise OverflowError("PCM WAV size exceeds the supported byte range.")
    return 44 + payload


def _rounded_decimal(value: int, unit: int, places: int) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        quantum = Decimal(1).scaleb(-places)
        return (Decimal(value) / Decimal(unit)).quantize(quantum, rounding=ROUND_CEILING)


def format_binary_size(size_bytes: int) -> str:
    """Format an upward-rounded binary quantity with researcher-facing unit labels."""
    _bounded_bytes(size_bytes, "Display size")
    if size_bytes == 0:
        return "0 KB"
    if size_bytes < KIB:
        return "1 KB"
    units = ((TIB, "TB"), (GIB, "GB"), (MIB, "MB"), (KIB, "KB"))
    unit, label = next(
        ((value, name) for value, name in units if size_bytes >= value),
        (KIB, "KB"),
    )
    raw = Decimal(size_bytes) / Decimal(unit)
    places = 1 if raw < 10 and size_bytes % unit else 0
    rounded = _rounded_decimal(size_bytes, unit, places)
    rendered = format(rounded, f".{places}f")
    return f"{rendered} {label}"


def format_output_estimate(estimate: ByteEstimate) -> str:
    if estimate.kind is EstimateKind.UNAVAILABLE:
        return ""
    assert estimate.low_bytes is not None and estimate.high_bytes is not None
    if estimate.kind is EstimateKind.EXACT:
        return f"about {format_binary_size(estimate.high_bytes)}"
    low = format_binary_size(estimate.low_bytes)
    high = format_binary_size(estimate.high_bytes)
    return f"about {high}" if low == high else f"{low}–{high}"


def reserve_for_peak(peak_bytes: int) -> int:
    _bounded_bytes(peak_bytes, "Peak additional space")
    percent = (peak_bytes * RESERVE_PERCENT + 99) // 100
    return max(MINIMUM_RESERVE_BYTES, percent)


def query_filesystem_capacity(path: Path, target_label: str) -> CapacityObservation:
    """Query the volume containing a destination or its nearest existing ancestor."""
    observed_at = datetime.now(UTC)
    candidate = Path(path)
    try:
        if not candidate.is_absolute():
            raise ValueError("destination_not_absolute")
        while not candidate.exists():
            parent = candidate.parent
            if parent == candidate:
                raise FileNotFoundError("destination_ancestor_missing")
            candidate = parent
        resolved = candidate.resolve(strict=True)
        usage = shutil.disk_usage(resolved)
        device = os.stat(resolved).st_dev
        return CapacityObservation(
            target_label=target_label,
            volume_id=f"device-{device}",
            free_bytes=usage.free,
            observed_at=observed_at,
        )
    except (OSError, ValueError) as exc:
        return CapacityObservation(
            target_label=target_label,
            volume_id="unknown-volume",
            free_bytes=None,
            observed_at=observed_at,
            error=type(exc).__name__,
        )


def _add_bounded(left: int, right: int, label: str) -> int:
    value = left + right
    if value > MAX_ESTIMATE_BYTES:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return value


def _volume_groups(
    target_peaks: Mapping[str, int | None],
    capacities: Mapping[str, CapacityObservation],
) -> tuple[tuple[str, str, int | None, int | None, datetime], ...]:
    """Combine simultaneous writes on one known filesystem without combining free space."""
    groups: dict[str, list[tuple[str, int | None, CapacityObservation]]] = {}
    for label, peak in target_peaks.items():
        observation = capacities[label]
        if observation.target_label != label:
            raise ValueError("Capacity observation target does not match its storage plan.")
        if peak is not None:
            _bounded_bytes(peak, "Peak additional space")
        # A failed query cannot prove that two destinations share a filesystem.
        group_key = (
            observation.volume_id
            if observation.free_bytes is not None
            else f"unknown:{label}"
        )
        groups.setdefault(group_key, []).append((label, peak, observation))

    combined = []
    for rows in groups.values():
        labels = tuple(row[0] for row in rows)
        peaks = tuple(row[1] for row in rows)
        observations = tuple(row[2] for row in rows)
        peak = None
        if all(value is not None for value in peaks):
            peak = 0
            for value in peaks:
                assert value is not None
                peak = _add_bounded(peak, value, "Combined peak additional space")
        known_free = tuple(
            observation.free_bytes
            for observation in observations
            if observation.free_bytes is not None
        )
        free = min(known_free) if len(known_free) == len(observations) else None
        combined.append(
            (
                " + ".join(labels),
                observations[0].volume_id,
                peak,
                free,
                max(observation.observed_at for observation in observations),
            )
        )
    return tuple(combined)


def assess_storage(
    *,
    operation: str,
    input_digest: str,
    expected_final: ByteEstimate,
    target_peaks: Mapping[str, int | None],
    capacities: Mapping[str, CapacityObservation],
    confidence: EstimateConfidence,
    basis: str,
    expected_input_digest: str | None = None,
) -> StorageEstimate:
    """Apply the reserve independently to every destination filesystem."""
    if not target_peaks or set(target_peaks) != set(capacities):
        raise ValueError("Every storage target requires exactly one capacity observation.")
    groups = _volume_groups(target_peaks, capacities)
    if expected_input_digest is not None and expected_input_digest != input_digest:
        assessments = tuple(
            VolumeAssessment(
                label,
                volume_id,
                peak,
                None,
                None,
                free,
                observed_at,
                StorageDecision.STALE,
            )
            for label, volume_id, peak, free, observed_at in groups
        )
        return StorageEstimate(
            STORAGE_ESTIMATE_SCHEMA_VERSION,
            operation,
            input_digest,
            expected_final,
            assessments,
            confidence,
            basis,
            StorageDecision.STALE,
            "The selected files, settings, or destination changed. Check storage again.",
        )

    assessments: list[VolumeAssessment] = []
    for label, volume_id, peak, free, observed_at in groups:
        if peak is None:
            assessments.append(
                VolumeAssessment(
                    label,
                    volume_id,
                    None,
                    None,
                    None,
                    free,
                    observed_at,
                    StorageDecision.UNKNOWN,
                )
            )
            continue
        reserve = reserve_for_peak(peak)
        required = _add_bounded(peak, reserve, "Required storage")
        if free is None:
            decision = StorageDecision.UNKNOWN
        elif free < required:
            decision = StorageDecision.INSUFFICIENT
        else:
            tight_ceiling = _add_bounded(required, reserve, "Tight-space threshold")
            decision = (
                StorageDecision.TIGHT
                if free < tight_ceiling
                else StorageDecision.READY
            )
        assessments.append(
            VolumeAssessment(
                label,
                volume_id,
                peak,
                reserve,
                required,
                free,
                observed_at,
                decision,
            )
        )

    decisions = {item.decision for item in assessments}
    if StorageDecision.INSUFFICIENT in decisions:
        decision = StorageDecision.INSUFFICIENT
        reason = (
            "Not enough free space for this operation. Choose another destination or free up "
            "space."
        )
    elif StorageDecision.UNKNOWN in decisions:
        decision = StorageDecision.UNKNOWN
        reason = "Can't check free space on this destination."
    elif StorageDecision.TIGHT in decisions:
        decision = StorageDecision.TIGHT
        reason = "Storage may run low while this runs. Continue?"
    else:
        decision = StorageDecision.READY
        reason = "Storage is ready."
    return StorageEstimate(
        STORAGE_ESTIMATE_SCHEMA_VERSION,
        operation,
        input_digest,
        expected_final,
        tuple(assessments),
        confidence,
        basis,
        decision,
        reason,
    )


def require_storage_admission(estimate: StorageEstimate, *, confirmed: bool = False) -> None:
    """Reject stale/insufficient decisions and require confirmation for uncertainty."""
    if estimate.decision is StorageDecision.STALE:
        raise StoragePreflightError(estimate.reason)
    if estimate.decision is StorageDecision.INSUFFICIENT:
        raise StoragePreflightError(estimate.reason)
    if estimate.requires_confirmation and not confirmed:
        raise StoragePreflightError(f"Storage confirmation is required. {estimate.reason}")


__all__ = [
    "GIB",
    "KIB",
    "MAX_ESTIMATE_BYTES",
    "MIB",
    "TIB",
    "ByteEstimate",
    "CapacityObservation",
    "EstimateConfidence",
    "EstimateKind",
    "OperationSizePlan",
    "StorageDecision",
    "StorageEstimate",
    "StoragePreflightError",
    "VolumeAssessment",
    "assess_storage",
    "format_binary_size",
    "format_output_estimate",
    "pcm_wav_bytes",
    "query_filesystem_capacity",
    "require_storage_admission",
    "reserve_for_peak",
    "storage_input_digest",
]
