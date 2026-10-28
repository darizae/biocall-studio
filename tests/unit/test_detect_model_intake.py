from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import pytest
import torch
from bioacoustics_dl_toolbox.config import (
    ClassifierConfig,
    EncoderConfig,
    NormalizationConfig,
    SpectrogramConfig,
)

from biocall_studio.detect import models
from biocall_studio.detect.models import (
    ModelFamily,
    ModelRole,
    ModelSnapshot,
    ScientificEvidenceState,
    inspect_model_directory,
    recheck_model_reference,
)
from biocall_studio_train.domain.model import (
    MODEL_SCIENTIFIC_REFERENCE,
    MODEL_TOOLBOX_REVISION,
)
from biocall_studio_train.domain.rf_training import rf_feature_names


def _collection_manifest() -> dict[str, object]:
    return {
        "schema_version": 2,
        "collection_id": "collection-model-intake",
        "collection_name": "Model intake",
        "scanned_at": datetime.now(UTC).isoformat(),
        "valid": True,
        "summary": {},
        "inventory": [],
        "record_partitions": [],
        "positive_partitions": [],
        "partition_sha256": {},
        "header_reads": 0,
    }


def _base_manifest(*, model_id: str, family: str, artifact: dict[str, object]) -> dict:
    output = "categorical_logits" if family == "cnn" else "target_probability"
    return {
        "schema_version": 1,
        "model_id": model_id,
        "label": "Verified intake fixture",
        "family": family,
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": f"run-{model_id}",
        "request_id": f"request-{model_id}",
        "dataset_id": "dataset-model-intake",
        "dataset_reference": "datasets/dataset-model-intake",
        "dataset_manifest_sha256": "a" * 64,
        "task": {
            "type": "binary_single_label",
            "class_to_index": {"noise": 0, "target": 1},
            "positive_class": "target",
            "num_classes": 2,
            "output": output,
        },
        "artifact": artifact,
    }


def _cnn_manifest(model_id: str, binary: Path) -> dict:
    encoder = EncoderConfig(resnet_size=18)
    classifier = ClassifierConfig(input_channels=512, num_classes=2)
    spectrogram = SpectrogramConfig(
        sample_rate=16_000,
        n_fft=256,
        hop_length=64,
        n_freq_bins=64,
        f_min=100,
        f_max=7_000,
    )
    normalization = NormalizationConfig()
    artifact = {
        "path": binary.name,
        "size_bytes": binary.stat().st_size,
        "sha256": models.sha256_file(binary),
        "format": "bioacoustics-dl-toolbox-pytorch",
        "format_version": 2,
    }
    manifest = _base_manifest(model_id=model_id, family="cnn", artifact=artifact)
    manifest.update(
        {
            "input": {
                "channel_policy": "mixdown_mono",
                "sample_rate_policy": "resample_to_model_rate",
                "sample_rate_hz": 16_000,
                "window_duration_ms": 250,
                "window_length_samples": 4_000,
                "sequence_length_frames": 59,
                "time_unit": "milliseconds",
                "sample_rounding": "nearest_integer_sample",
            },
            "resolved_config": {
                "schema_version": 1,
                "family": "cnn",
                "dataset_id": "dataset-model-intake",
                "requested_values": {"training.max_epochs": 1},
                "effective_values": {
                    "sequence_length_ms": 250,
                    "spectrogram.sample_rate": 16_000,
                    "classifier.num_classes": 2,
                },
                "class_mapping": {"noise": 0, "target": 1},
                "preset_origin": None,
            },
            "cnn": {
                "architecture": {
                    "encoder": asdict(encoder),
                    "classifier": asdict(classifier),
                },
                "transforms": {
                    "spectrogram": asdict(spectrogram),
                    "normalization": asdict(normalization),
                    "augmentation": {
                        "training": {"enabled": False},
                        "validation": {"enabled": False},
                    },
                    "preprocessing_order": [
                        "mono",
                        "resample",
                        "preemphasis",
                        "power_spectrogram",
                        "frequency_compression",
                        "normalization",
                        "fixed_window",
                    ],
                },
                "training": {
                    "seed": 42,
                    "device": "cpu",
                    "optimizer": {
                        "name": "Adam",
                        "learning_rate": 0.0001,
                        "beta1": 0.5,
                    },
                    "objective": "CrossEntropyLoss",
                },
            },
            "results": {
                "split_counts": {
                    "train": {"noise": 2, "target": 2},
                    "val": {"noise": 1, "target": 1},
                },
                "history": {
                    "train": [{"epoch": 1, "loss": 0.7}],
                    "val": [{"epoch": 1, "loss": 0.8}],
                },
                "metrics": _metrics(),
                "selected_epoch": 1,
            },
            "provenance": {
                "trainer": {
                    "distribution": "biocall-studio-train",
                    "version": version("biocall-studio-train"),
                },
                "toolbox": {
                    "distribution": "bioacoustics-dl-toolbox",
                    "version": version("bioacoustics-dl-toolbox"),
                    "revision": MODEL_TOOLBOX_REVISION,
                },
                "torch_version": torch.__version__,
                "scientific_reference": MODEL_SCIENTIFIC_REFERENCE,
            },
        }
    )
    return manifest


def _metrics() -> dict[str, dict[str, float | str | None]]:
    return {
        name: {"value": 0.5, "reason": None}
        for name in ("accuracy", "precision", "recall", "f1", "roc_auc")
    }


def _rf_manifest(model_id: str, binary: Path) -> dict:
    feature_config = {
        "sample_rate_hz": 8_000,
        "min_duration_s": 0.25,
        "pad_short_segments": True,
        "pad_mode": "constant",
        "n_fft": 256,
        "hop_length": 64,
        "n_mfcc": 2,
        "include_deltas": False,
        "fmin_hz": 100.0,
        "fmax_hz": 3_500.0,
    }
    names = rf_feature_names(2, False)
    artifact = {
        "path": binary.name,
        "size_bytes": binary.stat().st_size,
        "sha256": models.sha256_file(binary),
        "format": "scikit-learn-joblib",
        "format_version": 1,
    }
    manifest = _base_manifest(model_id=model_id, family="random_forest", artifact=artifact)
    effective = {f"feature_config.{key}": value for key, value in feature_config.items()}
    effective["rf_threshold"] = 0.55
    manifest.update(
        {
            "input": {
                "channel_policy": "mixdown_mono",
                "sample_rate_policy": "resample_to_model_rate_librosa_soxr_hq_fix_unscaled",
                "sample_rate_hz": 8_000,
                "min_duration_s": 0.25,
                "short_segment_policy": "center_zero_pad",
                "pad_mode": "constant",
                "dtype": "float32",
                "sample_rounding": "nearest_integer_sample",
                "preprocessing_order": [
                    "decode",
                    "mixdown_mono",
                    "resample",
                    "minimum_pad",
                ],
                "non_finite_policy": "reject",
            },
            "resolved_config": {
                "schema_version": 1,
                "family": "rf",
                "dataset_id": "dataset-model-intake",
                "requested_values": {},
                "effective_values": effective,
                "class_mapping": {"noise": 0, "target": 1},
                "preset_origin": None,
            },
            "random_forest": {
                "estimator": {
                    "type": "sklearn.ensemble.RandomForestClassifier",
                    "hyperparameters": {},
                    "classes": [0, 1],
                    "probability_columns": [
                        {"column": 0, "class_index": 0, "label": "noise"},
                        {"column": 1, "class_index": 1, "label": "target"},
                    ],
                    "target_probability_column": 1,
                    "n_features_in": len(names),
                },
                "features": {
                    "family": "robust-mfcc-v1",
                    "extractor_distribution": "bioacoustics-dl-toolbox",
                    "extractor_api": "bioacoustics_dl_toolbox.rf.compute_rf_features",
                    "extractor_revision": MODEL_TOOLBOX_REVISION,
                    "names": list(names),
                    "config": feature_config,
                    "window": "hann",
                    "center": True,
                    "output_dtype": "float64",
                },
                "decision_policy": {
                    "positive_class": "target",
                    "threshold": 0.55,
                    "scope": "held_out_validation_and_saved_policy",
                },
            },
            "results": {
                "split_counts": {
                    "train": {"noise": 2, "target": 2},
                    "val": {"noise": 1, "target": 1},
                },
                "metrics": _metrics(),
                "feature_importances": [
                    {"name": name, "value": 1.0 / len(names)} for name in names
                ],
            },
            "provenance": {
                "trainer": {
                    "distribution": "biocall-studio-train",
                    "version": version("biocall-studio-train"),
                },
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
    )
    return manifest


def _package(tmp_path: Path, family: str) -> tuple[Path, dict]:
    model_id = "model-cnn-intake" if family == "cnn" else "model-rf-intake"
    alpaca = tmp_path / "collection" / ".alpaca"
    root = alpaca / "models" / model_id
    root.mkdir(parents=True)
    (alpaca / "collection.json").write_text(json.dumps(_collection_manifest()))
    binary = root / ("model.pt" if family == "cnn" else "random_forest.joblib")
    binary.write_bytes(b"trusted structural fixture")
    manifest = (
        _cnn_manifest(model_id, binary) if family == "cnn" else _rf_manifest(model_id, binary)
    )
    (root / "model.json").write_text(json.dumps(manifest))
    return root, manifest


@pytest.fixture(autouse=True)
def _structural_loader_spy(monkeypatch):
    calls: list[tuple[Path, str, ModelFamily]] = []

    def load(root: Path, model_id: str, family: ModelFamily) -> None:
        calls.append((root, model_id, family))

    monkeypatch.setattr(models, "_load_runtime_structure", load)
    return calls


@pytest.mark.parametrize("family", ["cnn", "random_forest"])
def test_model_manifest_integrity_binary_contract_and_family_fields(
    tmp_path, family, _structural_loader_spy
):
    """Case: UT-DET-007."""
    root, manifest = _package(tmp_path, family)

    reference = inspect_model_directory(root)

    assert reference.snapshot.model_id == manifest["model_id"]
    assert reference.snapshot.manifest_sha256 == models.sha256_file(root / "model.json")
    assert reference.snapshot.artifact_sha256 == manifest["artifact"]["sha256"]
    assert reference.snapshot.class_to_index == (("noise", 0), ("target", 1))
    assert reference.snapshot.structure is ScientificEvidenceState.PASSED
    assert _structural_loader_spy == [
        (root.resolve(), manifest["model_id"], reference.snapshot.family)
    ]

    corrupt = json.loads(json.dumps(manifest))
    corrupt["task"]["class_to_index"] = {"noise": 0, "target": 1, "other": 2}
    (root / "model.json").write_text(json.dumps(corrupt))
    with pytest.raises(ValueError, match="two-class"):
        inspect_model_directory(root)

    (root / "model.json").write_text(json.dumps(manifest))
    binary = root / manifest["artifact"]["path"]
    binary.write_bytes(binary.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="size|digest"):
        inspect_model_directory(root)


def test_untrusted_unsafe_or_unsupported_model_never_deserializes(
    tmp_path, monkeypatch, _structural_loader_spy
):
    """Case: UT-DET-008."""
    root, manifest = _package(tmp_path, "cnn")
    untrusted = tmp_path / "downloads" / root.name
    untrusted.parent.mkdir()
    root.rename(untrusted)
    with pytest.raises(ValueError, match="trusted Train Model location"):
        inspect_model_directory(untrusted)
    assert _structural_loader_spy == []

    root.parent.mkdir(parents=True, exist_ok=True)
    untrusted.rename(root)
    unsupported = json.loads(json.dumps(manifest))
    unsupported["provenance"]["torch_version"] = "0.0.0"
    (root / "model.json").write_text(json.dumps(unsupported))
    with pytest.raises(ValueError, match="runtime"):
        inspect_model_directory(root)
    assert _structural_loader_spy == []

    unsafe = json.loads(json.dumps(manifest))
    unsafe["artifact"]["path"] = "../outside.pt"
    (root / "model.json").write_text(json.dumps(unsafe))
    with pytest.raises(ValueError, match="traversal|artifact"):
        inspect_model_directory(root)
    assert _structural_loader_spy == []

    (root / "model.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(
        models,
        "_verified_toolbox_import_origin",
        lambda: (_ for _ in ()).throw(ValueError("ambiguous pipeline shadow")),
    )
    with pytest.raises(ValueError, match="ambiguous pipeline shadow"):
        inspect_model_directory(root)
    assert _structural_loader_spy == []


def test_typed_handoff_preserves_role_semantics_and_unproven_prediction_parity(
    tmp_path, _structural_loader_spy
):
    """Case: UT-DET-009."""
    cnn_root, _ = _package(tmp_path / "cnn", "cnn")
    rf_root, rf_manifest = _package(tmp_path / "rf", "random_forest")

    cnn = inspect_model_directory(cnn_root)
    rf = inspect_model_directory(rf_root)

    assert cnn.snapshot.family is ModelFamily.CNN
    assert cnn.snapshot.role is ModelRole.PRIMARY_DETECTION
    assert cnn.snapshot.positive_output_index == 1
    assert cnn.snapshot.prediction_parity is ScientificEvidenceState.UNPROVEN
    assert cnn.snapshot.trusted is True
    assert cnn.snapshot.runtime_loadable is ScientificEvidenceState.PASSED
    assert cnn.snapshot.normalization_config == (
        ("min_level_db", -100.0),
        ("mode", "db"),
        ("ref_level_db", 20.0),
    )

    assert rf.snapshot.family is ModelFamily.RANDOM_FOREST
    assert rf.snapshot.role is ModelRole.INTERVAL_REFINEMENT
    assert rf.snapshot.rf_probability_column == 1
    assert rf.snapshot.rf_feature_names == tuple(
        rf_manifest["random_forest"]["features"]["names"]
    )
    assert rf.snapshot.prediction_parity is ScientificEvidenceState.UNPROVEN
    assert ModelSnapshot.from_dict(rf.snapshot.to_dict()) == rf.snapshot

    rechecked = recheck_model_reference(rf)
    assert rechecked == rf
    (rf_root / "model.json").write_text((rf_root / "model.json").read_text() + "\n")
    with pytest.raises(ValueError, match="changed since it was selected"):
        recheck_model_reference(rf)
