"""Pure validation for immutable, portable Trainer Model manifests."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from alpaca_desktop.domain.paths import validate_relative_path

MODEL_SCHEMA_VERSION = 1
MODEL_FORMAT = "bioacoustics-dl-toolbox-pytorch"
MODEL_FORMAT_VERSION = 2
MODEL_TOOLBOX_VERSION = "0.1.1"
MODEL_TOOLBOX_REVISION = "8e2e0528d4ce718005e194d426cde6e62fda0909"
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
        raise ValueError("Model metrics must contain the complete CNN validation metric set.")
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


def validate_model_manifest(raw: object) -> dict[str, Any]:
    """Validate the only supported 05b CNN Model schema without deserializing bytes."""
    if not isinstance(raw, dict) or raw.get("schema_version") != MODEL_SCHEMA_VERSION:
        raise ValueError("Unsupported Model manifest schema.")
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
        "cnn",
        "results",
        "artifact",
        "provenance",
    }
    if set(raw) != required:
        raise ValueError("Model manifest fields do not match its schema.")
    _portable_segment(raw["model_id"], "ID")
    label = _text(raw["label"], "label")
    if len(label) > 80 or any(ord(character) < 32 for character in label):
        raise ValueError("Model label must be at most 80 printable characters.")
    if raw["family"] != "cnn":
        raise ValueError("Model family must be cnn for this manifest version.")
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
    if (
        task["type"] != "binary_single_label"
        or task["positive_class"] != "target"
        or task["num_classes"] != 2
        or task["output"] != "categorical_logits"
    ):
        raise ValueError("Model task must be a categorical two-class binary single-label task.")
    _class_mapping(task["class_to_index"])

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
    counts = results["split_counts"]
    if not isinstance(counts, dict) or set(counts) != {"train", "val"}:
        raise ValueError("Model results require train and val counts.")
    for split in ("train", "val"):
        if (
            not isinstance(counts[split], dict)
            or set(counts[split]) != {"noise", "target"}
            or any(
                type(counts[split][label]) is not int or counts[split][label] <= 0
                for label in ("noise", "target")
            )
        ):
            raise ValueError("Model results require positive two-class Split counts.")
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
    _text(provenance["scientific_reference"], "scientific reference")
    return raw
