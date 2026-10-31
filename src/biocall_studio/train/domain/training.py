"""Qt-free training configuration catalog, drafts, validation, and frozen handoff."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class FieldDefinition:
    family: str
    section: str
    key: str
    label: str
    kind: str
    default: object
    choices: tuple[object, ...]
    mode: str
    help: str
    ui_tier: str
    recommended_starting_value: object
    recommendation_basis: str

    @property
    def wiki_anchor(self) -> str:
        anchor = self.key.replace(".", "-").replace("_", "-")
        return f"training-configuration#{anchor}"


def _catalog_path() -> Path:
    development = (
        Path(__file__).resolve().parents[4] / "docs/science/TRAINING_CONFIGURATION_FIELDS.json"
    )
    if development.is_file():
        return development
    packaged = resources.files("biocall_studio.train.data").joinpath(
        "TRAINING_CONFIGURATION_FIELDS.json"
    )
    return Path(str(packaged))


@lru_cache(maxsize=1)
def field_definitions() -> tuple[FieldDefinition, ...]:
    with _catalog_path().open(encoding="utf-8") as stream:
        raw = json.load(stream)
    if not isinstance(raw, list):
        raise ValueError("Training configuration field catalog must be a list.")
    fields: list[FieldDefinition] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Training configuration field entry must be an object.")
        fields.append(
            FieldDefinition(
                family=str(item["family"]),
                section=str(item["section"]),
                key=str(item["key"]),
                label=str(item["label"]),
                kind=str(item["kind"]),
                default=item["default"],
                choices=tuple(item["choices"]),
                mode=str(item["mode"]),
                help=str(item["help"]),
                ui_tier=str(item["ui_tier"]),
                recommended_starting_value=item["recommended_starting_value"],
                recommendation_basis=str(item["recommendation_basis"]),
            )
        )
    keys = [(field.family, field.key) for field in fields]
    if len(keys) != len(set(keys)):
        raise ValueError("Training configuration field keys must be unique per family.")
    return tuple(fields)


def fields_for_family(family: str) -> tuple[FieldDefinition, ...]:
    normalized = _normalize_family(family)
    wanted = normalized.upper()
    return tuple(field for field in field_definitions() if field.family in {"Common", wanted})


def _normalize_family(family: str) -> str:
    normalized = family.strip().lower() if isinstance(family, str) else ""
    if normalized not in {"cnn", "rf"}:
        raise ValueError("Training family must be 'cnn' or 'rf'.")
    return normalized


@dataclass(frozen=True)
class DeviceCapabilities:
    cuda: bool = False
    mps: bool = False
    cpu_count: int = max(1, os.cpu_count() or 1)

    @classmethod
    def detect(cls) -> DeviceCapabilities:
        try:
            import torch

            cuda = bool(torch.cuda.is_available())
        except (ImportError, RuntimeError):
            cuda = False
        # The inspected pipeline executor currently resolves only CUDA or CPU.
        return cls(cuda=cuda, mps=False)


@dataclass(frozen=True)
class TrainingDataset:
    dataset_id: str
    labels: tuple[str, ...]
    split_counts: Mapping[str, Mapping[str, int]]

    def __post_init__(self) -> None:
        if not self.dataset_id:
            raise ValueError("Select a published Dataset before training.")
        if set(self.labels) != {"target", "noise"} or len(self.labels) != 2:
            raise ValueError("Training requires exactly the binary target/noise labels.")
        for split in ("train", "val"):
            counts = self.split_counts.get(split)
            if not isinstance(counts, Mapping) or any(
                type(counts.get(label)) is not int or counts[label] <= 0
                for label in ("target", "noise")
            ):
                raise ValueError(
                    f"Training requires target and noise examples in the {split} Split."
                )

    @classmethod
    def from_artifact(cls, artifact) -> TrainingDataset:
        labels = tuple(sorted({str(row["label"]) for row in artifact.snippets}))
        counts = artifact.manifest["counts"]
        return cls(
            dataset_id=artifact.dataset_id,
            labels=labels,
            split_counts={
                split: {label: counts[split][label] for label in ("target", "noise")}
                for split in ("train", "val")
            },
        )


class TrainingValidationError(ValueError):
    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        super().__init__("Training configuration is invalid: " + "; ".join(errors.values()))


class TrainingDraft:
    """Mutable presentation draft; resolving produces a separate immutable snapshot."""

    def __init__(self, family: str, values: Mapping[str, object]):
        self.family = _normalize_family(family)
        self._fields = {field.key: field for field in fields_for_family(self.family)}
        editable = {key for key, field in self._fields.items() if field.mode == "editable"}
        if set(values) != editable:
            missing = sorted(editable - set(values))
            unknown = sorted(set(values) - editable)
            detail = []
            if missing:
                detail.append("missing: " + ", ".join(missing))
            if unknown:
                detail.append("unknown/noneditable: " + ", ".join(unknown))
            raise ValueError("Preset fields do not match the catalog (" + "; ".join(detail) + ").")
        self._values = dict(values)
        for key, value in self._values.items():
            error = _type_error(self._fields[key], value)
            if error:
                raise ValueError(f"{key}: {error}")

    @classmethod
    def defaults(cls, family: str) -> TrainingDraft:
        return cls(
            family,
            {
                field.key: field.default
                for field in fields_for_family(family)
                if field.mode == "editable"
            },
        )

    def copy(self) -> TrainingDraft:
        return TrainingDraft(self.family, self._values)

    @property
    def values(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self._values))

    def value(self, key: str) -> object:
        field = self._fields.get(key)
        if field is None:
            raise KeyError(key)
        return self._values[key] if field.mode == "editable" else field.default

    def set(self, key: str, value: object) -> None:
        field = self._fields.get(key)
        if field is None or field.mode != "editable":
            raise ValueError(f"Training field is unknown or read-only: {key}")
        error = _type_error(field, value)
        if error:
            raise ValueError(f"{key}: {error}")
        self._values[key] = value

    def reset(self, key: str) -> None:
        field = self._fields.get(key)
        if field is None or field.mode != "editable":
            raise ValueError(f"Training field is unknown or read-only: {key}")
        self._values[key] = field.default

    def reset_details(self) -> None:
        for field in self._fields.values():
            if field.mode == "editable" and field.ui_tier == "details":
                self._values[field.key] = field.default

    def modified_keys(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self._values.items() if value != self._fields[key].default
        )

    def validate(
        self,
        dataset: TrainingDataset,
        capabilities: DeviceCapabilities,
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        try:
            TrainingDataset(dataset.dataset_id, dataset.labels, dataset.split_counts)
        except ValueError as exc:
            errors["dataset"] = str(exc)
        for key, value in self._values.items():
            error = _type_error(self._fields[key], value)
            if error:
                errors[key] = error
        if errors:
            return errors
        _validate_common(self._values, errors)
        if self.family == "cnn":
            _validate_cnn(self._values, capabilities, errors)
        else:
            _validate_rf(self._values, capabilities, errors)
        return errors


def _type_error(field: FieldDefinition, value: object) -> str | None:
    if field.kind in {"int", "nullable_int"}:
        if value is None and field.kind == "nullable_int":
            return None
        if type(value) is not int:
            return "Enter a whole number."
    elif field.kind == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "Enter a numeric value."
        if not math.isfinite(float(value)):
            return "Enter a finite numeric value."
    elif field.kind == "bool":
        if type(value) is not bool:
            return "Choose on or off."
    elif field.kind == "text":
        if not isinstance(value, str):
            return "Enter text."
    elif field.kind == "select":
        if value not in field.choices:
            return "Choose one of the supported values."
    elif field.kind == "readonly":
        return None
    else:
        return f"Unsupported catalog field kind: {field.kind}"
    return None


def _bounded(
    values: Mapping[str, object],
    errors: dict[str, str],
    key: str,
    minimum: float,
    maximum: float,
    message: str,
) -> None:
    value = values[key]
    if value is None or not minimum <= float(value) <= maximum:
        errors[key] = message


def _validate_common(values: Mapping[str, object], errors: dict[str, str]) -> None:
    run_name = str(values["run_name"])
    if len(run_name) > 80 or any(ord(character) < 32 for character in run_name):
        errors["run_name"] = "Run name must be at most 80 printable characters."


def _validate_cnn(
    values: Mapping[str, object],
    capabilities: DeviceCapabilities,
    errors: dict[str, str],
) -> None:
    ranges = {
        "sequence_length_ms": (1, 600_000, "Sequence length must be positive milliseconds."),
        "training.max_epochs": (1, 100_000, "Maximum epochs must be at least 1."),
        "training.batch_size": (1, 65_536, "Batch size must be at least 1."),
        "training.learning_rate": (
            1e-12,
            1.0,
            "Learning rate must be greater than 0 and at most 1.",
        ),
        "spectrogram.sample_rate": (1, 768_000, "Sampling rate must be positive."),
        "spectrogram.preemphasis": (
            0,
            0.999999,
            "Pre-emphasis must be from 0 up to, but not including, 1.",
        ),
        "spectrogram.n_fft": (2, 1_048_576, "FFT window must be at least 2 samples."),
        "spectrogram.hop_length": (1, 1_048_576, "FFT hop must be positive."),
        "spectrogram.n_freq_bins": (2, 524_289, "Frequency bins must be at least 2."),
        "augmentation.amplitude_increase_db": (0, 120, "Maximum gain must be from 0 to 120 dB."),
        "augmentation.amplitude_decrease_db": (
            -120,
            0,
            "Maximum attenuation must be from −120 to 0 dB.",
        ),
        "augmentation.time_stretch_from": (0.01, 100, "Time stretch minimum must be positive."),
        "augmentation.time_stretch_to": (0.01, 100, "Time stretch maximum must be positive."),
        "augmentation.pitch_shift_from": (0.01, 100, "Pitch shift minimum must be positive."),
        "augmentation.pitch_shift_to": (0.01, 100, "Pitch shift maximum must be positive."),
        "training.num_workers": (0, 256, "Data-loader workers must be from 0 to 256."),
        "training.beta1": (0, 0.999999, "Adam β1 must be from 0 up to, but not including, 1."),
        "training.lr_patience_epochs": (0, 100_000, "LR scheduler patience cannot be negative."),
        "training.lr_decay_factor": (
            1e-12,
            0.999999,
            "LR decay factor must be greater than 0 and less than 1.",
        ),
        "training.early_stopping_patience_epochs": (
            1,
            100_000,
            "Early-stopping patience must be at least 1.",
        ),
        "training.epochs_per_eval": (1, 100_000, "Evaluation cadence must be at least 1 epoch."),
    }
    for key, (minimum, maximum, message) in ranges.items():
        _bounded(values, errors, key, minimum, maximum, message)
    if float(values["spectrogram.hop_length"]) > float(values["spectrogram.n_fft"]):
        errors["spectrogram.hop_length"] = "FFT hop must not exceed the FFT window."
    nyquist = float(values["spectrogram.sample_rate"]) / 2
    f_min = float(values["spectrogram.f_min"])
    f_max = float(values["spectrogram.f_max"])
    if f_min < 0:
        errors["spectrogram.f_min"] = "Minimum frequency cannot be negative."
    if f_max <= f_min or f_max > nyquist:
        errors["spectrogram.f_max"] = (
            "Maximum frequency must exceed the minimum and not exceed Nyquist."
        )
    max_bins = int(values["spectrogram.n_fft"]) // 2 + 1
    if int(values["spectrogram.n_freq_bins"]) > max_bins:
        errors["spectrogram.n_freq_bins"] = (
            "Frequency bins cannot exceed the FFT's available frequency bins."
        )
    for lower, upper, label in (
        ("augmentation.time_stretch_from", "augmentation.time_stretch_to", "Time stretch"),
        ("augmentation.pitch_shift_from", "augmentation.pitch_shift_to", "Pitch shift"),
    ):
        if float(values[lower]) > float(values[upper]):
            errors[upper] = f"{label} maximum must be at least the minimum."
    if int(values["augmentation.noise_min_snr"]) >= int(values["augmentation.noise_max_snr"]):
        errors["augmentation.noise_max_snr"] = (
            "Noise mix maximum SNR must be greater than the minimum."
        )
    if values["augmentation.noise_source"] != "none":
        errors["augmentation.noise_source"] = (
            "Collection-selected augmentation noise is not yet supported by the verified executor."
        )
    metric = values["training.val_metric"]
    expected_mode = "min" if metric == "loss" else "max"
    if values["training.val_metric_mode"] != expected_mode:
        errors["training.val_metric_mode"] = (
            f"{metric} validation must use the {expected_mode} direction."
        )
    device = values["device"]
    if device == "cuda" and not capabilities.cuda:
        errors["device"] = "CUDA is not available in this runtime."
    if device == "mps" and not capabilities.mps:
        errors["device"] = "MPS is not available in the verified training executor."
    if int(values["training.num_workers"]) > capabilities.cpu_count:
        errors["training.num_workers"] = (
            "Data-loader workers must not exceed this machine's CPU count."
        )


def _validate_rf(
    values: Mapping[str, object],
    capabilities: DeviceCapabilities,
    errors: dict[str, str],
) -> None:
    ranges = {
        "n_estimators": (10, 100_000, "Trees must be from 10 to 100000."),
        "min_samples_leaf": (1, 1_000_000, "Minimum samples per leaf must be at least 1."),
        "rf_threshold": (0, 1, "Decision threshold must be from 0 to 1."),
        "random_state": (0, 2_147_483_647, "Random seed must be from 0 to 2147483647."),
        "min_samples_split": (2, 1_000_000, "Minimum samples to split must be at least 2."),
        "feature_config.sample_rate_hz": (1, 768_000, "Feature sample rate must be positive."),
        "feature_config.min_duration_s": (1e-9, 86_400, "Minimum duration must be positive."),
        "feature_config.n_fft": (2, 1_048_576, "Feature FFT window must be at least 2."),
        "feature_config.hop_length": (1, 1_048_576, "Feature FFT hop must be positive."),
        "feature_config.n_mfcc": (1, 1000, "MFCC coefficients must be at least 1."),
    }
    for key, (minimum, maximum, message) in ranges.items():
        _bounded(values, errors, key, minimum, maximum, message)
    max_depth = values["max_depth"]
    if max_depth is not None and not 1 <= int(max_depth) <= 100_000:
        errors["max_depth"] = "Maximum tree depth must be positive or unlimited."
    n_jobs = int(values["n_jobs"])
    if n_jobs != -1 and not 1 <= n_jobs <= max(1, capabilities.cpu_count):
        errors["n_jobs"] = "CPU workers must be −1 or within this machine's CPU count."
    max_features = values["max_features"]
    if type(max_features) is int and max_features < 1:
        errors["max_features"] = "Numeric feature counts must be at least 1."
    if type(max_features) is float and not 0 < max_features <= 1:
        errors["max_features"] = "Feature proportions must be greater than 0 and at most 1."
    if float(values["feature_config.hop_length"]) > float(values["feature_config.n_fft"]):
        errors["feature_config.hop_length"] = "Feature FFT hop must not exceed its window."
    f_min = float(values["feature_config.fmin_hz"])
    f_max = float(values["feature_config.fmax_hz"])
    nyquist = float(values["feature_config.sample_rate_hz"]) / 2
    if f_min < 0:
        errors["feature_config.fmin_hz"] = "Feature minimum frequency cannot be negative."
    if f_max <= f_min or f_max > nyquist:
        errors["feature_config.fmax_hz"] = (
            "Feature maximum frequency must exceed the minimum and not exceed Nyquist."
        )


@dataclass(frozen=True)
class FrozenTrainingConfig:
    schema_version: int
    family: str
    dataset_id: str
    requested_values: Mapping[str, object]
    effective_values: Mapping[str, object]
    class_mapping: Mapping[str, int]
    preset_origin: str | None = None

    def to_worker_snapshot(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "family": self.family,
            "dataset_id": self.dataset_id,
            "requested_values": dict(self.requested_values),
            "effective_values": dict(self.effective_values),
            "class_mapping": dict(self.class_mapping),
            "preset_origin": self.preset_origin,
        }

    @classmethod
    def from_worker_snapshot(cls, raw: object) -> FrozenTrainingConfig:
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported resolved Training configuration schema.")
        if set(raw) != {
            "schema_version",
            "family",
            "dataset_id",
            "requested_values",
            "effective_values",
            "class_mapping",
            "preset_origin",
        }:
            raise ValueError("Resolved Training configuration fields do not match its schema.")
        family = _normalize_family(raw.get("family"))
        dataset_id = raw.get("dataset_id")
        requested = raw.get("requested_values")
        effective = raw.get("effective_values")
        mapping = raw.get("class_mapping")
        preset_origin = raw.get("preset_origin")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("Resolved Training configuration requires a Dataset ID.")
        if not isinstance(requested, dict) or not isinstance(effective, dict):
            raise ValueError("Resolved Training configuration values must be objects.")
        draft = TrainingDraft(family, requested)
        expected_keys = {field.key for field in fields_for_family(family)}
        if set(effective) != expected_keys:
            raise ValueError("Effective Training configuration does not match the field catalog.")
        if mapping != {"noise": 0, "target": 1}:
            raise ValueError("Resolved Training configuration requires the binary class mapping.")
        if preset_origin is not None and (
            not isinstance(preset_origin, str) or not preset_origin.strip()
        ):
            raise ValueError("Resolved Training preset origin is invalid.")
        for field in fields_for_family(family):
            if field.mode == "editable":
                error = _type_error(field, draft.value(field.key))
            else:
                error = _type_error(field, effective[field.key])
            if error:
                raise ValueError(f"{field.key}: {error}")
        return cls(
            schema_version=1,
            family=family,
            dataset_id=dataset_id,
            requested_values=MappingProxyType(dict(requested)),
            effective_values=MappingProxyType(dict(effective)),
            class_mapping=MappingProxyType(dict(mapping)),
            preset_origin=preset_origin,
        )


def verify_frozen_training_config(
    frozen: FrozenTrainingConfig,
    dataset: TrainingDataset,
    capabilities: DeviceCapabilities,
) -> None:
    """Re-resolve the persisted request in the Worker and reject any disagreement."""
    draft = TrainingDraft(frozen.family, frozen.requested_values)
    expected = freeze_training_config(
        draft,
        dataset,
        capabilities,
        preset_origin=frozen.preset_origin,
    )
    if (
        expected.dataset_id != frozen.dataset_id
        or dict(expected.effective_values) != dict(frozen.effective_values)
        or dict(expected.class_mapping) != dict(frozen.class_mapping)
    ):
        raise ValueError("Resolved Training configuration disagrees with Worker capabilities.")


def freeze_training_config(
    draft: TrainingDraft,
    dataset: TrainingDataset,
    capabilities: DeviceCapabilities,
    *,
    preset_origin: str | None = None,
) -> FrozenTrainingConfig:
    errors = draft.validate(dataset, capabilities)
    if errors:
        raise TrainingValidationError(errors)
    requested = dict(draft.values)
    effective: dict[str, object] = {}
    for field in fields_for_family(draft.family):
        effective[field.key] = requested.get(field.key, field.default)
    if draft.family == "cnn":
        device = requested["device"]
        if device == "auto":
            effective["device"] = "cuda" if capabilities.cuda else "cpu"
        else:
            effective["device"] = device
        effective["encoder.input_channels"] = 1
        effective["classifier.num_classes"] = 2
        effective["classifier.input_channels"] = (
            512 if requested["encoder.resnet_size"] in {18, 34} else 2048
        )
    else:
        if effective["max_features"] == "all":
            effective["max_features"] = None
        if effective["class_weight"] == "none":
            effective["class_weight"] = None
        if effective["n_jobs"] == -1:
            effective["n_jobs"] = capabilities.cpu_count
        effective["feature_family"] = "robust-mfcc"
        effective["feature_config.pad_mode"] = "constant"
    return FrozenTrainingConfig(
        schema_version=1,
        family=draft.family,
        dataset_id=dataset.dataset_id,
        requested_values=MappingProxyType(requested),
        effective_values=MappingProxyType(effective),
        class_mapping=MappingProxyType({"noise": 0, "target": 1}),
        preset_origin=preset_origin,
    )
