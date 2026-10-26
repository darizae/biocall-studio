from __future__ import annotations

import json

import pytest

from biocall_studio_train.persistence.display_names import DisplayNameStore


def test_display_names_are_atomic_validated_and_separate_from_artifact_manifests(tmp_path):
    """Case: UT-UI-001."""
    root = tmp_path / "collection"
    alpaca = root / ".alpaca"
    dataset = alpaca / "datasets" / "dataset-1"
    model = alpaca / "models" / "model-1"
    dataset.mkdir(parents=True)
    model.mkdir(parents=True)
    dataset_manifest = dataset / "dataset.json"
    model_manifest = model / "model.json"
    dataset_manifest.write_text('{"label":"Original Dataset"}\n')
    model_manifest.write_text('{"label":"Original Model"}\n')

    store = DisplayNameStore(root)
    store.rename("datasets", "dataset-1", "  Dawn set  ")
    store.rename("models", "model-1", "Dawn classifier")

    assert store.name("datasets", "dataset-1", "Original Dataset") == "Dawn set"
    assert store.name("models", "model-1", "Original Model") == "Dawn classifier"
    assert json.loads(dataset_manifest.read_text()) == {"label": "Original Dataset"}
    assert json.loads(model_manifest.read_text()) == {"label": "Original Model"}
    assert not list(alpaca.glob("*.tmp"))

    with pytest.raises(ValueError, match="cannot be empty"):
        store.rename("datasets", "dataset-1", "   ")
    with pytest.raises(ValueError, match="printable"):
        store.rename("models", "model-1", "bad\nname")
    with pytest.raises(ValueError, match="does not exist"):
        store.rename("models", "missing", "Missing")

    store.forget("datasets", "dataset-1")
    assert store.name("datasets", "dataset-1", "Original Dataset") == "Original Dataset"
