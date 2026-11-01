from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import textwrap
import wave
from dataclasses import dataclass
from pathlib import Path

import pytest
from alp_ui.components import HelpHint
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QPushButton

from biocall_studio.detect.application.controller import DetectWorkspaceController, ModelIntakeState
from biocall_studio.detect.application.model_intake import inspect_model_directory
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.detect.domain.models import (
    ModelFamily,
    ScientificEvidenceState,
)
from biocall_studio.detect.gui.workspace import DetectWorkspacePage
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio.train.persistence.models import ModelArtifact
from biocall_studio.train.workflows.cnn_training import CnnTrainingRequest, train_cnn_model
from biocall_studio.train.workflows.dataset_build import build_dataset
from biocall_studio.train.workflows.rf_training import RfTrainingRequest, train_rf_model

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class _Exports:
    collection_root: Path
    cnn: ModelArtifact
    rf: ModelArtifact
    source_bytes: dict[str, bytes]


def _write_wav(path: Path, *, frames: int, rate: int = 16_000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        payload.extend(struct.pack("<h", ((frame * 97) % 20_000) - 10_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)
    return path


def _cnn_draft() -> TrainingDraft:
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


def _rf_draft() -> TrainingDraft:
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
    }.items():
        draft.set(key, value)
    return draft


@pytest.fixture(scope="module")
def genuine_exports(tmp_path_factory) -> _Exports:
    root = tmp_path_factory.mktemp("st05-genuine-exports") / "collection"
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        _write_wav(root / "recordings" / f"{stem}.wav", frames=32_000)
        _write_wav(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call{index}.wav",
            frames=8_000,
        )
    scan = publish_collection_metadata(root, scan_collection(root))
    dataset = build_dataset(
        root,
        scan,
        BuildConfig(
            selected_recording_ids=tuple(record.id for record in scan.records),
            negative_mode="ratio",
            negative_ratio=1.0,
            negative_count=0,
            allocation="proportional",
            train_percent=80,
            balance_classes=True,
            seed=42,
            margin_ms=100,
        ),
        dataset_id="dataset-detect-model-intake",
    )
    training_dataset = TrainingDataset.from_artifact(dataset)
    capabilities = DeviceCapabilities(cuda=False, mps=False, cpu_count=8)
    cnn_config = freeze_training_config(_cnn_draft(), training_dataset, capabilities)
    rf_config = freeze_training_config(_rf_draft(), training_dataset, capabilities)
    source_bytes = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    cnn = train_cnn_model(
        root,
        CnnTrainingRequest(
            run_id="run-detect-intake-cnn",
            request_id="request-detect-intake-cnn",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=cnn_config,
            model_id="model-detect-intake-cnn",
            model_label="Genuine Detect intake CNN",
        ),
    )
    rf = train_rf_model(
        root,
        RfTrainingRequest(
            run_id="run-detect-intake-rf",
            request_id="request-detect-intake-rf",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=rf_config,
            model_id="model-detect-intake-rf",
            model_label="Genuine Detect intake RF",
        ),
    )
    assert source_bytes == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (root / folder).iterdir()
    }
    return _Exports(root, cnn, rf, source_bytes)


def _copy_model_collection(source: _Exports, artifact: ModelArtifact, target: Path) -> Path:
    alpaca = target / ".alpaca"
    (alpaca / "models").mkdir(parents=True)
    shutil.copy2(source.collection_root / ".alpaca" / "collection.json", alpaca)
    destination = alpaca / "models" / artifact.model_id
    shutil.copytree(artifact.root, destination)
    return destination


def test_genuine_train_exports_inspect_in_fresh_process_with_installed_toolbox_wheel(
    genuine_exports, tmp_path
):
    """Case: IT-DET-006."""
    wheels = tmp_path / "wheels"
    runtime = tmp_path / "runtime"
    wheels.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheels),
            str(Path(__file__).resolve().parents[3] / "bioacoustics-dl-toolbox"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel_path = next(wheels.glob("bioacoustics_dl_toolbox-*.whl"))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(runtime),
            str(wheel_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    code = textwrap.dedent(
        """
        import json
        import sys
        import bioacoustics_dl_toolbox
        from pathlib import Path
        from biocall_studio.detect.application.model_intake import inspect_model_directory

        snapshots = [
            inspect_model_directory(Path(path)).snapshot.to_dict()
            for path in sys.argv[1:]
        ]
        print(json.dumps({"origin": bioacoustics_dl_toolbox.__file__, "snapshots": snapshots}))
        """
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(runtime), str(Path(__file__).resolve().parents[2] / "src"))
    )
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code, str(genuine_exports.cnn.root), str(genuine_exports.rf.root)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    result = json.loads(completed.stdout)
    assert Path(result["origin"]).is_relative_to(runtime)
    assert [item["family"] for item in result["snapshots"]] == ["cnn", "random_forest"]
    assert all(item["structure"] == "passed" for item in result["snapshots"])
    assert all(item["runtime_loadable"] == "passed" for item in result["snapshots"])
    assert all(item["prediction_parity"] == "unproven" for item in result["snapshots"])
    assert genuine_exports.source_bytes == {
        path.relative_to(genuine_exports.collection_root).as_posix(): path.read_bytes()
        for folder in ("recordings", "positives")
        for path in (genuine_exports.collection_root / folder).iterdir()
    }


@pytest.mark.parametrize(
    "case",
    (
        "missing",
        "corrupt",
        "checksum-swapped",
        "extra-class",
        "feature-order",
        "unsupported-runtime",
        "unsafe-path",
        "untrusted",
    ),
)
def test_invalid_or_untrusted_genuine_exports_are_denied(genuine_exports, tmp_path, case):
    """Case: IT-DET-007."""
    artifact = genuine_exports.rf if case == "feature-order" else genuine_exports.cnn
    root = _copy_model_collection(genuine_exports, artifact, tmp_path / case)
    manifest_path = root / "model.json"
    manifest = json.loads(manifest_path.read_text())
    binary = root / manifest["artifact"]["path"]

    if case == "missing":
        binary.unlink()
    elif case == "corrupt":
        payload = binary.read_bytes()
        binary.write_bytes(bytes([payload[0] ^ 0xFF]) + payload[1:])
    elif case == "checksum-swapped":
        other_binary = genuine_exports.rf.root / "random_forest.joblib"
        shutil.copy2(other_binary, binary)
        manifest["artifact"]["size_bytes"] = binary.stat().st_size
        from biocall_studio.shared.integrity import sha256_file

        manifest["artifact"]["sha256"] = sha256_file(binary)
        manifest_path.write_text(json.dumps(manifest))
    elif case == "extra-class":
        manifest["task"]["class_to_index"] = {"noise": 0, "target": 1, "other": 2}
        manifest_path.write_text(json.dumps(manifest))
    elif case == "feature-order":
        names = manifest["random_forest"]["features"]["names"]
        names[0], names[1] = names[1], names[0]
        manifest_path.write_text(json.dumps(manifest))
    elif case == "unsupported-runtime":
        manifest["provenance"]["torch_version"] = "0.0.0"
        manifest_path.write_text(json.dumps(manifest))
    elif case == "unsafe-path":
        manifest["artifact"]["path"] = "../outside.pt"
        manifest_path.write_text(json.dumps(manifest))
    elif case == "untrusted":
        untrusted = tmp_path / "download" / root.name
        untrusted.parent.mkdir()
        root.rename(untrusted)
        root = untrusted

    with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
        inspect_model_directory(root)


@pytest.mark.qt
def test_native_model_selection_reopen_states_and_readiness_without_worker(
    qapp, qtbot, genuine_exports, tmp_path, monkeypatch
):
    """Case: IT-DET-008."""
    cnn_root = _copy_model_collection(genuine_exports, genuine_exports.cnn, tmp_path / "cnn")
    rf_root = _copy_model_collection(genuine_exports, genuine_exports.rf, tmp_path / "rf")
    app_data = tmp_path / "application-data"
    controller = DetectWorkspaceController(app_data, model_step_delay_seconds=0.05)
    page = DetectWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(1180, 790)
    page.show()

    assert controller.model_state is ModelIntakeState.EMPTY
    assert page.model_status_badge.text() == "Not selected"
    page.model_picker.folderChanged.emit(str(cnn_root))
    assert controller.model_state is ModelIntakeState.LOADING
    qtbot.waitUntil(lambda: controller.model_state is ModelIntakeState.COMPATIBLE, timeout=30_000)
    assert controller.model_reference is not None
    assert controller.model_reference.snapshot.family is ModelFamily.CNN
    assert controller.model_reference.snapshot.prediction_parity is (
        ScientificEvidenceState.UNPROVEN
    )
    assert page.model_status_badge.text() == "Compatible"
    assert page.model_status_badge.intent == "success"
    assert not page.model_detail.isVisible()
    assert page.model_picker.folderPath() == str(cnn_root.resolve())

    page.folder_picker.folderChanged.emit(str(genuine_exports.collection_root))
    qtbot.waitUntil(lambda: controller.snapshot is not None, timeout=30_000)
    assert controller.inputs_ready
    assert not hasattr(page, "readiness_card")
    assert page.start_detection_button.isEnabled()
    assert controller.current_run is None

    assert any(
        hint.accessibleName() == "More about Detection Model"
        for hint in page.findChildren(HelpHint)
    )
    page.resize(700, 780)
    qtbot.waitUntil(lambda: page.is_compact)
    assert page.models_layout.getItemPosition(page.models_layout.indexOf(page.model_card))[:2] == (
        0,
        0,
    )
    assert page.models_layout.getItemPosition(
        page.models_layout.indexOf(page.refinement_model_card)
    )[:2] == (1, 0)
    page._navigation[DetectRoute.RECORDINGS].click()
    assert page.current_route is DetectRoute.RECORDINGS
    assert page.collection_card.isVisible()

    before = controller.model_reference
    monkeypatch.setattr(QFileDialog, "exec", lambda *_args, **_kwargs: 0)
    browse = next(
        button
        for button in page.model_picker.findChildren(QPushButton)
        if button.accessibleName() == "Choose Train Model folder"
    )
    qtbot.mouseClick(browse, Qt.MouseButton.LeftButton)
    assert controller.model_reference == before
    assert controller.wait_for_model(30_000)

    reopened_controller = DetectWorkspaceController(app_data, model_step_delay_seconds=0.05)
    reopened_page = DetectWorkspacePage(reopened_controller)
    qtbot.addWidget(reopened_page)
    reopened_page.show()
    assert reopened_controller.model_state is ModelIntakeState.LOADING
    qtbot.waitUntil(
        lambda: reopened_controller.model_state is ModelIntakeState.COMPATIBLE,
        timeout=30_000,
    )
    assert reopened_controller.model_reference.snapshot == before.snapshot

    moved = cnn_root.with_name("model-moved-away")
    cnn_root.rename(moved)
    reopened_controller.refresh()
    qtbot.waitUntil(
        lambda: reopened_controller.model_state is ModelIntakeState.MISSING,
        timeout=30_000,
    )
    assert "choose" in reopened_page.model_detail.text().lower()

    reopened_page.model_picker.folderChanged.emit(str(rf_root))
    qtbot.waitUntil(
        lambda: reopened_controller.model_state is ModelIntakeState.INCOMPATIBLE,
        timeout=30_000,
    )
    assert reopened_controller.model_reference is not None
    assert reopened_controller.model_reference.snapshot.family is ModelFamily.RANDOM_FOREST
    assert reopened_page.model_detail.text() == (
        "This folder does not contain a compatible BioCall Studio model. "
        "Choose a different model folder."
    )
    assert not reopened_controller.inputs_ready

    empty_collection = tmp_path / "empty" / ".alpaca"
    empty_model = empty_collection / "models" / "empty-model"
    empty_model.mkdir(parents=True)
    shutil.copy2(
        genuine_exports.collection_root / ".alpaca" / "collection.json",
        empty_collection / "collection.json",
    )
    reopened_page.model_picker.folderChanged.emit(str(empty_model))
    qtbot.waitUntil(
        lambda: reopened_controller.model_state is ModelIntakeState.INCOMPATIBLE,
        timeout=30_000,
    )
    assert "model information" not in reopened_page.model_detail.text().lower()
    assert reopened_page.model_detail.text() == (
        "This folder does not contain a compatible BioCall Studio model. "
        "Choose a different model folder."
    )
    assert reopened_controller.wait_for_model(30_000)
