from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version

import pytest
from alp_ui.components import Plot
from PySide6.QtWidgets import QLabel

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.domain.run import RunStatus
from alpaca_desktop.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.persistence.diagnostics import read_diagnostic_records, worker_log_path
from alpaca_desktop.persistence.models import (
    list_models,
    load_model,
    structurally_reload_cnn_model,
    structurally_reload_rf_model,
)
from alpaca_desktop.persistence.training_presets import PresetStore
from alpaca_desktop.workflows.dataset_build import build_dataset

pytestmark = pytest.mark.integration


def _dataset(root, wav_factory):
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        wav_factory(root / "recordings" / f"{stem}.wav", frames=32_000, rate=16_000)
        wav_factory(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index}.wav",
            frames=8_000,
            rate=16_000,
        )
    scan = publish_collection_metadata(root, scan_collection(root))
    config = BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=100,
    )
    return scan, build_dataset(root, scan, config, dataset_id="dataset-rf-training")


def _fast_rf_draft():
    draft = TrainingDraft.defaults("rf")
    for key, value in {
        "n_estimators": 10,
        "min_samples_leaf": 1,
        "rf_threshold": 0.55,
        "random_state": 42,
        "n_jobs": 1,
        "feature_config.sample_rate_hz": 8_000,
        "feature_config.min_duration_s": 0.25,
        "feature_config.n_fft": 256,
        "feature_config.hop_length": 64,
        "feature_config.n_mfcc": 4,
        "feature_config.fmin_hz": 100.0,
        "feature_config.fmax_hz": 3_500.0,
        "logging_level": "debug",
    }.items():
        draft.set(key, value)
    return draft


def _fast_cnn_draft():
    draft = TrainingDraft.defaults("cnn")
    for key, value in {
        "sequence_length_ms": 250,
        "training.max_epochs": 1,
        "training.batch_size": 2,
        "training.learning_rate": 0.0001,
        "device": "cpu",
        "spectrogram.sample_rate": 16_000,
        "spectrogram.n_fft": 256,
        "spectrogram.hop_length": 64,
        "spectrogram.n_freq_bins": 64,
        "spectrogram.f_min": 100,
        "spectrogram.f_max": 7_000,
        "training.num_workers": 0,
        "training.early_stopping_patience_epochs": 2,
        "training.epochs_per_eval": 1,
        "training.pin_memory": False,
    }.items():
        draft.set(key, value)
    return draft


@pytest.mark.qt
def test_real_rf_worker_publishes_reloadable_model_and_native_views(
    qapp, qtbot, tmp_path, wav_factory
):
    """Cases: IT-TRAIN-002, IT-TRAIN-003, IT-TRAIN-005, IT-TRAIN-006, IT-TRAIN-007,
    IT-TRAIN-008, IT-TRAIN-012, IT-TRAIN-014, IT-LOG-002.
    """
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    source_bytes = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)

    cnn_frozen = freeze_training_config(
        _fast_cnn_draft(),
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    cnn_run_id = controller.start_training(
        cnn_frozen,
        model_label="Tiny verified CNN",
        model_id="model-cnn-shared-dataset",
    )
    qtbot.waitUntil(
        lambda: any(run.run_id == cnn_run_id and run.terminal for run in controller.runs),
        timeout=180_000,
    )
    cnn_run = next(run for run in controller.runs if run.run_id == cnn_run_id)
    assert cnn_run.status is RunStatus.COMPLETED
    assert cnn_run.training_family == "cnn"

    preset_store = PresetStore(tmp_path / "presets")
    preset = preset_store.create("Tiny RF", _fast_rf_draft())
    loaded = preset_store.load(preset.preset_id)
    frozen = freeze_training_config(
        loaded.draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
        preset_origin=loaded.record.preset_id,
    )
    frozen_snapshot = frozen.to_worker_snapshot()

    run_id = controller.start_training(
        frozen,
        model_label="Tiny verified RF",
        model_id="model-rf-integration",
    )
    preset_store.overwrite(preset.preset_id, TrainingDraft.defaults("rf"))
    preset_store.delete(preset.preset_id)
    qtbot.waitUntil(
        lambda: any(run.run_id == run_id and run.terminal for run in controller.runs),
        timeout=180_000,
    )
    run = next(run for run in controller.runs if run.run_id == run_id)

    assert run.status is RunStatus.COMPLETED
    assert run.training_family == "rf"
    assert run.published_artifact_id == "model-rf-integration"
    assert run.stages == (
        "Validate immutable Dataset",
        "Extract acoustic features",
        "Fit Random Forest",
        "Validate predictions",
        "Verify and publish Model",
    )
    importance_rows = [row for row in run.measurements if row["kind"] == "feature_importance"]
    assert importance_rows
    worker_records, notices = read_diagnostic_records(worker_log_path(root, run_id))
    assert notices == ()
    assert {record["event"] for record in worker_records} >= {
        "worker_started",
        "training_stage",
        "measurement_available",
        "worker_completed",
    }
    models = list_models(root)
    assert {model.model_id for model in models} == {
        "model-cnn-shared-dataset",
        "model-rf-integration",
    }
    assert {model.manifest["dataset_id"] for model in models} == {dataset.dataset_id}
    assert {model.manifest["family"] for model in models} == {"cnn", "random_forest"}
    cnn_model = next(model for model in models if model.model_id == "model-cnn-shared-dataset")
    model = next(model for model in models if model.model_id == "model-rf-integration")
    assert model.manifest["family"] == "random_forest"
    assert model.manifest["resolved_config"] == frozen_snapshot
    assert model.manifest["resolved_config"]["preset_origin"] == preset.preset_id
    assert model.manifest["random_forest"]["decision_policy"]["threshold"] == 0.55
    assert model.manifest["random_forest"]["estimator"]["classes"] == [0, 1]
    assert model.manifest["random_forest"]["estimator"]["target_probability_column"] == 1
    assert model.manifest["input"]["sample_rate_policy"] == (
        "resample_to_model_rate_librosa_soxr_hq_fix_unscaled"
    )
    assert model.manifest["provenance"]["librosa_version"] == version("librosa")
    assert model.manifest["results"]["feature_importances"] == [
        {"name": row["feature"], "value": row["importance"]} for row in importance_rows
    ]
    assert str(root) not in (model.root / "model.json").read_text()
    assert source_bytes == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }

    structure = structurally_reload_rf_model(root, model.model_id)
    assert structure.classes == (0, 1)
    assert structure.n_features == len(structure.feature_names)
    assert structurally_reload_cnn_model(root, cnn_model.model_id).num_classes == 2
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json,sys; "
                "from pathlib import Path; "
                "from alpaca_desktop.persistence.models import structurally_reload_rf_model; "
                "print(json.dumps(structurally_reload_rf_model(Path(sys.argv[1]), "
                "sys.argv[2]).to_dict(), sort_keys=True))"
            ),
            str(root),
            model.model_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["classes"] == [0, 1]

    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.open_run(run_id)
    assert isinstance(window.run_detail_page.training_plot, Plot)
    assert window.run_detail_page.training_plot.kind == "bar"
    assert window.run_detail_page.training_plot.accessibleDescription() == (
        f"Bar plot with {len(importance_rows)} categories."
    )
    assert "Feature importance" in window.run_detail_page.training_values.accessibleName()
    for item in importance_rows:
        assert f"{item['feature']} · {item['importance']:.6f}" in (
            window.run_detail_page.training_values.text()
        )
    window.navigate("models")
    assert window.model_list_page.model.rowCount() == 2
    displayed_families = {
        window.model_list_page.model.index(row, 1).data()
        for row in range(window.model_list_page.model.rowCount())
    }
    assert displayed_families == {"CNN", "Random Forest"}
    window.open_model(model.model_id)
    assert window.current_route == "model-detail"
    assert "Random Forest" in window.model_detail_page.accessibleName()
    model_text = "\n".join(label.text() for label in window.findChildren(QLabel))
    assert "Librosa" in model_text
    assert version("librosa") in model_text

    undefined_draft = _fast_rf_draft()
    undefined_draft.set("min_samples_leaf", 100)
    undefined_config = freeze_training_config(
        undefined_draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    undefined_run_id = controller.start_training(
        undefined_config,
        model_label="RF with undefined precision metrics",
        model_id="model-rf-undefined-metrics",
    )
    qtbot.waitUntil(
        lambda: any(item.run_id == undefined_run_id and item.terminal for item in controller.runs),
        timeout=180_000,
    )
    undefined_run = next(item for item in controller.runs if item.run_id == undefined_run_id)
    assert undefined_run.status is RunStatus.COMPLETED
    undefined_model = load_model(root, "model-rf-undefined-metrics")
    assert undefined_model.manifest["results"]["metrics"]["f1"] == {
        "value": None,
        "reason": "F1 is undefined without target true positives.",
    }
    window.open_model(undefined_model.model_id)
    undefined_model_text = "\n".join(label.text() for label in window.findChildren(QLabel))
    assert "F1 is undefined without target true positives." in undefined_model_text

    manifest_path = model.root / "model.json"
    original_manifest = manifest_path.read_text()
    incompatible = json.loads(original_manifest)
    incompatible["random_forest"]["features"]["names"][0:2] = reversed(
        incompatible["random_forest"]["features"]["names"][0:2]
    )
    manifest_path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="ordered feature schema"):
        load_model(root, model.model_id)
    manifest_path.write_text(original_manifest)

    incompatible = json.loads(original_manifest)
    incompatible["random_forest"]["features"]["config"]["include_deltas"] = "yes"
    incompatible["resolved_config"]["effective_values"]["feature_config.include_deltas"] = "yes"
    manifest_path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="feature configuration"):
        load_model(root, model.model_id)
    manifest_path.write_text(original_manifest)

    incompatible = json.loads(original_manifest)
    incompatible["random_forest"]["estimator"]["classes"] = [0, 1, 2]
    manifest_path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="class or feature shape"):
        load_model(root, model.model_id)
    manifest_path.write_text(original_manifest)

    incompatible = json.loads(original_manifest)
    incompatible["artifact"]["path"] = "../outside.joblib"
    manifest_path.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="traversal|binary"):
        load_model(root, model.model_id)
    manifest_path.write_text(original_manifest)

    binary = model.root / "random_forest.joblib"
    original_binary = binary.read_bytes()
    binary.write_bytes(bytes([original_binary[0] ^ 0xFF]) + original_binary[1:])
    with pytest.raises(ValueError, match="digest"):
        load_model(root, model.model_id)


@pytest.mark.qt
def test_info_and_debug_diagnostics_do_not_change_rf_science(
    qapp, qtbot, tmp_path, wav_factory
):
    """Case: IT-LOG-002."""
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    controller = WorkspaceController(tmp_path / "settings")
    controller.bind_verified_collection(root, scan.collection_id)

    runs = {}
    for detail in ("info", "debug"):
        draft = _fast_rf_draft()
        draft.set("logging_level", detail)
        frozen = freeze_training_config(
            draft,
            TrainingDataset.from_artifact(dataset),
            DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
        )
        run_id = controller.start_training(
            frozen,
            model_label=f"RF {detail} diagnostics",
            model_id=f"model-rf-{detail}-diagnostics",
        )
        qtbot.waitUntil(
            lambda current=run_id: any(
                run.run_id == current and run.terminal for run in controller.runs
            ),
            timeout=180_000,
        )
        runs[detail] = next(run for run in controller.runs if run.run_id == run_id)

    assert runs["info"].status is RunStatus.COMPLETED
    assert runs["debug"].status is RunStatus.COMPLETED
    assert runs["info"].measurements == runs["debug"].measurements
    models = {model.model_id: model for model in list_models(root)}
    info_model = models["model-rf-info-diagnostics"]
    debug_model = models["model-rf-debug-diagnostics"]
    assert info_model.manifest["results"] == debug_model.manifest["results"]
    assert info_model.manifest["artifact"]["sha256"] == debug_model.manifest["artifact"][
        "sha256"
    ]
    info_records, _ = read_diagnostic_records(worker_log_path(root, runs["info"].run_id))
    debug_records, _ = read_diagnostic_records(worker_log_path(root, runs["debug"].run_id))
    assert not any(record["event"] == "measurement_available" for record in info_records)
    assert any(record["event"] == "measurement_available" for record in debug_records)


@pytest.mark.qt
def test_rf_cancellation_and_changed_dataset_never_publish_model(
    qapp, qtbot, tmp_path, wav_factory
):
    """Cases: IT-TRAIN-004, IT-TRAIN-009."""
    create_application()
    root = tmp_path / "collection"
    scan, dataset = _dataset(root, wav_factory)
    controller = WorkspaceController(
        tmp_path / "settings",
        worker_step_delay_seconds=0.2,
        cancel_grace_ms=100,
        kill_grace_ms=200,
    )
    controller.bind_verified_collection(root, scan.collection_id)
    frozen = freeze_training_config(
        _fast_rf_draft(),
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    run_id = controller.start_training(
        frozen,
        model_label="Cancelled RF",
        model_id="model-rf-cancelled",
    )
    qtbot.waitUntil(
        lambda: (
            controller.active_run is not None and controller.active_run.status is RunStatus.RUNNING
        ),
        timeout=20_000,
    )
    controller.cancel_active_run()
    qtbot.waitUntil(
        lambda: any(run.run_id == run_id and run.terminal for run in controller.runs),
        timeout=60_000,
    )
    cancelled = next(run for run in controller.runs if run.run_id == run_id)
    assert cancelled.status is RunStatus.CANCELLED
    assert not (root / ".alpaca" / "models" / "model-rf-cancelled").exists()

    broken = dataset.root / dataset.snippets[0]["relative_path"]
    broken.unlink()
    with pytest.raises(ValueError, match="missing|unsafe"):
        controller.start_training(
            frozen,
            model_label="Broken RF",
            model_id="model-rf-broken",
        )
    assert not (root / ".alpaca" / "models" / "model-rf-broken").exists()
