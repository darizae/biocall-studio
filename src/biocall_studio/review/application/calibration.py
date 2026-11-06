"""Persist bounded local measurements for truthful Review cache sizing."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from biocall_studio.review.application.storage import CacheSizeCalibration
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_RENDER_VERSION,
    SpectrogramImageTier,
    validate_spectrogram_content_key,
)

_SCHEMA_VERSION = 1
_MAX_MEASUREMENTS = 256


@dataclass(frozen=True, slots=True)
class CacheMeasurement:
    """One completed encoded image measured on this installation."""

    content_key: str
    render_version: str
    tier: SpectrogramImageTier
    source_sha256: str
    encoded_bytes: int
    metadata_bytes: int
    staging_bytes: int
    elapsed_milliseconds: int

    def __post_init__(self) -> None:
        validate_spectrogram_content_key(self.content_key)
        if self.render_version != SPECTROGRAM_RENDER_VERSION:
            raise ValueError("Cache measurement renderer is incompatible.")
        if not isinstance(self.tier, SpectrogramImageTier):
            raise ValueError("Cache measurement tier is invalid.")
        if (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_sha256)
        ):
            raise ValueError("Cache measurement source digest is invalid.")
        for value, label in (
            (self.encoded_bytes, "encoded bytes"),
            (self.metadata_bytes, "metadata bytes"),
            (self.staging_bytes, "staging bytes"),
            (self.elapsed_milliseconds, "elapsed time"),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"Cache measurement {label} is invalid.")
        if self.staging_bytes < self.encoded_bytes:
            raise ValueError("Cache measurement staging bytes are invalid.")

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "tier": self.tier.value}

    @classmethod
    def from_dict(cls, value: object) -> CacheMeasurement:
        expected = {
            "content_key",
            "render_version",
            "tier",
            "source_sha256",
            "encoded_bytes",
            "metadata_bytes",
            "staging_bytes",
            "elapsed_milliseconds",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("Cache measurement record is invalid.")
        return cls(**{**value, "tier": SpectrogramImageTier(value["tier"])})


class CacheCalibrationStore:
    """Atomic, privacy-safe local cohort used only when at least ten samples exist."""

    def __init__(self, path: Path, *, max_measurements: int = _MAX_MEASUREMENTS):
        self.path = Path(path).expanduser().resolve(strict=False)
        if type(max_measurements) is not int or not 10 <= max_measurements <= 1_024:
            raise ValueError("Cache calibration bound is invalid.")
        self.max_measurements = max_measurements
        self._lock = threading.RLock()

    def _load(self) -> tuple[CacheMeasurement, ...]:
        if not self.path.exists():
            return ()
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("Cache calibration path is unsafe.")
        raw = self.path.read_bytes()
        if len(raw) > 512 * 1_024:
            raise ValueError("Cache calibration document is too large.")
        value = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "measurements"}
            or value["schema_version"] != _SCHEMA_VERSION
            or not isinstance(value["measurements"], list)
            or len(value["measurements"]) > self.max_measurements
        ):
            raise ValueError("Cache calibration document is invalid.")
        return tuple(CacheMeasurement.from_dict(item) for item in value["measurements"])

    def measurements(self) -> tuple[CacheMeasurement, ...]:
        with self._lock:
            return self._load()

    def record(self, measurement: CacheMeasurement) -> None:
        if not isinstance(measurement, CacheMeasurement):
            raise TypeError("Cache calibration measurement is invalid.")
        with self._lock:
            existing = self._load()
            retained = (
                *(item for item in existing if item.content_key != measurement.content_key),
                measurement,
            )[-self.max_measurements :]
            payload = json.dumps(
                {
                    "schema_version": _SCHEMA_VERSION,
                    "measurements": [item.to_dict() for item in retained],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.parent.is_symlink():
                raise ValueError("Cache calibration directory is unsafe.")
            staging = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex}.tmp"
            try:
                with staging.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(staging, self.path)
                os.chmod(self.path, 0o600)
            finally:
                if staging.exists() and not staging.is_symlink():
                    staging.unlink(missing_ok=True)

    def calibration(self, tier: SpectrogramImageTier) -> CacheSizeCalibration | None:
        tier = SpectrogramImageTier(tier)
        with self._lock:
            cohort = tuple(item for item in self._load() if item.tier is tier)
        if len(cohort) < 10:
            return None
        document = [item.to_dict() for item in cohort]
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        times = [item.elapsed_milliseconds for item in cohort]
        time_low = min(times)
        time_high = max(times)
        if time_low == time_high:
            time_high += 1
        return CacheSizeCalibration(
            calibration_version=f"local-v1-{digest}",
            render_version=SPECTROGRAM_RENDER_VERSION,
            tier=tier,
            sample_count=len(cohort),
            encoded_low_bytes=min(item.encoded_bytes for item in cohort),
            encoded_high_bytes=max(item.encoded_bytes for item in cohort),
            metadata_high_bytes=max(item.metadata_bytes for item in cohort),
            staging_high_bytes=max(item.staging_bytes for item in cohort),
            milliseconds_low=time_low,
            milliseconds_high=time_high,
        )


__all__ = ["CacheCalibrationStore", "CacheMeasurement"]
