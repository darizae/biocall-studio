from __future__ import annotations

import json

import pytest

from alpaca_desktop.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    field_definitions,
    freeze_training_config,
)
from alpaca_desktop.persistence.training_presets import PresetStore


def _dataset() -> TrainingDataset:
    return TrainingDataset(
        dataset_id="dataset-0001",
        labels=("noise", "target"),
        split_counts={
            "train": {"target": 4, "noise": 4},
            "val": {"target": 2, "noise": 2},
        },
    )


def test_catalog_roster_is_complete_typed_and_binary_only():
    """Case: UT-TRAIN-007."""
    fields = field_definitions()

    assert len(fields) == 67
    assert {field.ui_tier for field in fields} == {"primary", "details"}
    assert {field.key for field in fields if field.ui_tier == "primary"} == {
        "run_name",
        "sequence_length_ms",
        "training.max_epochs",
        "training.batch_size",
        "training.learning_rate",
        "device",
        "n_estimators",
        "max_depth",
        "min_samples_leaf",
    }
    assert all(
        field.help and field.wiki_anchor.startswith("training-configuration#") for field in fields
    )
    assert all(
        field.recommended_starting_value == field.default
        and field.recommendation_basis == "backend_default_baseline"
        for field in fields
        if field.mode == "editable"
    )
    derived = {field.key: field for field in fields if field.mode == "derived"}
    assert derived["classifier.num_classes"].default == 2
    assert all(field.recommended_starting_value is None for field in derived.values())
    max_features = next(field for field in fields if field.key == "max_features")
    assert 0.5 in max_features.choices and 1 in max_features.choices
    assert not {"task_type", "classes", "positive_class"} & {field.key for field in fields}


def test_drafts_validate_without_clamping_and_freeze_complete_values():
    """Case: UT-TRAIN-008."""
    capabilities = DeviceCapabilities(cuda=False, mps=False, cpu_count=8)
    cnn = TrainingDraft.defaults("cnn")
    cnn.set("training.batch_size", 24)
    cnn.set("spectrogram.n_fft", 1024)
    cnn.set("spectrogram.hop_length", 2048)

    errors = cnn.validate(_dataset(), capabilities)

    assert errors["spectrogram.hop_length"] == "FFT hop must not exceed the FFT window."
    assert cnn.value("spectrogram.hop_length") == 2048
    cnn.set("spectrogram.hop_length", 256)
    cnn.set("device", "cuda")
    assert "not available" in cnn.validate(_dataset(), capabilities)["device"]
    assert cnn.value("device") == "cuda"
    cnn.set("device", "auto")
    frozen = freeze_training_config(cnn, _dataset(), capabilities)

    assert frozen.family == "cnn"
    assert frozen.dataset_id == "dataset-0001"
    assert frozen.requested_values["training.batch_size"] == 24
    assert frozen.effective_values["device"] == "cpu"
    assert frozen.effective_values["classifier.num_classes"] == 2
    assert frozen.class_mapping == {"noise": 0, "target": 1}
    assert len(frozen.effective_values) == 47
    with pytest.raises(TypeError):
        frozen.effective_values["training.batch_size"] = 99

    cnn.reset("training.batch_size")
    assert cnn.value("training.batch_size") == 16
    cnn.set("training.batch_size", 32)
    cnn.reset_details()
    assert cnn.value("training.batch_size") == 32
    assert cnn.value("spectrogram.n_fft") == 4096


def test_saved_presets_are_family_scoped_complete_and_run_independent(tmp_path):
    """Case: UT-TRAIN-009."""
    store = PresetStore(tmp_path / "presets")
    cnn = TrainingDraft.defaults("cnn")
    cnn.set("training.batch_size", 32)
    cnn.set("spectrogram.n_fft", 2048)
    rf = TrainingDraft.defaults("rf")
    rf.set("n_estimators", 1200)

    first = store.create("Field laptop", cnn)
    second = store.create("Forest baseline", rf)
    duplicate = store.duplicate(first.preset_id, "Field laptop copy")
    store.rename(duplicate.preset_id, "Field laptop renamed")
    loaded = store.load(first.preset_id)
    frozen = freeze_training_config(loaded.draft, _dataset(), DeviceCapabilities(cpu_count=8))
    loaded.draft.set("training.batch_size", 64)
    store.overwrite(first.preset_id, loaded.draft)

    assert {item.family for item in store.list()} == {"cnn", "rf"}
    assert store.load(second.preset_id).draft.value("n_estimators") == 1200
    assert store.load(first.preset_id).draft.value("training.batch_size") == 64
    assert frozen.requested_values["training.batch_size"] == 32
    store.delete(duplicate.preset_id)
    assert {item.label for item in store.list()} == {"Field laptop", "Forest baseline"}
    payload = (tmp_path / "presets" / "presets.json").read_text()
    assert "dataset-0001" not in payload
    assert str(tmp_path) not in payload
    assert "classifier.num_classes" not in payload

    incompatible_values = dict(cnn.values)
    incompatible_values["classifier.num_classes"] = 3
    with pytest.raises(ValueError, match="unknown/noneditable: classifier.num_classes"):
        TrainingDraft("cnn", incompatible_values)


def test_preset_store_rejects_corruption_unknown_schema_names_and_atomic_failure(
    tmp_path, monkeypatch
):
    """Case: UT-TRAIN-010."""
    store = PresetStore(tmp_path / "presets")
    created = store.create("Baseline", TrainingDraft.defaults("cnn"))
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        store.create(" baseline ", TrainingDraft.defaults("cnn"))
    with pytest.raises(ValueError, match="Preset name"):
        store.create("../unsafe", TrainingDraft.defaults("cnn"))

    real_replace = __import__("os").replace

    def fail_replace(source, destination):
        if destination == store.path:
            raise OSError("injected replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr("alpaca_desktop.persistence.training_presets.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        store.rename(created.preset_id, "Changed")
    assert store.path.read_bytes() == before

    monkeypatch.undo()
    incompatible = json.loads(before)
    incompatible["toolbox_schema_revision"] = "unsupported-toolbox-schema"
    store.path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="toolbox revision is incompatible"):
        store.list()

    incompatible = json.loads(before)
    incompatible["presets"][0]["values"]["legacy_source_path"] = "/private/input.wav"
    store.path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="unknown/noneditable: legacy_source_path"):
        store.list()

    store.path.write_text(json.dumps({"schema_version": 999, "presets": []}))
    with pytest.raises(ValueError, match="Unsupported preset store schema"):
        store.list()
    store.path.write_text("{not json")
    with pytest.raises(ValueError, match="invalid JSON"):
        store.list()
