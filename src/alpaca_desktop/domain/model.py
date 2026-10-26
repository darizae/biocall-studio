"""Pure validation for immutable, portable Trainer Model manifests."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from alpaca_desktop.domain.paths import validate_relative_path
from alpaca_desktop.domain.rf_training import rf_feature_names

MODEL_SCHEMA_VERSION = 1
MODEL_FORMAT = "bioacoustics-dl-toolbox-pytorch"
MODEL_FORMAT_VERSION = 2
MODEL_TOOLBOX_VERSION = "0.2.0"
MODEL_TOOLBOX_REVISION = "e478ca5156a5d1018d0a7a61486bc85fe7c1e92d"
MODEL_SCIENTIFIC_REFERENCE = "alpaca-pipelines@91af5287dc18313f88902dc9696e8756274736b3"
_METRIC_NAMES = frozenset({"accuracy", "precision", "recall", "f1", "roc_auc"})


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model {label} must be nonempty text.")
    return value


def _portable_segment(value: object, label: str) -> str:
    safe = validate_relative_path(_text(value, label))
    if "/" in safe:
        raise ValueError(f"Model {label} must be one portable path segment.")
    return safe


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Model {label} must be finite numeric data.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Model {label} must be finite numeric data.")
    return number


def _class_mapping(value: object) -> dict[str, int]:
    if value != {"noise": 0, "target": 1}:
        raise ValueError("Model task requires the exact two-class noise/target mapping.")
    return dict(value)


def _validate_history(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"train", "val"}:
        raise ValueError("Model results history must contain train and val series.")
    for phase in ("train", "val"):
        rows = value[phase]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Model results require a nonempty {phase} history.")
        previous = 0
        for row in rows:
            if not isinstance(row, dict) or "epoch" not in row or "loss" not in row:
                raise ValueError(f"Model {phase} history row is invalid.")
            epoch = row["epoch"]
            if type(epoch) is not int or epoch <= previous:
                raise ValueError(f"Model {phase} epochs must be positive and increasing.")
            _finite(row["loss"], f"{phase} loss")
            for name, metric in row.items():
                if name not in {"epoch", "loss"}:
                    _finite(metric, f"{phase} {name}")
            previous = epoch


def _validate_metrics(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _METRIC_NAMES:
        raise ValueError("Model metrics must contain the complete validation metric set.")
    for name, metric in value.items():
        if not isinstance(metric, dict) or set(metric) != {"value", "reason"}:
            raise ValueError(f"Model metric {name} must contain value and reason.")
        number = metric["value"]
        reason = metric["reason"]
        if number is None:
            _text(reason, f"undefined {name} reason")
        else:
            _finite(number, name)
            if reason is not None:
                raise ValueError(f"Defined Model metric {name} cannot have an undefined reason.")


def _validate_split_counts(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"train", "val"}:
        raise ValueError("Model results require train and val counts.")
    for split in ("train", "val"):
        if (
            not isinstance(value[split], dict)
            or set(value[split]) != {"noise", "target"}
            or any(
                type(value[split][label]) is not int or value[split][label] <= 0
                for label in ("noise", "target")
            )
        ):
            raise ValueError("Model results require positive two-class Split counts.")


def _validate_rf_manifest(raw: dict[str, Any], dataset_id: str) -> None:
    input_spec = raw["input"]
    if not isinstance(input_spec, dict) or set(input_spec) != {
        "channel_policy",
        "sample_rate_policy",
        "sample_rate_hz",
        "min_duration_s",
        "short_segment_policy",
        "pad_mode",
        "dtype",
        "sample_rounding",
        "preprocessing_order",
        "non_finite_policy",
    }:
        raise ValueError("RF Model input declaration is invalid.")
    if (
        input_spec["channel_policy"] != "mixdown_mono"
        or input_spec["sample_rate_policy"] != "resample_to_model_rate_librosa_soxr_hq_fix_unscaled"
        or type(input_spec["sample_rate_hz"]) is not int
        or input_spec["sample_rate_hz"] <= 0
        or isinstance(input_spec["min_duration_s"], bool)
        or not isinstance(input_spec["min_duration_s"], (int, float))
        or not math.isfinite(float(input_spec["min_duration_s"]))
        or input_spec["min_duration_s"] <= 0
        or input_spec["short_segment_policy"] not in {"center_zero_pad", "reject"}
        or input_spec["pad_mode"] != "constant"
        or input_spec["dtype"] != "float32"
        or input_spec["sample_rounding"] != "nearest_integer_sample"
        or input_spec["preprocessing_order"]
        != ["decode", "mixdown_mono", "resample", "minimum_pad"]
        or input_spec["non_finite_policy"] != "reject"
    ):
        raise ValueError("RF Model preprocessing policy is invalid.")

    resolved = raw["resolved_config"]
    if (
        not isinstance(resolved, dict)
        or resolved.get("schema_version") != 1
        or resolved.get("family") != "rf"
        or resolved.get("dataset_id") != dataset_id
        or resolved.get("class_mapping") != {"noise": 0, "target": 1}
        or not isinstance(resolved.get("effective_values"), dict)
    ):
        raise ValueError("RF Model resolved configuration is invalid.")
    effective = resolved["effective_values"]
    if (
        effective.get("feature_config.sample_rate_hz") != input_spec["sample_rate_hz"]
        or effective.get("feature_config.min_duration_s") != input_spec["min_duration_s"]
        or effective.get("feature_config.pad_mode") != input_spec["pad_mode"]
        or ("center_zero_pad" if effective.get("feature_config.pad_short_segments") else "reject")
        != input_spec["short_segment_policy"]
    ):
        raise ValueError("RF Model resolved configuration disagrees with preprocessing metadata.")

    rf = raw["random_forest"]
    if not isinstance(rf, dict) or set(rf) != {"estimator", "features", "decision_policy"}:
        raise ValueError("RF Model family declaration is invalid.")
    features = rf["features"]
    if not isinstance(features, dict) or set(features) != {
        "family",
        "extractor_distribution",
        "extractor_api",
        "extractor_revision",
        "names",
        "config",
        "window",
        "center",
        "output_dtype",
    }:
        raise ValueError("RF Model feature declaration is invalid.")
    config = features["config"]
    expected_config_keys = {
        "sample_rate_hz",
        "min_duration_s",
        "pad_short_segments",
        "pad_mode",
        "n_fft",
        "hop_length",
        "n_mfcc",
        "include_deltas",
        "fmin_hz",
        "fmax_hz",
    }
    if not isinstance(config, dict) or set(config) != expected_config_keys:
        raise ValueError("RF Model feature configuration is incomplete.")
    if (
        type(config["sample_rate_hz"]) is not int
        or config["sample_rate_hz"] <= 0
        or isinstance(config["min_duration_s"], bool)
        or not isinstance(config["min_duration_s"], (int, float))
        or not math.isfinite(float(config["min_duration_s"]))
        or config["min_duration_s"] <= 0
        or type(config["pad_short_segments"]) is not bool
        or config["pad_mode"] != "constant"
        or type(config["n_fft"]) is not int
        or config["n_fft"] <= 0
        or type(config["hop_length"]) is not int
        or config["hop_length"] <= 0
        or type(config["n_mfcc"]) is not int
        or config["n_mfcc"] <= 0
        or type(config["include_deltas"]) is not bool
        or isinstance(config["fmin_hz"], bool)
        or not isinstance(config["fmin_hz"], (int, float))
        or not math.isfinite(float(config["fmin_hz"]))
        or isinstance(config["fmax_hz"], bool)
        or not isinstance(config["fmax_hz"], (int, float))
        or not math.isfinite(float(config["fmax_hz"]))
        or not 0 <= config["fmin_hz"] < config["fmax_hz"] <= config["sample_rate_hz"] / 2
    ):
        raise ValueError("RF Model feature configuration is invalid.")
    expected_names = rf_feature_names(config["n_mfcc"], config["include_deltas"])
    if (
        not isinstance(features["names"], list)
        or features["family"] != "robust-mfcc-v1"
        or features["extractor_distribution"] != "bioacoustics-dl-toolbox"
        or features["extractor_api"] != "bioacoustics_dl_toolbox.rf.compute_rf_features"
        or features["extractor_revision"] != MODEL_TOOLBOX_REVISION
        or tuple(features["names"]) != expected_names
        or features["window"] != "hann"
        or features["center"] is not True
        or features["output_dtype"] != "float64"
        or any(effective.get(f"feature_config.{key}") != value for key, value in config.items())
    ):
        raise ValueError("RF Model ordered feature schema or extractor revision is incompatible.")

    estimator = rf["estimator"]
    if not isinstance(estimator, dict) or set(estimator) != {
        "type",
        "hyperparameters",
        "classes",
        "probability_columns",
        "target_probability_column",
        "n_features_in",
    }:
        raise ValueError("RF Model estimator declaration is invalid.")
    classes = estimator["classes"]
    if (
        estimator["type"] != "sklearn.ensemble.RandomForestClassifier"
        or not isinstance(classes, list)
        or len(classes) != 2
        or any(type(class_index) is not int for class_index in classes)
        or set(classes) != {0, 1}
        or type(estimator["n_features_in"]) is not int
        or estimator["n_features_in"] != len(expected_names)
        or not isinstance(estimator["hyperparameters"], dict)
    ):
        raise ValueError("RF Model estimator class or feature shape is invalid.")
    columns = estimator["probability_columns"]
    expected_columns = [
        {
            "column": column,
            "class_index": class_index,
            "label": "target" if class_index == 1 else "noise",
        }
        for column, class_index in enumerate(classes)
    ]
    target_column = classes.index(1)
    if (
        columns != expected_columns
        or type(estimator["target_probability_column"]) is not int
        or estimator["target_probability_column"] != target_column
    ):
        raise ValueError("RF Model probability class order is invalid.")
    policy = rf["decision_policy"]
    if (
        not isinstance(policy, dict)
        or set(policy) != {"positive_class", "threshold", "scope"}
        or policy["positive_class"] != "target"
        or policy["scope"] != "held_out_validation_and_saved_policy"
        or isinstance(policy["threshold"], bool)
        or not isinstance(policy["threshold"], (int, float))
        or not math.isfinite(float(policy["threshold"]))
        or not 0 <= float(policy["threshold"]) <= 1
        or effective.get("rf_threshold") != policy["threshold"]
    ):
        raise ValueError("RF Model decision threshold policy is invalid.")

    results = raw["results"]
    if not isinstance(results, dict) or set(results) != {
        "split_counts",
        "metrics",
        "feature_importances",
    }:
        raise ValueError("RF Model results declaration is invalid.")
    _validate_split_counts(results["split_counts"])
    _validate_metrics(results["metrics"])
    importance_rows = results["feature_importances"]
    if (
        not isinstance(importance_rows, list)
        or len(importance_rows) != len(expected_names)
        or any(
            not isinstance(row, dict)
            or set(row) != {"name", "value"}
            or row["name"] != expected_names[index]
            or isinstance(row["value"], bool)
            or not isinstance(row["value"], (int, float))
            or not math.isfinite(float(row["value"]))
            or row["value"] < 0
            for index, row in enumerate(importance_rows)
        )
    ):
        raise ValueError("RF Model feature importances do not match ordered feature metadata.")

    artifact = raw["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "path",
        "size_bytes",
        "sha256",
        "format",
        "format_version",
    }:
        raise ValueError("RF Model binary artifact declaration is invalid.")
    artifact_path = validate_relative_path(_text(artifact["path"], "artifact path"))
    digest = artifact["sha256"]
    if (
        "/" in artifact_path
        or artifact_path != "random_forest.joblib"
        or type(artifact["size_bytes"]) is not int
        or artifact["size_bytes"] <= 0
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or artifact["format"] != "scikit-learn-joblib"
        or artifact["format_version"] != 1
    ):
        raise ValueError("RF Model binary size, digest, path, or format is invalid.")

    provenance = raw["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "trainer",
        "toolbox",
        "scikit_learn_version",
        "joblib_version",
        "librosa_version",
        "scientific_reference",
    }:
        raise ValueError("RF Model provenance is invalid.")
    for owner in ("trainer", "toolbox"):
        item = provenance[owner]
        if (
            not isinstance(item, dict)
            or item.get("distribution")
            != ("alpaca-desktop" if owner == "trainer" else "bioacoustics-dl-toolbox")
            or not isinstance(item.get("version"), str)
            or not item["version"]
        ):
            raise ValueError("RF Model package provenance is invalid.")
    if (
        provenance["toolbox"].get("version") != MODEL_TOOLBOX_VERSION
        or provenance["toolbox"].get("revision") != MODEL_TOOLBOX_REVISION
    ):
        raise ValueError("Model toolbox version or revision provenance is incompatible.")
    _text(provenance["scikit_learn_version"], "scikit-learn version")
    _text(provenance["joblib_version"], "joblib version")
    _text(provenance["librosa_version"], "librosa version")
    if provenance["scientific_reference"] != MODEL_SCIENTIFIC_REFERENCE:
        raise ValueError("RF Model scientific reference provenance is incompatible.")


def validate_model_manifest(raw: object) -> dict[str, Any]:
    """Validate the canonical family-specific Model schema without deserializing bytes."""
    if not isinstance(raw, dict) or raw.get("schema_version") != MODEL_SCHEMA_VERSION:
        raise ValueError("Unsupported Model manifest schema.")
    family = raw.get("family") if isinstance(raw, dict) else None
    if family not in ("cnn", "random_forest"):
        raise ValueError("Model family must be cnn or random_forest.")
    family_key = str(family)
    required = {
        "schema_version",
        "model_id",
        "label",
        "family",
        "created_at",
        "run_id",
        "request_id",
        "dataset_id",
        "dataset_reference",
        "dataset_manifest_sha256",
        "task",
        "input",
        "resolved_config",
        family_key,
        "results",
        "artifact",
        "provenance",
    }
    if set(raw) != required:
        raise ValueError("Model manifest fields do not match its family schema.")
    _portable_segment(raw["model_id"], "ID")
    label = _text(raw["label"], "label")
    if len(label) > 80 or any(ord(character) < 32 for character in label):
        raise ValueError("Model label must be at most 80 printable characters.")
    try:
        datetime.fromisoformat(_text(raw["created_at"], "creation time"))
    except ValueError as exc:
        raise ValueError("Model creation time is invalid.") from exc
    _portable_segment(raw["run_id"], "Run ID")
    _portable_segment(raw["request_id"], "request ID")
    dataset_id = _portable_segment(raw["dataset_id"], "Dataset ID")
    reference = validate_relative_path(_text(raw["dataset_reference"], "Dataset reference"))
    if reference != f"datasets/{dataset_id}":
        raise ValueError("Model Dataset reference must be the canonical root-relative reference.")
    dataset_digest = raw["dataset_manifest_sha256"]
    if (
        not isinstance(dataset_digest, str)
        or len(dataset_digest) != 64
        or any(character not in "0123456789abcdef" for character in dataset_digest)
    ):
        raise ValueError("Model Dataset manifest digest is invalid.")

    task = raw["task"]
    if not isinstance(task, dict) or set(task) != {
        "type",
        "class_to_index",
        "positive_class",
        "num_classes",
        "output",
    }:
        raise ValueError("Model task declaration is invalid.")
    expected_output = "categorical_logits" if family == "cnn" else "target_probability"
    if (
        task["type"] != "binary_single_label"
        or task["positive_class"] != "target"
        or task["num_classes"] != 2
        or task["output"] != expected_output
    ):
        raise ValueError("Model task must be a two-class binary single-label task.")
    _class_mapping(task["class_to_index"])

    if family == "random_forest":
        _validate_rf_manifest(raw, dataset_id)
        return raw

    input_spec = raw["input"]
    if not isinstance(input_spec, dict) or set(input_spec) != {
        "channel_policy",
        "sample_rate_policy",
        "sample_rate_hz",
        "window_duration_ms",
        "window_length_samples",
        "sequence_length_frames",
        "time_unit",
        "sample_rounding",
    }:
        raise ValueError("Model input declaration is invalid.")
    if (
        input_spec["channel_policy"] != "mixdown_mono"
        or input_spec["sample_rate_policy"] != "resample_to_model_rate"
        or input_spec["time_unit"] != "milliseconds"
        or input_spec["sample_rounding"] != "nearest_integer_sample"
        or any(
            type(input_spec[name]) is not int or input_spec[name] <= 0
            for name in (
                "sample_rate_hz",
                "window_duration_ms",
                "window_length_samples",
                "sequence_length_frames",
            )
        )
        or input_spec["window_length_samples"]
        != round(input_spec["window_duration_ms"] * input_spec["sample_rate_hz"] / 1_000)
    ):
        raise ValueError("Model input shape or preprocessing policy is invalid.")

    resolved = raw["resolved_config"]
    if (
        not isinstance(resolved, dict)
        or resolved.get("schema_version") != 1
        or resolved.get("family") != "cnn"
        or resolved.get("dataset_id") != dataset_id
        or not isinstance(resolved.get("requested_values"), dict)
        or not isinstance(resolved.get("effective_values"), dict)
    ):
        raise ValueError("Model resolved configuration is invalid.")
    _class_mapping(resolved.get("class_mapping"))
    if (
        resolved["effective_values"].get("classifier.num_classes") != 2
        or resolved["effective_values"].get("sequence_length_ms")
        != input_spec["window_duration_ms"]
        or resolved["effective_values"].get("spectrogram.sample_rate")
        != input_spec["sample_rate_hz"]
    ):
        raise ValueError("Model resolved configuration disagrees with its input or binary task.")

    cnn = raw["cnn"]
    if not isinstance(cnn, dict) or set(cnn) != {"architecture", "transforms", "training"}:
        raise ValueError("Model CNN declaration is invalid.")
    architecture = cnn["architecture"]
    if (
        not isinstance(architecture, dict)
        or set(architecture) != {"encoder", "classifier"}
        or not isinstance(architecture["encoder"], dict)
        or not isinstance(architecture["classifier"], dict)
        or architecture["classifier"].get("num_classes") != 2
    ):
        raise ValueError("Model CNN architecture must declare a two-class classifier.")
    transforms = cnn["transforms"]
    if (
        not isinstance(transforms, dict)
        or set(transforms)
        != {"spectrogram", "normalization", "augmentation", "preprocessing_order"}
        or not isinstance(transforms["spectrogram"], dict)
        or not isinstance(transforms["normalization"], dict)
        or transforms["spectrogram"].get("sample_rate") != input_spec["sample_rate_hz"]
        or not isinstance(transforms["preprocessing_order"], list)
        or not transforms["preprocessing_order"]
    ):
        raise ValueError("Model CNN transform declaration is invalid.")
    augmentation = transforms["augmentation"]
    if (
        not isinstance(augmentation, dict)
        or set(augmentation) != {"training", "validation"}
        or not isinstance(augmentation["training"], dict)
        or augmentation.get("validation") != {"enabled": False}
    ):
        raise ValueError("Model augmentation must separate training from validation.")
    training = cnn["training"]
    if (
        not isinstance(training, dict)
        or set(training) != {"seed", "device", "optimizer", "objective"}
        or type(training["seed"]) is not int
        or training["seed"] < 0
        or training["device"] not in {"cpu", "cuda"}
        or training["objective"] != "CrossEntropyLoss"
        or not isinstance(training["optimizer"], dict)
    ):
        raise ValueError("Model CNN training provenance is invalid.")

    results = raw["results"]
    if not isinstance(results, dict) or set(results) != {
        "split_counts",
        "history",
        "metrics",
        "selected_epoch",
    }:
        raise ValueError("Model results declaration is invalid.")
    _validate_split_counts(results["split_counts"])
    _validate_history(results["history"])
    _validate_metrics(results["metrics"])
    if type(results["selected_epoch"]) is not int or results["selected_epoch"] < 1:
        raise ValueError("Model selected epoch is invalid.")

    artifact = raw["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "path",
        "size_bytes",
        "sha256",
        "format",
        "format_version",
    }:
        raise ValueError("Model binary artifact declaration is invalid.")
    artifact_path = validate_relative_path(_text(artifact["path"], "artifact path"))
    if "/" in artifact_path or artifact_path != "model.pt":
        raise ValueError("Model artifact path must be the contained model.pt file.")
    digest = artifact["sha256"]
    if (
        type(artifact["size_bytes"]) is not int
        or artifact["size_bytes"] <= 0
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or artifact["format"] != MODEL_FORMAT
        or artifact["format_version"] != MODEL_FORMAT_VERSION
    ):
        raise ValueError("Model binary size, digest, or format is invalid.")

    provenance = raw["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "trainer",
        "toolbox",
        "torch_version",
        "scientific_reference",
    }:
        raise ValueError("Model provenance is invalid.")
    for owner in ("trainer", "toolbox"):
        item = provenance[owner]
        if (
            not isinstance(item, dict)
            or item.get("distribution")
            != ("alpaca-desktop" if owner == "trainer" else "bioacoustics-dl-toolbox")
            or not isinstance(item.get("version"), str)
            or not item["version"]
        ):
            raise ValueError("Model package provenance is invalid.")
    revision = provenance["toolbox"].get("revision")
    if (
        provenance["toolbox"]["version"] != MODEL_TOOLBOX_VERSION
        or revision != MODEL_TOOLBOX_REVISION
    ):
        raise ValueError("Model toolbox version or revision provenance is incompatible.")
    _text(provenance["torch_version"], "torch version")
    if provenance["scientific_reference"] != MODEL_SCIENTIFIC_REFERENCE:
        raise ValueError("CNN Model scientific reference provenance is incompatible.")
    return raw
