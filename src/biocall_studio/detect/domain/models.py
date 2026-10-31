"""Pure immutable Model compatibility contracts for Detect."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias

from biocall_studio.shared.paths import validate_relative_path

MODEL_SNAPSHOT_SCHEMA_VERSION = 1
_SNAPSHOT_ID = re.compile(r"mdl_[0-9a-f]{32}")
_Scalar: TypeAlias = str | int | float | bool | None
_ConfigItems: TypeAlias = tuple[tuple[str, _Scalar], ...]


class ModelFamily(StrEnum):
    CNN = "cnn"
    RANDOM_FOREST = "random_forest"


class ModelRole(StrEnum):
    PRIMARY_DETECTION = "primary_detection"
    INTERVAL_REFINEMENT = "interval_refinement"


class ScientificEvidenceState(StrEnum):
    PASSED = "passed"
    UNPROVEN = "unproven"


def _config_items(raw: object, *, label: str) -> _ConfigItems:
    if not isinstance(raw, dict):
        raise ValueError(f"Model {label} must be an object.")
    items: list[tuple[str, _Scalar]] = []
    for key in sorted(raw):
        value = raw[key]
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"Model {label} contains unsupported nested data.")
        items.append((key, value))
    return tuple(items)


def _items_to_json(items: _ConfigItems) -> list[list[_Scalar]]:
    return [[key, value] for key, value in items]


def _items_from_json(raw: object, *, label: str) -> _ConfigItems:
    if not isinstance(raw, list):
        raise ValueError(f"ModelSnapshot {label} is invalid.")
    value: dict[str, _Scalar] = {}
    for row in raw:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not isinstance(row[0], str)
            or not isinstance(row[1], (str, int, float, bool, type(None)))
            or row[0] in value
        ):
            raise ValueError(f"ModelSnapshot {label} is invalid.")
        value[row[0]] = row[1]
    return _config_items(value, label=label)


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    """Path-free, immutable Model facts for ST-06/07/09 handoff."""

    snapshot_id: str
    model_id: str
    label: str
    family: ModelFamily
    role: ModelRole
    manifest_version: int
    manifest_sha256: str
    artifact_relative_path: str
    artifact_size_bytes: int
    artifact_sha256: str
    artifact_format: str
    artifact_format_version: int
    class_to_index: tuple[tuple[str, int], ...]
    positive_class: str
    positive_output_index: int
    rf_probability_column: int | None
    channel_policy: str
    sample_rate_policy: str
    sample_rate_hz: int
    window_duration_ms: int | None
    window_length_samples: int | None
    sequence_length_frames: int | None
    minimum_duration_seconds: float | None
    short_segment_policy: str | None
    preprocessing_order: tuple[str, ...]
    spectrogram_config: _ConfigItems
    normalization_config: _ConfigItems
    rf_feature_family: str | None
    rf_feature_names: tuple[str, ...]
    rf_feature_config: _ConfigItems
    loader_api: str
    loader_distribution: str
    loader_version: str
    source_revision: str
    runtime_versions: tuple[tuple[str, str], ...]
    trusted: bool
    trust_reason: str
    structure: ScientificEvidenceState
    runtime_loadable: ScientificEvidenceState
    prediction_parity: ScientificEvidenceState
    schema_version: int = MODEL_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MODEL_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("Unsupported ModelSnapshot schema.")
        if _SNAPSHOT_ID.fullmatch(self.snapshot_id) is None:
            raise ValueError("ModelSnapshot identifier is invalid.")
        validate_relative_path(self.model_id)
        if "/" in self.model_id or not self.label.strip():
            raise ValueError("ModelSnapshot identity is invalid.")
        for digest in (self.manifest_sha256, self.artifact_sha256):
            invalid_character = any(
                character not in "0123456789abcdef" for character in digest
            )
            if len(digest) != 64 or invalid_character:
                raise ValueError("ModelSnapshot digest is invalid.")
        if self.class_to_index != (("noise", 0), ("target", 1)):
            raise ValueError("ModelSnapshot requires the exact noise/target mapping.")
        if (
            self.positive_class != "target"
            or self.positive_output_index != 1
            or self.sample_rate_hz <= 0
            or self.artifact_size_bytes <= 0
            or not self.trusted
            or self.structure is not ScientificEvidenceState.PASSED
            or self.runtime_loadable is not ScientificEvidenceState.PASSED
            or self.prediction_parity is not ScientificEvidenceState.UNPROVEN
        ):
            raise ValueError("ModelSnapshot compatibility evidence is invalid.")
        if self.family is ModelFamily.CNN:
            if (
                self.role is not ModelRole.PRIMARY_DETECTION
                or self.rf_probability_column is not None
                or self.window_length_samples is None
                or not self.spectrogram_config
                or not self.normalization_config
                or self.rf_feature_names
            ):
                raise ValueError("CNN ModelSnapshot family evidence is invalid.")
        elif (
            self.role is not ModelRole.INTERVAL_REFINEMENT
            or self.rf_probability_column is None
            or self.minimum_duration_seconds is None
            or not self.rf_feature_names
            or not self.rf_feature_config
        ):
            raise ValueError("Random Forest ModelSnapshot family evidence is invalid.")

    @property
    def primary_detection_compatible(self) -> bool:
        return self.role is ModelRole.PRIMARY_DETECTION

    @property
    def interval_refinement_compatible(self) -> bool:
        return self.role is ModelRole.INTERVAL_REFINEMENT

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "model_id": self.model_id,
            "label": self.label,
            "family": self.family.value,
            "role": self.role.value,
            "manifest_version": self.manifest_version,
            "manifest_sha256": self.manifest_sha256,
            "artifact_relative_path": self.artifact_relative_path,
            "artifact_size_bytes": self.artifact_size_bytes,
            "artifact_sha256": self.artifact_sha256,
            "artifact_format": self.artifact_format,
            "artifact_format_version": self.artifact_format_version,
            "class_to_index": [list(row) for row in self.class_to_index],
            "positive_class": self.positive_class,
            "positive_output_index": self.positive_output_index,
            "rf_probability_column": self.rf_probability_column,
            "channel_policy": self.channel_policy,
            "sample_rate_policy": self.sample_rate_policy,
            "sample_rate_hz": self.sample_rate_hz,
            "window_duration_ms": self.window_duration_ms,
            "window_length_samples": self.window_length_samples,
            "sequence_length_frames": self.sequence_length_frames,
            "minimum_duration_seconds": self.minimum_duration_seconds,
            "short_segment_policy": self.short_segment_policy,
            "preprocessing_order": list(self.preprocessing_order),
            "spectrogram_config": _items_to_json(self.spectrogram_config),
            "normalization_config": _items_to_json(self.normalization_config),
            "rf_feature_family": self.rf_feature_family,
            "rf_feature_names": list(self.rf_feature_names),
            "rf_feature_config": _items_to_json(self.rf_feature_config),
            "loader_api": self.loader_api,
            "loader_distribution": self.loader_distribution,
            "loader_version": self.loader_version,
            "source_revision": self.source_revision,
            "runtime_versions": [list(row) for row in self.runtime_versions],
            "trusted": self.trusted,
            "trust_reason": self.trust_reason,
            "structure": self.structure.value,
            "runtime_loadable": self.runtime_loadable.value,
            "prediction_parity": self.prediction_parity.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> ModelSnapshot:
        if not isinstance(raw, dict) or raw.get("schema_version") != MODEL_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("Unsupported ModelSnapshot schema.")
        expected = {
            "schema_version",
            "snapshot_id",
            "model_id",
            "label",
            "family",
            "role",
            "manifest_version",
            "manifest_sha256",
            "artifact_relative_path",
            "artifact_size_bytes",
            "artifact_sha256",
            "artifact_format",
            "artifact_format_version",
            "class_to_index",
            "positive_class",
            "positive_output_index",
            "rf_probability_column",
            "channel_policy",
            "sample_rate_policy",
            "sample_rate_hz",
            "window_duration_ms",
            "window_length_samples",
            "sequence_length_frames",
            "minimum_duration_seconds",
            "short_segment_policy",
            "preprocessing_order",
            "spectrogram_config",
            "normalization_config",
            "rf_feature_family",
            "rf_feature_names",
            "rf_feature_config",
            "loader_api",
            "loader_distribution",
            "loader_version",
            "source_revision",
            "runtime_versions",
            "trusted",
            "trust_reason",
            "structure",
            "runtime_loadable",
            "prediction_parity",
        }
        if set(raw) != expected:
            raise ValueError("ModelSnapshot fields do not match its schema.")
        mapping = raw["class_to_index"]
        runtimes = raw["runtime_versions"]
        if not isinstance(mapping, list) or not isinstance(runtimes, list):
            raise ValueError("ModelSnapshot mappings are invalid.")
        return cls(
            schema_version=raw["schema_version"],
            snapshot_id=raw["snapshot_id"],
            model_id=raw["model_id"],
            label=raw["label"],
            family=ModelFamily(raw["family"]),
            role=ModelRole(raw["role"]),
            manifest_version=raw["manifest_version"],
            manifest_sha256=raw["manifest_sha256"],
            artifact_relative_path=raw["artifact_relative_path"],
            artifact_size_bytes=raw["artifact_size_bytes"],
            artifact_sha256=raw["artifact_sha256"],
            artifact_format=raw["artifact_format"],
            artifact_format_version=raw["artifact_format_version"],
            class_to_index=tuple(tuple(row) for row in mapping),
            positive_class=raw["positive_class"],
            positive_output_index=raw["positive_output_index"],
            rf_probability_column=raw["rf_probability_column"],
            channel_policy=raw["channel_policy"],
            sample_rate_policy=raw["sample_rate_policy"],
            sample_rate_hz=raw["sample_rate_hz"],
            window_duration_ms=raw["window_duration_ms"],
            window_length_samples=raw["window_length_samples"],
            sequence_length_frames=raw["sequence_length_frames"],
            minimum_duration_seconds=raw["minimum_duration_seconds"],
            short_segment_policy=raw["short_segment_policy"],
            preprocessing_order=tuple(raw["preprocessing_order"]),
            spectrogram_config=_items_from_json(
                raw["spectrogram_config"], label="spectrogram config"
            ),
            normalization_config=_items_from_json(
                raw["normalization_config"], label="normalization config"
            ),
            rf_feature_family=raw["rf_feature_family"],
            rf_feature_names=tuple(raw["rf_feature_names"]),
            rf_feature_config=_items_from_json(
                raw["rf_feature_config"], label="RF feature config"
            ),
            loader_api=raw["loader_api"],
            loader_distribution=raw["loader_distribution"],
            loader_version=raw["loader_version"],
            source_revision=raw["source_revision"],
            runtime_versions=tuple(tuple(row) for row in runtimes),
            trusted=raw["trusted"],
            trust_reason=raw["trust_reason"],
            structure=ScientificEvidenceState(raw["structure"]),
            runtime_loadable=ScientificEvidenceState(raw["runtime_loadable"]),
            prediction_parity=ScientificEvidenceState(raw["prediction_parity"]),
        )


@dataclass(frozen=True, slots=True)
class VerifiedModelReference:
    root: Path
    snapshot: ModelSnapshot

    def __post_init__(self) -> None:
        if not self.root.is_absolute():
            raise ValueError("Verified Model reference root must be absolute.")


__all__ = [
    "MODEL_SNAPSHOT_SCHEMA_VERSION",
    "ModelFamily",
    "ModelRole",
    "ModelSnapshot",
    "ScientificEvidenceState",
    "VerifiedModelReference",
]
