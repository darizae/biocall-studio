"""Trusted, read-only Train Model intake and immutable scientific handoff facts."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from importlib import util as importlib_util
from importlib.metadata import version
from pathlib import Path
from typing import TypeAlias

from biocall_studio_train.domain.model import validate_model_manifest
from biocall_studio_train.domain.paths import validate_relative_path
from biocall_studio_train.persistence.collection_metadata import validate_collection_manifest
from biocall_studio_train.persistence.integrity import sha256_file
from biocall_studio_train.persistence.models import (
    structurally_reload_cnn_directory,
    structurally_reload_rf_directory,
)

MODEL_SNAPSHOT_SCHEMA_VERSION = 1
MAX_MODEL_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_COLLECTION_MANIFEST_BYTES = 16 * 1024 * 1024
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


def _read_json(path: Path, *, maximum_bytes: int, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe.")
    if path.stat().st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its bounded read limit.")
    try:
        with path.open(encoding="utf-8") as stream:
            raw = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON.") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    return raw


def _trusted_train_location(root: Path) -> None:
    models_root = root.parent
    alpaca_root = models_root.parent
    if (
        models_root.name != "models"
        or alpaca_root.name != ".alpaca"
        or models_root.is_symlink()
        or alpaca_root.is_symlink()
    ):
        raise ValueError(
            "Choose a Model from a trusted Train Model location (.alpaca/models)."
        )
    collection_path = alpaca_root / "collection.json"
    collection = _read_json(
        collection_path,
        maximum_bytes=MAX_COLLECTION_MANIFEST_BYTES,
        label="Train Collection manifest",
    )
    try:
        validate_collection_manifest(collection)
    except ValueError as exc:
        raise ValueError("The Model is not inside a verified local Train Collection.") from exc


def _verified_toolbox_import_origin() -> str:
    spec = importlib_util.find_spec("bioacoustics_dl_toolbox")
    if spec is None or spec.origin is None:
        raise ValueError("The verified bioacoustics toolbox runtime is unavailable.")
    origin = Path(spec.origin).resolve(strict=True)
    project_name: str | None = None
    for parent in origin.parents:
        metadata = parent / "pyproject.toml"
        if metadata.is_file():
            try:
                project = tomllib.loads(metadata.read_text(encoding="utf-8")).get("project", {})
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ValueError("The toolbox import origin cannot be verified.") from exc
            project_name = project.get("name") if isinstance(project, dict) else None
            break
    if project_name is not None and project_name != "bioacoustics-dl-toolbox":
        raise ValueError("An ambiguous pipeline copy shadows the direct bioacoustics toolbox.")
    if "alpaca-pipelines" in {part.casefold() for part in origin.parts}:
        raise ValueError("An ambiguous pipeline copy shadows the direct bioacoustics toolbox.")
    return str(origin)


def _require_runtime(manifest: dict, family: ModelFamily) -> tuple[tuple[str, str], ...]:
    provenance = manifest["provenance"]
    expected = {
        "biocall-studio-train": provenance["trainer"]["version"],
        "bioacoustics-dl-toolbox": provenance["toolbox"]["version"],
    }
    if family is ModelFamily.CNN:
        expected["torch"] = provenance["torch_version"]
    else:
        expected.update(
            {
                "scikit-learn": provenance["scikit_learn_version"],
                "joblib": provenance["joblib_version"],
                "librosa": provenance["librosa_version"],
            }
        )
    observed = {name: version(name) for name in expected}
    if expected != observed:
        mismatch = next(name for name in expected if expected[name] != observed[name])
        raise ValueError(
            f"The Model requires a different {mismatch} runtime and cannot be loaded safely."
        )
    return tuple(sorted(observed.items()))


def _contained_artifact(root: Path, manifest: dict) -> Path:
    relative = validate_relative_path(manifest["artifact"]["path"])
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("Model artifact cannot be a symlink.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("The selected Model artifact is missing.") from exc
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError("Model artifact escapes its selected folder.")
    artifact = manifest["artifact"]
    if resolved.stat().st_size != artifact["size_bytes"]:
        raise ValueError("Model artifact size disagrees with model.json.")
    if sha256_file(resolved) != artifact["sha256"]:
        raise ValueError("Model artifact digest disagrees with model.json.")
    return resolved


def _load_runtime_structure(root: Path, model_id: str, family: ModelFamily) -> None:
    if family is ModelFamily.CNN:
        structurally_reload_cnn_directory(root, model_id)
    else:
        structurally_reload_rf_directory(root, model_id)


def _snapshot(
    manifest: dict,
    *,
    manifest_sha256: str,
    runtime_versions: tuple[tuple[str, str], ...],
) -> ModelSnapshot:
    family = ModelFamily(manifest["family"])
    artifact = manifest["artifact"]
    input_spec = manifest["input"]
    source_revision = manifest["provenance"]["toolbox"]["revision"]
    token = json.dumps(
        {
            "manifest": manifest_sha256,
            "artifact": artifact["sha256"],
            "family": family.value,
            "runtime": runtime_versions,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    import hashlib

    snapshot_id = f"mdl_{hashlib.sha256(token).hexdigest()[:32]}"
    if family is ModelFamily.CNN:
        transforms = manifest["cnn"]["transforms"]
        role = ModelRole.PRIMARY_DETECTION
        probability_column = None
        feature_family = None
        feature_names: tuple[str, ...] = ()
        feature_config: _ConfigItems = ()
        spectrogram = _config_items(transforms["spectrogram"], label="spectrogram config")
        normalization = _config_items(
            transforms["normalization"], label="normalization config"
        )
        preprocessing = tuple(transforms["preprocessing_order"])
        loader_api = "bioacoustics_dl_toolbox.training.checkpoints.load_model"
        window_duration = input_spec["window_duration_ms"]
        window_samples = input_spec["window_length_samples"]
        frames = input_spec["sequence_length_frames"]
        minimum_duration = None
        short_policy = None
    else:
        rf = manifest["random_forest"]
        features = rf["features"]
        role = ModelRole.INTERVAL_REFINEMENT
        probability_column = rf["estimator"]["target_probability_column"]
        feature_family = features["family"]
        feature_names = tuple(features["names"])
        feature_config = _config_items(features["config"], label="RF feature config")
        spectrogram = ()
        normalization = ()
        preprocessing = tuple(input_spec["preprocessing_order"])
        loader_api = "joblib.load"
        window_duration = None
        window_samples = None
        frames = None
        minimum_duration = float(input_spec["min_duration_s"])
        short_policy = input_spec["short_segment_policy"]
    return ModelSnapshot(
        snapshot_id=snapshot_id,
        model_id=manifest["model_id"],
        label=manifest["label"],
        family=family,
        role=role,
        manifest_version=manifest["schema_version"],
        manifest_sha256=manifest_sha256,
        artifact_relative_path=artifact["path"],
        artifact_size_bytes=artifact["size_bytes"],
        artifact_sha256=artifact["sha256"],
        artifact_format=artifact["format"],
        artifact_format_version=artifact["format_version"],
        class_to_index=(("noise", 0), ("target", 1)),
        positive_class="target",
        positive_output_index=1,
        rf_probability_column=probability_column,
        channel_policy=input_spec["channel_policy"],
        sample_rate_policy=input_spec["sample_rate_policy"],
        sample_rate_hz=input_spec["sample_rate_hz"],
        window_duration_ms=window_duration,
        window_length_samples=window_samples,
        sequence_length_frames=frames,
        minimum_duration_seconds=minimum_duration,
        short_segment_policy=short_policy,
        preprocessing_order=preprocessing,
        spectrogram_config=spectrogram,
        normalization_config=normalization,
        rf_feature_family=feature_family,
        rf_feature_names=feature_names,
        rf_feature_config=feature_config,
        loader_api=loader_api,
        loader_distribution=(
            "bioacoustics-dl-toolbox" if family is ModelFamily.CNN else "joblib"
        ),
        loader_version=(
            version("bioacoustics-dl-toolbox")
            if family is ModelFamily.CNN
            else version("joblib")
        ),
        source_revision=source_revision,
        runtime_versions=runtime_versions,
        trusted=True,
        trust_reason="Verified current Train Collection, contained files, and declared checksums.",
        structure=ScientificEvidenceState.PASSED,
        runtime_loadable=ScientificEvidenceState.PASSED,
        prediction_parity=ScientificEvidenceState.UNPROVEN,
    )


def inspect_model_directory(root: Path) -> VerifiedModelReference:
    """Validate, trust, checksum, and only then structurally deserialize a Train Model."""
    selected = Path(root).expanduser()
    if selected.is_symlink():
        raise ValueError("Model folder cannot be a symlink.")
    try:
        resolved = selected.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("The selected Model folder is missing.") from exc
    if not resolved.is_dir() or not os.access(resolved, os.R_OK | os.X_OK):
        raise ValueError("The selected Model folder cannot be read.")
    _trusted_train_location(resolved)
    manifest_path = resolved / "model.json"
    raw = _read_json(
        manifest_path,
        maximum_bytes=MAX_MODEL_MANIFEST_BYTES,
        label="Model manifest",
    )
    manifest = validate_model_manifest(raw)
    if manifest["model_id"] != resolved.name:
        raise ValueError("Model folder identity disagrees with model.json.")
    artifact_path = _contained_artifact(resolved, manifest)
    family = ModelFamily(manifest["family"])
    runtime_versions = _require_runtime(manifest, family)
    _verified_toolbox_import_origin()
    manifest_digest = sha256_file(manifest_path)
    artifact_digest = sha256_file(artifact_path)
    try:
        _load_runtime_structure(resolved, manifest["model_id"], family)
    except Exception as exc:
        raise ValueError(
            "The Model binary is not structurally loadable by the verified runtime."
        ) from exc
    if (
        sha256_file(manifest_path) != manifest_digest
        or artifact_path.stat().st_size != manifest["artifact"]["size_bytes"]
        or sha256_file(artifact_path) != artifact_digest
    ):
        raise ValueError("Model files changed during compatibility inspection.")
    snapshot = _snapshot(
        manifest,
        manifest_sha256=manifest_digest,
        runtime_versions=runtime_versions,
    )
    return VerifiedModelReference(resolved, snapshot)


def recheck_model_reference(reference: VerifiedModelReference) -> VerifiedModelReference:
    """Reject changed bytes before any repeat deserialization, then rerun intake checks."""
    manifest_path = reference.root / "model.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError("The selected Model manifest is missing.")
    if sha256_file(manifest_path) != reference.snapshot.manifest_sha256:
        raise ValueError("The Model changed since it was selected; choose it again.")
    artifact = reference.root / reference.snapshot.artifact_relative_path
    if not artifact.is_file() or artifact.is_symlink():
        raise FileNotFoundError("The selected Model artifact is missing.")
    if (
        artifact.stat().st_size != reference.snapshot.artifact_size_bytes
        or sha256_file(artifact) != reference.snapshot.artifact_sha256
    ):
        raise ValueError("The Model changed since it was selected; choose it again.")
    current = inspect_model_directory(reference.root)
    if current.snapshot != reference.snapshot:
        raise ValueError("The Model compatibility evidence changed since it was selected.")
    return current


__all__ = [
    "MODEL_SNAPSHOT_SCHEMA_VERSION",
    "ModelFamily",
    "ModelRole",
    "ModelSnapshot",
    "ScientificEvidenceState",
    "VerifiedModelReference",
    "inspect_model_directory",
    "recheck_model_reference",
    "sha256_file",
]
