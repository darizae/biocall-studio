from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
import torch
from bioacoustics_dl_toolbox.config import (
    ClassifierConfig,
    EncoderConfig,
    NormalizationConfig,
    SpectrogramConfig,
)
from bioacoustics_dl_toolbox.models import Classifier, ResidualEncoder
from bioacoustics_dl_toolbox.training.checkpoints import save_model

from biocall_studio.shared.integrity import sha256_file
from biocall_studio.train.domain.model import validate_model_manifest
from biocall_studio.train.persistence.models import (
    discard_uncommitted_model,
    load_model,
    load_model_directory,
    structurally_reload_cnn_model,
)


def _manifest(checkpoint, *, digest: str | None = None) -> dict:
    encoder_config = EncoderConfig(resnet_size=18)
    classifier_config = ClassifierConfig(input_channels=512, num_classes=2)
    spectrogram = SpectrogramConfig(
        sample_rate=16_000,
        n_fft=256,
        hop_length=64,
        n_freq_bins=64,
        f_min=100,
        f_max=7_000,
    )
    normalization = NormalizationConfig()
    return {
        "schema_version": 1,
        "model_id": "model-cnn-0001",
        "label": "Tiny verified CNN",
        "family": "cnn",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": "run-cnn-0001",
        "request_id": "request-cnn-0001",
        "dataset_id": "dataset-0001",
        "dataset_reference": "datasets/dataset-0001",
        "dataset_manifest_sha256": "a" * 64,
        "task": {
            "type": "binary_single_label",
            "class_to_index": {"noise": 0, "target": 1},
            "positive_class": "target",
            "num_classes": 2,
            "output": "categorical_logits",
        },
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
            "dataset_id": "dataset-0001",
            "requested_values": {"training.max_epochs": 1},
            "effective_values": {
                "sequence_length_ms": 250,
                "spectrogram.sample_rate": 16_000,
                "training.max_epochs": 1,
                "classifier.num_classes": 2,
            },
            "class_mapping": {"noise": 0, "target": 1},
            "preset_origin": None,
        },
        "cnn": {
            "architecture": {
                "encoder": asdict(encoder_config),
                "classifier": asdict(classifier_config),
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
                "optimizer": {"name": "Adam", "learning_rate": 0.0001, "beta1": 0.5},
                "objective": "CrossEntropyLoss",
            },
        },
        "results": {
            "split_counts": {
                "train": {"noise": 2, "target": 2},
                "val": {"noise": 1, "target": 1},
            },
            "history": {
                "train": [{"epoch": 1, "loss": 0.75}],
                "val": [{"epoch": 1, "loss": 0.72}],
            },
            "metrics": {
                "accuracy": {"value": 0.5, "reason": None},
                "precision": {"value": 0.5, "reason": None},
                "recall": {"value": 1.0, "reason": None},
                "f1": {"value": 2 / 3, "reason": None},
                "roc_auc": {"value": 0.5, "reason": None},
            },
            "selected_epoch": 1,
        },
        "artifact": {
            "path": "model.pt",
            "size_bytes": checkpoint.stat().st_size,
            "sha256": digest or sha256_file(checkpoint),
            "format": "bioacoustics-dl-toolbox-pytorch",
            "format_version": 2,
        },
        "provenance": {
            "trainer": {"distribution": "biocall-studio", "version": "0.1.0a0"},
            "toolbox": {
                "distribution": "bioacoustics-dl-toolbox",
                "version": "0.2.0",
                "revision": "22c1b342918b33c62288f23b660aa716f3e361e6",
            },
            "torch_version": torch.__version__,
            "scientific_reference": "alpaca-pipelines@91af5287dc18313f88902dc9696e8756274736b3",
        },
    }


def _published_model(tmp_path):
    root = tmp_path / "collection"
    model_root = root / ".alpaca" / "models" / "model-cnn-0001"
    model_root.mkdir(parents=True)
    encoder_config = EncoderConfig(resnet_size=18)
    encoder = ResidualEncoder(encoder_config)
    classifier_config = ClassifierConfig(
        input_channels=encoder.output_channels,
        pooling="avg",
        num_classes=2,
    )
    classifier = Classifier(classifier_config)
    checkpoint = model_root / "model.pt"
    save_model(
        torch.nn.Sequential(encoder, classifier),
        encoder,
        encoder_config,
        classifier,
        classifier_config,
        SpectrogramConfig(
            sample_rate=16_000,
            n_fft=256,
            hop_length=64,
            n_freq_bins=64,
            f_min=100,
            f_max=7_000,
        ),
        checkpoint,
        {"noise": 0, "target": 1},
        metadata={
            "schema_version": 2,
            "task_type": "binary",
            "normalization_config": asdict(NormalizationConfig()),
            "window_length_samples": 4_000,
            "sequence_length_frames": 59,
            "class_names": ["noise", "target"],
        },
    )
    manifest = _manifest(checkpoint)
    (model_root / "model.json").write_text(json.dumps(manifest))
    return root, model_root, manifest


def test_model_manifest_identity_paths_metrics_and_binary_contract(tmp_path):
    """Case: UT-TRAIN-004."""
    root, model_root, manifest = _published_model(tmp_path)

    validated = validate_model_manifest(manifest)
    artifact = load_model(root, "model-cnn-0001")

    assert validated["dataset_reference"] == "datasets/dataset-0001"
    assert artifact.model_id == "model-cnn-0001"
    assert artifact.manifest["results"]["metrics"]["f1"]["value"] == pytest.approx(2 / 3)

    for changed, message in (
        ({**manifest, "family": "random_forest"}, "family"),
        ({**manifest, "dataset_reference": "../private"}, "traversal|reference"),
        ({**manifest, "schema_version": 99}, "schema"),
    ):
        with pytest.raises(ValueError, match=message):
            validate_model_manifest(changed)

    corrupt = json.loads(json.dumps(manifest))
    corrupt["task"]["class_to_index"] = {"noise": 0, "target": 1, "other": 2}
    with pytest.raises(ValueError, match="two-class"):
        validate_model_manifest(corrupt)

    incompatible = json.loads(json.dumps(manifest))
    incompatible["provenance"]["toolbox"]["version"] = "999"
    with pytest.raises(ValueError, match="incompatible"):
        validate_model_manifest(incompatible)

    original = (model_root / "model.pt").read_bytes()
    (model_root / "model.pt").write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])
    with pytest.raises(ValueError, match="digest"):
        load_model_directory(model_root, "model-cnn-0001")


def test_cnn_checkpoint_structural_reload_matches_exported_configuration(tmp_path):
    """Case: UT-TRAIN-005."""
    root, model_root, manifest = _published_model(tmp_path)

    structure = structurally_reload_cnn_model(root, "model-cnn-0001")

    assert structure.num_classes == 2
    assert structure.class_to_index == {"noise": 0, "target": 1}
    assert structure.encoder_config == manifest["cnn"]["architecture"]["encoder"]
    assert structure.classifier_config == manifest["cnn"]["architecture"]["classifier"]
    assert structure.spectrogram_config == manifest["cnn"]["transforms"]["spectrogram"]
    assert structure.normalization_config == manifest["cnn"]["transforms"]["normalization"]
    assert structure.window_length_samples == manifest["input"]["window_length_samples"]
    assert structure.sequence_length_frames == manifest["input"]["sequence_length_frames"]

    mismatched = json.loads(json.dumps(manifest))
    mismatched["cnn"]["architecture"]["classifier"]["num_classes"] = 3
    (model_root / "model.json").write_text(json.dumps(mismatched))
    with pytest.raises(ValueError, match="two-class|num_classes"):
        structurally_reload_cnn_model(root, "model-cnn-0001")


def test_model_manifest_preserves_null_metric_reason(tmp_path):
    """Case: UT-TRAIN-003."""
    _root, _model_root, manifest = _published_model(tmp_path)
    manifest["results"]["metrics"]["roc_auc"] = {
        "value": None,
        "reason": "Validation Split does not contain both classes.",
    }

    validated = validate_model_manifest(manifest)

    assert validated["results"]["metrics"]["roc_auc"]["value"] is None
    assert "both classes" in validated["results"]["metrics"]["roc_auc"]["reason"]


def test_uncommitted_model_cleanup_requires_exact_run_identity(tmp_path):
    """Case: UT-TRAIN-004."""
    root, model_root, _manifest_data = _published_model(tmp_path)

    with pytest.raises(ValueError, match="different Run"):
        discard_uncommitted_model(
            root,
            "model-cnn-0001",
            run_id="run-other",
            request_id="request-cnn-0001",
        )
    assert model_root.is_dir()

    assert discard_uncommitted_model(
        root,
        "model-cnn-0001",
        run_id="run-cnn-0001",
        request_id="request-cnn-0001",
    )
    assert not model_root.exists()
