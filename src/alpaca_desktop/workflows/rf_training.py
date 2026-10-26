"""Genuine deterministic Random Forest Training and immutable Model publication."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import librosa
import numpy as np
from bioacoustics_dl_toolbox.audio import load_audio_file
from bioacoustics_dl_toolbox.rf import compute_rf_features
from numpy.typing import NDArray
from sklearn.ensemble import RandomForestClassifier

from alpaca_desktop.domain.model import MODEL_SCIENTIFIC_REFERENCE, MODEL_TOOLBOX_REVISION
from alpaca_desktop.domain.paths import validate_relative_path
from alpaca_desktop.domain.rf_training import (
    ROBUST_FEATURE_NAMES,
    evaluate_binary_probabilities,
    rf_feature_names,
    validate_rf_estimator_structure,
)
from alpaca_desktop.domain.training import (
    DeviceCapabilities,
    FrozenTrainingConfig,
    TrainingDataset,
    verify_frozen_training_config,
)
from alpaca_desktop.persistence.datasets import DatasetArtifact, load_dataset
from alpaca_desktop.persistence.integrity import sha256_file
from alpaca_desktop.persistence.models import (
    ModelArtifact,
    load_model,
    structurally_reload_rf_directory,
)
from alpaca_desktop.workflows.model_publication import (
    publish_model_directory,
    write_model_manifest,
)

RF_EXTRACTOR_API = "bioacoustics_dl_toolbox.rf.compute_rf_features"
RF_EXTRACTOR_REVISION = MODEL_TOOLBOX_REVISION
RF_FEATURE_FAMILY = "robust-mfcc-v1"


class RfTrainingError(RuntimeError):
    pass


class RfTrainingCancelled(RfTrainingError):
    pass


@dataclass(frozen=True)
class RfTrainingRequest:
    run_id: str
    request_id: str
    collection_root: str
    collection_id: str
    config: FrozenTrainingConfig
    model_id: str
    model_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "collection_root": self.collection_root,
            "collection_id": self.collection_id,
            "config": self.config.to_worker_snapshot(),
            "model_id": self.model_id,
            "model_label": self.model_label,
        }

    @classmethod
    def from_dict(cls, raw: object) -> RfTrainingRequest:
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported RF Training request schema.")
        expected = {
            "schema_version",
            "run_id",
            "request_id",
            "collection_root",
            "collection_id",
            "config",
            "model_id",
            "model_label",
        }
        if set(raw) != expected:
            raise ValueError("RF Training request fields do not match its schema.")
        for field in ("run_id", "request_id", "collection_root", "collection_id", "model_id"):
            if not isinstance(raw[field], str) or not raw[field]:
                raise ValueError(f"RF Training request {field} is invalid.")
        for field in ("run_id", "request_id", "collection_id", "model_id"):
            safe = validate_relative_path(raw[field])
            if "/" in safe:
                raise ValueError(f"RF Training request {field} must be one path segment.")
        label = raw["model_label"]
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label.strip()) > 80
            or any(ord(character) < 32 for character in label)
        ):
            raise ValueError("RF Model display name must be 1 to 80 printable characters.")
        root = Path(raw["collection_root"])
        if not root.is_absolute():
            raise ValueError("RF Training request Collection root must be absolute.")
        config = FrozenTrainingConfig.from_worker_snapshot(raw["config"])
        if config.family != "rf":
            raise ValueError("RF Training request requires an RF configuration.")
        return cls(
            raw["run_id"],
            raw["request_id"],
            raw["collection_root"],
            raw["collection_id"],
            config,
            raw["model_id"],
            label.strip(),
        )


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise RfTrainingCancelled("RF Training cancelled before Model publication.")


def _toolbox_to_pipeline_features(
    values: dict[str, float], *, n_mfcc: int, include_deltas: bool
) -> dict[str, float]:
    mapped = {name: float(values[name]) for name in ROBUST_FEATURE_NAMES}
    prefixes = (("MFCC", "mfcc"), ("ΔMFCC", "d_mfcc"), ("ΔΔMFCC", "dd_mfcc"))
    for toolbox_prefix, canonical_prefix in prefixes:
        if canonical_prefix != "mfcc" and not include_deltas:
            continue
        for coefficient in range(1, n_mfcc + 1):
            mapped[f"{canonical_prefix}{coefficient}_mean"] = float(
                values[f"{toolbox_prefix} {coefficient:02d} mean"]
            )
            mapped[f"{canonical_prefix}{coefficient}_std"] = float(
                values[f"{toolbox_prefix} {coefficient:02d} std"]
            )
    return mapped


def _extract_features(
    path: Path,
    values: dict[str, object],
    *,
    source_sample_rate: int,
) -> dict[str, float]:
    sample_rate = int(values["feature_config.sample_rate_hz"])
    waveform = load_audio_file(str(path), sample_rate=None, mono=True)
    if waveform.ndim != 2 or waveform.shape[0] != 1 or waveform.shape[1] == 0:
        raise RfTrainingError(f"RF input must decode to nonempty mono audio: {path.name}")
    signal = np.asarray(waveform[0].numpy(), dtype=np.float32)
    if source_sample_rate != sample_rate:
        source_samples = int(signal.shape[0])
        signal = np.asarray(
            librosa.resample(
                signal,
                orig_sr=source_sample_rate,
                target_sr=sample_rate,
                res_type="soxr_hq",
                fix=True,
                scale=False,
            ),
            dtype=np.float32,
        )
        # Match the pipeline's post-resample slice_seconds(0, source duration).
        expected_samples = round(source_samples * sample_rate / source_sample_rate)
        signal = signal[:expected_samples]
    minimum = round(sample_rate * float(values["feature_config.min_duration_s"]))
    if signal.shape[0] < minimum:
        if not bool(values["feature_config.pad_short_segments"]):
            raise RfTrainingError(
                f"RF input is shorter than the configured minimum duration: {path.name}"
            )
        missing = minimum - int(signal.shape[0])
        signal = np.pad(signal, (missing // 2, missing - missing // 2), mode="constant").astype(
            np.float32,
            copy=False,
        )
    extracted = compute_rf_features(
        signal,
        sample_rate,
        0.0,
        float(signal.shape[0]) / sample_rate,
        low_hz=float(values["feature_config.fmin_hz"]),
        high_hz=float(values["feature_config.fmax_hz"]),
        n_fft=int(values["feature_config.n_fft"]),
        hop_length=int(values["feature_config.hop_length"]),
        n_mfcc=int(values["feature_config.n_mfcc"]),
        include_deltas=bool(values["feature_config.include_deltas"]),
        window="hann",
        center=True,
    )
    mapped = _toolbox_to_pipeline_features(
        extracted,
        n_mfcc=int(values["feature_config.n_mfcc"]),
        include_deltas=bool(values["feature_config.include_deltas"]),
    )
    expected = rf_feature_names(
        int(values["feature_config.n_mfcc"]),
        bool(values["feature_config.include_deltas"]),
    )
    if tuple(mapped) != expected:
        raise RfTrainingError("RF feature extractor order disagrees with its exact schema.")
    if any(not np.isfinite(value) for value in mapped.values()):
        invalid = ", ".join(name for name, value in mapped.items() if not np.isfinite(value))
        raise RfTrainingError(f"RF feature extraction produced non-finite values: {invalid}")
    return mapped


def _feature_table(
    artifact: DatasetArtifact,
    split: str,
    values: dict[str, object],
    cancelled: Callable[[], bool] | None,
    progress: Callable[[int, int, str], None] | None,
    completed: int,
    total: int,
) -> tuple[NDArray[np.float64], NDArray[np.int64], int]:
    rows: list[list[float]] = []
    labels: list[int] = []
    names = rf_feature_names(
        int(values["feature_config.n_mfcc"]),
        bool(values["feature_config.include_deltas"]),
    )
    split_rows = [row for row in artifact.snippets if row["split"] == split]
    for row in split_rows:
        _check_cancelled(cancelled)
        features = _extract_features(
            artifact.root / row["relative_path"],
            values,
            source_sample_rate=int(row["transform"]["sample_rate_hz"]),
        )
        rows.append([features[name] for name in names])
        labels.append(1 if row["label"] == "target" else 0)
        completed += 1
        if progress is not None:
            progress(
                1,
                min(54, 5 + round(49 * completed / max(1, total))),
                f"Extracted acoustic features · {completed} of {total}",
            )
    if not rows:
        raise RfTrainingError(f"RF Training requires a nonempty {split} Split.")
    matrix = np.asarray(rows, dtype=np.float64)
    target = np.asarray(labels, dtype=np.int64)
    if matrix.shape != (len(rows), len(names)) or not np.isfinite(matrix).all():
        raise RfTrainingError("RF feature matrix is non-finite or does not match its schema.")
    return matrix, target, completed


def train_rf_model(
    collection_root: Path,
    request: RfTrainingRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    measurement: Callable[[dict[str, Any]], None] | None = None,
    publication_allowed: Callable[[], bool] | None = None,
) -> ModelArtifact:
    """Extract, fit, validate, structurally reload, and publish one RF Model."""
    root = collection_root.resolve(strict=True)
    if root != Path(request.collection_root).resolve(strict=True):
        raise RfTrainingError("RF Training request Collection path changed.")
    safe_model_id = validate_relative_path(request.model_id)
    if "/" in safe_model_id:
        raise ValueError("Model ID must be one portable path segment.")
    alpaca = root / ".alpaca"
    if alpaca.is_symlink() or not alpaca.is_dir():
        raise RfTrainingError("Validated Collection metadata folder is missing or unsafe.")
    models_root = alpaca / "models"
    staging_root = alpaca / ".staging"
    for directory in (models_root, staging_root):
        if directory.is_symlink():
            raise RfTrainingError("App-owned Model storage cannot use symlinks.")
        directory.mkdir(exist_ok=True)
    final = models_root / safe_model_id
    if final.exists():
        raise FileExistsError(f"Model already exists: {safe_model_id}")
    stage_container = staging_root / f"{safe_model_id}-{request.request_id}"
    stage = stage_container / safe_model_id
    if stage_container.exists():
        raise FileExistsError("RF Model staging output already exists.")
    stage.mkdir(parents=True)
    try:
        _check_cancelled(cancelled)
        if progress is not None:
            progress(0, 3, "Validating immutable Dataset")
        artifact = load_dataset(root, request.config.dataset_id)
        dataset_digest = sha256_file(artifact.root / "dataset.json")
        dataset = TrainingDataset.from_artifact(artifact)
        verify_frozen_training_config(request.config, dataset, DeviceCapabilities.detect())
        values = dict(request.config.effective_values)
        feature_names = rf_feature_names(
            int(values["feature_config.n_mfcc"]),
            bool(values["feature_config.include_deltas"]),
        )
        total = len(artifact.snippets)
        x_train, y_train, completed = _feature_table(
            artifact, "train", values, cancelled, progress, 0, total
        )
        x_val, y_val, _completed = _feature_table(
            artifact, "val", values, cancelled, progress, completed, total
        )
        if (
            x_train.ndim != 2
            or x_val.ndim != 2
            or x_train.shape[1] != len(feature_names)
            or x_val.shape[1] != x_train.shape[1]
        ):
            raise RfTrainingError("RF train/val feature matrices do not share the exact schema.")
        if set(y_train.tolist()) != {0, 1}:
            raise RfTrainingError("RF training requires exactly noise and target examples.")
        _check_cancelled(cancelled)
        if progress is not None:
            progress(2, 58, "Fitting deterministic Random Forest")
        estimator = RandomForestClassifier(
            n_estimators=int(values["n_estimators"]),
            max_depth=None if values["max_depth"] is None else int(values["max_depth"]),
            min_samples_split=int(values["min_samples_split"]),
            min_samples_leaf=int(values["min_samples_leaf"]),
            max_features=values["max_features"],
            class_weight=values["class_weight"],
            n_jobs=int(values["n_jobs"]),
            random_state=int(values["random_state"]),
        )
        estimator.fit(x_train, y_train)
        class_order = tuple(int(value) for value in np.asarray(estimator.classes_).tolist())
        validate_rf_estimator_structure(
            estimator,
            feature_names=feature_names,
            probability_class_order=class_order,
        )
        _check_cancelled(cancelled)
        if progress is not None:
            progress(3, 78, "Validating target probabilities on val")
        evaluation = evaluate_binary_probabilities(
            y_val,
            estimator.predict_proba(x_val),
            classes=estimator.classes_,
            threshold=float(values["rf_threshold"]),
        )
        importances = [float(value) for value in estimator.feature_importances_]
        importance_rows = [
            {"name": name, "value": value}
            for name, value in zip(feature_names, importances, strict=True)
        ]
        if measurement is not None:
            for row in importance_rows:
                measurement(
                    {
                        "kind": "feature_importance",
                        "feature": row["name"],
                        "importance": row["value"],
                    }
                )
        binary = stage / "random_forest.joblib"
        joblib.dump(estimator, binary, compress=3)
        with binary.open("rb") as stream:
            os.fsync(stream.fileno())
        _check_cancelled(cancelled)
        reopened_dataset = load_dataset(root, artifact.dataset_id)
        if sha256_file(reopened_dataset.root / "dataset.json") != dataset_digest:
            raise RfTrainingError("Dataset manifest changed during RF Training.")
        split_counts = {
            split: {
                label: artifact.manifest["counts"][split][label] for label in ("noise", "target")
            }
            for split in ("train", "val")
        }
        probability_columns = [
            {
                "column": column,
                "class_index": class_index,
                "label": "target" if class_index == 1 else "noise",
            }
            for column, class_index in enumerate(class_order)
        ]
        manifest = {
            "schema_version": 1,
            "model_id": safe_model_id,
            "label": request.model_label,
            "family": "random_forest",
            "created_at": datetime.now(UTC).isoformat(),
            "run_id": request.run_id,
            "request_id": request.request_id,
            "dataset_id": artifact.dataset_id,
            "dataset_reference": f"datasets/{artifact.dataset_id}",
            "dataset_manifest_sha256": dataset_digest,
            "task": {
                "type": "binary_single_label",
                "class_to_index": {"noise": 0, "target": 1},
                "positive_class": "target",
                "num_classes": 2,
                "output": "target_probability",
            },
            "input": {
                "channel_policy": "mixdown_mono",
                "sample_rate_policy": ("resample_to_model_rate_librosa_soxr_hq_fix_unscaled"),
                "sample_rate_hz": int(values["feature_config.sample_rate_hz"]),
                "min_duration_s": float(values["feature_config.min_duration_s"]),
                "short_segment_policy": (
                    "center_zero_pad" if values["feature_config.pad_short_segments"] else "reject"
                ),
                "pad_mode": str(values["feature_config.pad_mode"]),
                "dtype": "float32",
                "sample_rounding": "nearest_integer_sample",
                "preprocessing_order": ["decode", "mixdown_mono", "resample", "minimum_pad"],
                "non_finite_policy": "reject",
            },
            "resolved_config": request.config.to_worker_snapshot(),
            "random_forest": {
                "estimator": {
                    "type": "sklearn.ensemble.RandomForestClassifier",
                    "hyperparameters": {
                        key: values[key]
                        for key in (
                            "n_estimators",
                            "max_depth",
                            "min_samples_split",
                            "min_samples_leaf",
                            "max_features",
                            "class_weight",
                            "n_jobs",
                            "random_state",
                        )
                    },
                    "classes": list(class_order),
                    "probability_columns": probability_columns,
                    "target_probability_column": evaluation.target_probability_column,
                    "n_features_in": int(estimator.n_features_in_),
                },
                "features": {
                    "family": RF_FEATURE_FAMILY,
                    "extractor_distribution": "bioacoustics-dl-toolbox",
                    "extractor_api": RF_EXTRACTOR_API,
                    "extractor_revision": RF_EXTRACTOR_REVISION,
                    "names": list(feature_names),
                    "config": {
                        key.removeprefix("feature_config."): values[key]
                        for key in values
                        if key.startswith("feature_config.")
                    },
                    "window": "hann",
                    "center": True,
                    "output_dtype": "float64",
                },
                "decision_policy": {
                    "positive_class": "target",
                    "threshold": float(values["rf_threshold"]),
                    "scope": "held_out_validation_and_saved_policy",
                },
            },
            "results": {
                "split_counts": split_counts,
                "metrics": evaluation.metrics,
                "feature_importances": importance_rows,
            },
            "artifact": {
                "path": binary.name,
                "size_bytes": binary.stat().st_size,
                "sha256": sha256_file(binary),
                "format": "scikit-learn-joblib",
                "format_version": 1,
            },
            "provenance": {
                "trainer": {"distribution": "alpaca-desktop", "version": version("alpaca-desktop")},
                "toolbox": {
                    "distribution": "bioacoustics-dl-toolbox",
                    "version": version("bioacoustics-dl-toolbox"),
                    "revision": MODEL_TOOLBOX_REVISION,
                },
                "scikit_learn_version": version("scikit-learn"),
                "joblib_version": version("joblib"),
                "librosa_version": version("librosa"),
                "scientific_reference": MODEL_SCIENTIFIC_REFERENCE,
            },
        }
        if progress is not None:
            progress(4, 91, "Verifying staged RF Model")
        write_model_manifest(stage / "model.json", manifest)
        structurally_reload_rf_directory(stage, safe_model_id)
        _check_cancelled(cancelled)
        if progress is not None:
            progress(4, 98, "Publishing verified RF Model")
        publish_model_directory(stage, final, publication_allowed)
        return load_model(root, safe_model_id)
    except InterruptedError as exc:
        raise RfTrainingCancelled(str(exc) or "RF Training cancelled before publication.") from exc
    finally:
        if stage_container.exists():
            shutil.rmtree(stage_container)
