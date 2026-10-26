"""Verified immutable Model loading and trusted family-specific structural reload."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
from bioacoustics_dl_toolbox.config import ClassifierConfig, EncoderConfig
from bioacoustics_dl_toolbox.models import Classifier, ResidualEncoder
from bioacoustics_dl_toolbox.training.checkpoints import (
    extract_model_metadata,
)
from bioacoustics_dl_toolbox.training.checkpoints import (
    load_model as toolbox_load_model,
)
from sklearn.ensemble import RandomForestClassifier

from biocall_studio_train.domain.model import validate_model_manifest
from biocall_studio_train.domain.paths import validate_relative_path
from biocall_studio_train.domain.rf_training import validate_rf_estimator_structure
from biocall_studio_train.persistence.integrity import sha256_file

MAX_MODEL_JSON_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ModelArtifact:
    root: Path
    manifest: dict[str, Any]

    @property
    def model_id(self) -> str:
        return self.manifest["model_id"]

    @property
    def label(self) -> str:
        return self.manifest["label"]


@dataclass(frozen=True)
class CnnModelStructure:
    model_id: str
    num_classes: int
    class_to_index: dict[str, int]
    encoder_config: dict[str, Any]
    classifier_config: dict[str, Any]
    spectrogram_config: dict[str, Any]
    normalization_config: dict[str, Any]
    window_length_samples: int
    sequence_length_frames: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RfModelStructure:
    model_id: str
    classes: tuple[int, int]
    class_to_index: dict[str, int]
    target_probability_column: int
    n_features: int
    feature_names: tuple[str, ...]
    feature_importances: tuple[float, ...]
    feature_config: dict[str, Any]
    threshold: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _models_root(collection_root: Path, *, create: bool = False) -> Path:
    collection = collection_root.resolve(strict=True)
    alpaca = collection / ".alpaca"
    if alpaca.is_symlink() or not alpaca.is_dir():
        raise ValueError("Validated Collection metadata folder is missing or unsafe.")
    root = alpaca / "models"
    if root.is_symlink():
        raise ValueError("Model storage cannot use symlinks.")
    if create:
        root.mkdir(exist_ok=True)
    if root.exists() and (
        not root.is_dir() or not root.resolve(strict=True).is_relative_to(collection)
    ):
        raise ValueError("Model storage escapes the selected Collection.")
    return root


def _model_root(collection_root: Path, model_id: str) -> Path:
    safe = validate_relative_path(model_id)
    if "/" in safe:
        raise ValueError("Model ID must be one portable path segment.")
    candidate = _models_root(collection_root) / safe
    if candidate.is_symlink():
        raise ValueError("Model directory cannot be a symlink.")
    return candidate


def _contained_file(root: Path, relative: str) -> Path:
    safe = validate_relative_path(relative)
    candidate = root / safe
    if candidate.is_symlink():
        raise ValueError(f"Model file cannot be a symlink: {safe}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError(f"Model reference escapes its immutable directory: {safe}")
    return resolved


def load_model_directory(root: Path, expected_model_id: str) -> ModelArtifact:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Model directory is missing or unsafe.")
    root = root.resolve(strict=True)
    manifest_path = _contained_file(root, "model.json")
    if manifest_path.stat().st_size > MAX_MODEL_JSON_BYTES:
        raise ValueError("Model manifest exceeds 4 MiB.")
    try:
        with manifest_path.open(encoding="utf-8") as stream:
            manifest = validate_model_manifest(json.load(stream))
    except json.JSONDecodeError as exc:
        raise ValueError("Model manifest is invalid JSON.") from exc
    if manifest["model_id"] != expected_model_id or root.name != expected_model_id:
        raise ValueError("Model directory identity does not match its manifest.")
    artifact = manifest["artifact"]
    binary = _contained_file(root, artifact["path"])
    if binary.stat().st_size != artifact["size_bytes"]:
        raise ValueError("Model binary size disagrees with its manifest.")
    if sha256_file(binary) != artifact["sha256"]:
        raise ValueError("Model binary digest disagrees with its manifest.")
    return ModelArtifact(root, manifest)


def load_model(collection_root: Path, model_id: str) -> ModelArtifact:
    root = _model_root(collection_root, model_id)
    if not root.is_dir():
        raise FileNotFoundError(f"Model does not exist: {model_id}")
    return load_model_directory(root, model_id)


def list_models(collection_root: Path) -> tuple[ModelArtifact, ...]:
    root = _models_root(collection_root)
    if not root.exists():
        return ()
    artifacts = tuple(
        load_model(collection_root, path.name)
        for path in root.iterdir()
        if path.is_dir() and not path.is_symlink()
    )
    return tuple(
        sorted(
            artifacts,
            key=lambda item: (item.manifest["created_at"], item.model_id),
            reverse=True,
        )
    )


def discard_uncommitted_model(
    collection_root: Path,
    model_id: str,
    *,
    run_id: str,
    request_id: str,
) -> bool:
    """Remove only a verified output owned by the failed prospective Run."""
    try:
        artifact = load_model(collection_root, model_id)
    except FileNotFoundError:
        return False
    if artifact.manifest["run_id"] != run_id or artifact.manifest["request_id"] != request_id:
        raise ValueError("Prospective Model identity belongs to a different Run.")
    parent = artifact.root.parent
    shutil.rmtree(artifact.root)
    try:
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass
    return True


def structurally_reload_cnn_model(collection_root: Path, model_id: str) -> CnnModelStructure:
    """Verify manifest/hash, then deserialize trusted local bytes and load both state dicts."""
    artifact = load_model(collection_root, model_id)
    return structurally_reload_cnn_directory(artifact.root, model_id)


def structurally_reload_cnn_directory(root: Path, model_id: str) -> CnnModelStructure:
    """Structurally verify a trusted staged or published CNN Model directory."""
    artifact = load_model_directory(root, model_id)
    manifest = artifact.manifest
    if manifest["family"] != "cnn":
        raise ValueError("CNN structural reload requires a CNN Model.")
    binary = artifact.root / manifest["artifact"]["path"]
    payload = toolbox_load_model(binary)
    required = {
        "encoderConfig",
        "classifierConfig",
        "spectrogramConfig",
        "encoderState",
        "classifierState",
        "classes",
        "metadata",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("CNN checkpoint fields do not match the supported export schema.")
    architecture = manifest["cnn"]["architecture"]
    transforms = manifest["cnn"]["transforms"]
    if payload["encoderConfig"] != architecture["encoder"]:
        raise ValueError("CNN checkpoint encoder config disagrees with model.json.")
    if payload["classifierConfig"] != architecture["classifier"]:
        raise ValueError("CNN checkpoint classifier config disagrees with model.json.")
    if payload["spectrogramConfig"] != transforms["spectrogram"]:
        raise ValueError("CNN checkpoint spectrogram config disagrees with model.json.")
    if payload["classes"] != manifest["task"]["class_to_index"]:
        raise ValueError("CNN checkpoint class mapping disagrees with model.json.")
    metadata = extract_model_metadata(payload)
    if metadata["task_type"] != "binary" or metadata["class_names"] != ["noise", "target"]:
        raise ValueError("CNN checkpoint does not declare the required binary class order.")
    if metadata["normalization_config"] != transforms["normalization"]:
        raise ValueError("CNN checkpoint normalization config disagrees with model.json.")
    if (
        metadata["window_length_samples"] != manifest["input"]["window_length_samples"]
        or metadata["sequence_length_frames"] != manifest["input"]["sequence_length_frames"]
    ):
        raise ValueError("CNN checkpoint input shape disagrees with model.json.")

    try:
        encoder_config = EncoderConfig(**payload["encoderConfig"])
        classifier_config = ClassifierConfig(**payload["classifierConfig"])
    except TypeError as exc:
        raise ValueError(f"CNN checkpoint architecture config is invalid: {exc}") from exc
    if classifier_config.num_classes != 2:
        raise ValueError("CNN checkpoint classifier must have exactly two outputs.")
    encoder = ResidualEncoder(encoder_config)
    classifier = Classifier(classifier_config)
    try:
        encoder.load_state_dict(payload["encoderState"], strict=True)
        classifier.load_state_dict(payload["classifierState"], strict=True)
    except (RuntimeError, TypeError) as exc:
        raise ValueError(f"CNN checkpoint tensor state is incompatible: {exc}") from exc
    if (
        classifier.linear.out_features != 2
        or classifier.linear.in_features != encoder.output_channels
    ):
        raise ValueError("CNN checkpoint head shape disagrees with its encoder and binary task.")
    return CnnModelStructure(
        model_id=model_id,
        num_classes=classifier.linear.out_features,
        class_to_index=dict(payload["classes"]),
        encoder_config=dict(payload["encoderConfig"]),
        classifier_config=dict(payload["classifierConfig"]),
        spectrogram_config=dict(payload["spectrogramConfig"]),
        normalization_config=dict(metadata["normalization_config"]),
        window_length_samples=int(metadata["window_length_samples"]),
        sequence_length_frames=int(metadata["sequence_length_frames"]),
    )


def structurally_reload_rf_model(collection_root: Path, model_id: str) -> RfModelStructure:
    """Verify manifest/hash, then deserialize trusted local RF estimator bytes."""
    artifact = load_model(collection_root, model_id)
    return structurally_reload_rf_directory(artifact.root, model_id)


def structurally_reload_rf_directory(root: Path, model_id: str) -> RfModelStructure:
    """Structurally verify a trusted staged or published RF Model directory."""
    artifact = load_model_directory(root, model_id)
    manifest = artifact.manifest
    if manifest["family"] != "random_forest":
        raise ValueError("RF structural reload requires a Random Forest Model.")
    binary = artifact.root / manifest["artifact"]["path"]
    estimator = joblib.load(binary)
    if not isinstance(estimator, RandomForestClassifier):
        raise ValueError("RF binary is not a supported RandomForestClassifier.")
    rf = manifest["random_forest"]
    estimator_spec = rf["estimator"]
    feature_names = tuple(rf["features"]["names"])
    class_order = tuple(estimator_spec["classes"])
    validate_rf_estimator_structure(
        estimator,
        feature_names=feature_names,
        probability_class_order=class_order,
    )
    parameters = estimator.get_params(deep=False)
    for name, expected in estimator_spec["hyperparameters"].items():
        if parameters.get(name) != expected:
            raise ValueError(f"RF estimator hyperparameter disagrees with model.json: {name}")
    importances = tuple(float(value) for value in estimator.feature_importances_)
    declared = tuple(float(row["value"]) for row in manifest["results"]["feature_importances"])
    if importances != declared:
        raise ValueError("RF estimator importances disagree with model.json.")
    return RfModelStructure(
        model_id=model_id,
        classes=(int(class_order[0]), int(class_order[1])),
        class_to_index=dict(manifest["task"]["class_to_index"]),
        target_probability_column=int(estimator_spec["target_probability_column"]),
        n_features=int(estimator.n_features_in_),
        feature_names=feature_names,
        feature_importances=importances,
        feature_config=dict(rf["features"]["config"]),
        threshold=float(rf["decision_policy"]["threshold"]),
    )
