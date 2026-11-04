"""Review-only cache sizing adapter over the shared REV-05 storage contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_RENDER_VERSION,
    SpectrogramImageTier,
)
from biocall_studio.shared.storage import (
    MAX_ESTIMATE_BYTES,
    ByteEstimate,
    CapacityObservation,
    EstimateConfidence,
    EstimateKind,
    OperationSizePlan,
    StorageEstimate,
    assess_storage,
    query_filesystem_capacity,
    storage_input_digest,
)


def _bounded(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer.")
    if value > MAX_ESTIMATE_BYTES:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return value


def _multiply(left: int, right: int, label: str) -> int:
    _bounded(left, label)
    _bounded(right, label)
    if left and right > MAX_ESTIMATE_BYTES // left:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return left * right


def _add(left: int, right: int, label: str) -> int:
    _bounded(left, label)
    _bounded(right, label)
    if right > MAX_ESTIMATE_BYTES - left:
        raise OverflowError(f"{label} exceeds the supported byte range.")
    return left + right


@dataclass(frozen=True, slots=True)
class TimeEstimate:
    kind: EstimateKind
    low_milliseconds: int | None
    high_milliseconds: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EstimateKind):
            raise ValueError("Cache time estimate kind is invalid.")
        if self.kind is EstimateKind.UNAVAILABLE:
            if self.low_milliseconds is not None or self.high_milliseconds is not None:
                raise ValueError("Unavailable cache time cannot contain bounds.")
            return
        if self.low_milliseconds is None or self.high_milliseconds is None:
            raise ValueError("Cache time estimate requires both bounds.")
        _bounded(self.low_milliseconds, "Cache time lower bound")
        _bounded(self.high_milliseconds, "Cache time upper bound")
        if self.low_milliseconds > self.high_milliseconds:
            raise ValueError("Cache time estimate range is reversed.")
        if self.kind is EstimateKind.EXACT and self.low_milliseconds != self.high_milliseconds:
            raise ValueError("Exact cache time requires one value.")
        if self.kind is EstimateKind.RANGE and self.low_milliseconds == self.high_milliseconds:
            raise ValueError("Cache time range requires distinct bounds.")

    @classmethod
    def unavailable(cls) -> TimeEstimate:
        return cls(EstimateKind.UNAVAILABLE, None, None)


@dataclass(frozen=True, slots=True)
class CacheSizeCalibration:
    """A caller-supplied measured cohort; no pilot constants live in production."""

    calibration_version: str
    render_version: str
    tier: SpectrogramImageTier
    sample_count: int
    encoded_low_bytes: int
    encoded_high_bytes: int
    metadata_high_bytes: int
    staging_high_bytes: int
    milliseconds_low: int | None
    milliseconds_high: int | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.calibration_version, str)
            or not self.calibration_version
            or len(self.calibration_version) > 120
        ):
            raise ValueError("Cache calibration version is invalid.")
        if self.render_version != SPECTROGRAM_RENDER_VERSION:
            raise ValueError("Cache calibration does not match the active renderer.")
        if not isinstance(self.tier, SpectrogramImageTier):
            raise ValueError("Cache calibration image tier is invalid.")
        if type(self.sample_count) is not int or self.sample_count < 10:
            raise ValueError("Cache calibration requires at least ten measured images.")
        for value, label in (
            (self.encoded_low_bytes, "Encoded cache lower bound"),
            (self.encoded_high_bytes, "Encoded cache upper bound"),
            (self.metadata_high_bytes, "Cache metadata upper bound"),
            (self.staging_high_bytes, "Cache staging upper bound"),
        ):
            _bounded(value, label)
        if self.encoded_low_bytes <= 0 or self.encoded_low_bytes > self.encoded_high_bytes:
            raise ValueError("Encoded cache calibration range is invalid.")
        if self.staging_high_bytes < self.encoded_high_bytes:
            raise ValueError("Cache staging bound cannot be below the encoded image bound.")
        if (self.milliseconds_low is None) != (self.milliseconds_high is None):
            raise ValueError("Cache time calibration requires both bounds or neither.")
        if self.milliseconds_low is not None and self.milliseconds_high is not None:
            _bounded(self.milliseconds_low, "Cache time lower bound")
            _bounded(self.milliseconds_high, "Cache time upper bound")
            if self.milliseconds_low >= self.milliseconds_high:
                raise ValueError("Cache time calibration range is invalid.")


@dataclass(frozen=True, slots=True)
class ReviewCacheSizePlan:
    input_digest: str
    missing_count: int
    cache_hit_count: int
    existing_cache_bytes: int
    tier: SpectrogramImageTier
    settings_digest: str
    size_plan: OperationSizePlan
    time_estimate: TimeEstimate
    calibration_version: str | None


def measured_cache_limit(
    calibration: CacheSizeCalibration,
    *,
    item_capacity: int,
) -> int:
    """Derive a quota from measured upper cost and an explicit item capacity."""
    if not isinstance(calibration, CacheSizeCalibration):
        raise TypeError("Cache limit calibration is invalid.")
    _bounded(item_capacity, "Cache item capacity")
    per_item = _add(
        calibration.encoded_high_bytes,
        calibration.metadata_high_bytes,
        "Measured cache bytes per item",
    )
    outputs = _multiply(item_capacity, per_item, "Measured cache limit")
    return _add(outputs, calibration.staging_high_bytes, "Measured cache limit")


def plan_review_cache_generation(
    *,
    missing_count: int,
    existing_file_sizes: tuple[int, ...] | list[int],
    tier: SpectrogramImageTier,
    settings_digest: str,
    calibration: CacheSizeCalibration | None,
) -> ReviewCacheSizePlan:
    """Size only new writes; existing valid cache hits remain exact context."""
    _bounded(missing_count, "Missing spectrogram count")
    if not isinstance(tier, SpectrogramImageTier):
        raise ValueError("Spectrogram sizing tier is invalid.")
    if (
        not isinstance(settings_digest, str)
        or len(settings_digest) != 64
        or any(character not in "0123456789abcdef" for character in settings_digest)
    ):
        raise ValueError("Spectrogram settings digest is invalid.")
    sizes = tuple(existing_file_sizes)
    existing_bytes = 0
    for size in sizes:
        existing_bytes = _add(
            existing_bytes,
            _bounded(size, "Existing cache file size"),
            "Existing cache bytes",
        )

    if missing_count == 0:
        output = ByteEstimate.exact(0)
        peak = 0
        confidence = EstimateConfidence.ARITHMETIC
        basis = "All requested spectrograms are verified cache hits; no image write is planned."
        time_estimate = TimeEstimate.unavailable()
        calibration_version = calibration.calibration_version if calibration is not None else None
    elif calibration is None or calibration.tier is not tier:
        output = ByteEstimate.unavailable()
        peak = None
        confidence = EstimateConfidence.INSUFFICIENT_EVIDENCE
        basis = (
            "No compatible measured encoded-image cohort is available; cache bytes cannot yet "
            "be estimated reliably."
        )
        time_estimate = TimeEstimate.unavailable()
        calibration_version = None
    else:
        low_per_image = _add(
            calibration.encoded_low_bytes,
            calibration.metadata_high_bytes,
            "Per-image cache lower bound",
        )
        high_per_image = _add(
            calibration.encoded_high_bytes,
            calibration.metadata_high_bytes,
            "Per-image cache upper bound",
        )
        low = _multiply(missing_count, low_per_image, "Cache output lower bound")
        high = _multiply(missing_count, high_per_image, "Cache output upper bound")
        output = ByteEstimate.exact(low) if low == high else ByteEstimate.range(low, high)
        peak = _add(high, calibration.staging_high_bytes, "Cache peak staging bytes")
        confidence = EstimateConfidence.MEASURED
        basis = (
            f"Measured encoded {tier.value} images and manifest growth from "
            f"{calibration.sample_count} local outputs ({calibration.calibration_version})."
        )
        if calibration.milliseconds_low is None or calibration.milliseconds_high is None:
            time_estimate = TimeEstimate.unavailable()
        else:
            time_estimate = TimeEstimate(
                EstimateKind.RANGE,
                _multiply(
                    missing_count,
                    calibration.milliseconds_low,
                    "Cache time lower bound",
                ),
                _multiply(
                    missing_count,
                    calibration.milliseconds_high,
                    "Cache time upper bound",
                ),
            )
        calibration_version = calibration.calibration_version

    frozen_inputs = {
        "operation": "review.generate_spectrograms",
        "missing_count": missing_count,
        "cache_hit_count": len(sizes),
        "existing_cache_bytes": existing_bytes,
        "tier": tier.value,
        "settings_digest": settings_digest,
        "render_version": SPECTROGRAM_RENDER_VERSION,
        "calibration_version": calibration_version,
    }
    return ReviewCacheSizePlan(
        input_digest=storage_input_digest(frozen_inputs),
        missing_count=missing_count,
        cache_hit_count=len(sizes),
        existing_cache_bytes=existing_bytes,
        tier=tier,
        settings_digest=settings_digest,
        size_plan=OperationSizePlan(
            expected_final=output,
            peak_bytes=peak,
            confidence=confidence,
            basis=basis,
            user_note=(
                "Generation time depends on this computer and cannot yet be estimated reliably."
                if time_estimate.kind is EstimateKind.UNAVAILABLE
                else "Generation time is a measured range and may vary on this computer."
            ),
        ),
        time_estimate=time_estimate,
        calibration_version=calibration_version,
    )


def assess_review_cache_storage(
    plan: ReviewCacheSizePlan,
    *,
    cache_root: Path | None = None,
    capacity: CapacityObservation | None = None,
    expected_input_digest: str | None = None,
) -> StorageEstimate:
    """Use the shared REV-05 decision service for the actual cache volume."""
    if not isinstance(plan, ReviewCacheSizePlan):
        raise TypeError("Review cache size plan is invalid.")
    if capacity is None:
        if cache_root is None:
            raise ValueError("Cache root is required for a live capacity check.")
        capacity = query_filesystem_capacity(Path(cache_root), "Spectrogram cache")
    if capacity.target_label != "Spectrogram cache":
        raise ValueError("Cache capacity observation has the wrong target.")
    return assess_storage(
        operation="review.generate_spectrograms",
        input_digest=plan.input_digest,
        expected_input_digest=expected_input_digest,
        expected_final=plan.size_plan.expected_final,
        target_peaks={"Spectrogram cache": plan.size_plan.peak_bytes},
        capacities={"Spectrogram cache": capacity},
        confidence=plan.size_plan.confidence,
        basis=plan.size_plan.basis,
    )


__all__ = [
    "CacheSizeCalibration",
    "ReviewCacheSizePlan",
    "TimeEstimate",
    "assess_review_cache_storage",
    "measured_cache_limit",
    "plan_review_cache_generation",
]
