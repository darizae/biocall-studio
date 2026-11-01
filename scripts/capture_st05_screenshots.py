"""Capture ST-05 Model intake states from visible native macOS windows."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import shutil
import struct
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from biocall_studio.detect.application.controller import ModelIntakeState
from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
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


@dataclass(frozen=True)
class _Exports:
    collection_root: Path
    cnn: ModelArtifact
    rf: ModelArtifact


def _wav(path: Path, *, frames: int, rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        payload.extend(struct.pack("<h", ((frame * 97) % 20_000) - 10_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)


def _draft(family: str) -> TrainingDraft:
    draft = TrainingDraft.defaults(family)
    values = (
        {
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
        }
        if family == "cnn"
        else {
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
        }
    )
    for key, value in values.items():
        draft.set(key, value)
    return draft


def _train_exports(root: Path) -> _Exports:
    for index in range(3):
        stem = f"REC_{chr(ord('A') + index)}"
        _wav(root / "recordings" / f"{stem}.wav", frames=32_000)
        _wav(
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
        dataset_id="dataset-st05-evidence",
    )
    facts = TrainingDataset.from_artifact(dataset)
    capabilities = DeviceCapabilities(cuda=False, mps=False, cpu_count=8)
    cnn = train_cnn_model(
        root,
        CnnTrainingRequest(
            run_id="run-st05-evidence-cnn",
            request_id="request-st05-evidence-cnn",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=freeze_training_config(_draft("cnn"), facts, capabilities),
            model_id="model-st05-evidence-cnn",
            model_label="Rainforest calls CNN",
        ),
    )
    rf = train_rf_model(
        root,
        RfTrainingRequest(
            run_id="run-st05-evidence-rf",
            request_id="request-st05-evidence-rf",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=freeze_training_config(_draft("rf"), facts, capabilities),
            model_id="model-st05-evidence-rf",
            model_label="Rainforest interval refinement",
        ),
    )
    return _Exports(root, cnn, rf)


def _copy_model(exports: _Exports, artifact: ModelArtifact, root: Path) -> Path:
    alpaca = root / ".alpaca"
    (alpaca / "models").mkdir(parents=True)
    shutil.copy2(exports.collection_root / ".alpaca" / "collection.json", alpaca)
    destination = alpaca / "models" / artifact.model_id
    shutil.copytree(artifact.root, destination)
    return destination


def _wait_until(predicate, *, timeout_ms: int = 30_000) -> None:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout_ms:
            raise TimeoutError("Timed out preparing native ST-05 evidence state.")
        QTest.qWait(25)
        elapsed += 25


def _capture(window: QWidget, path: Path, *, settle_ms: int) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    origin = window.mapToGlobal(QPoint(0, 0))
    image = (
        window.windowHandle()
        .screen()
        .grabWindow(0, origin.x(), origin.y(), window.width(), window.height())
    )
    if image.isNull() or image.width() < 640 or image.height() < 600:
        raise RuntimeError(f"Native capture failed or was unexpectedly small: {path}")
    if image.size() != window.size():
        image = image.scaled(
            window.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save native screenshot: {path}")
    print(f"Captured {path.name}: {image.width()}x{image.height()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/st-05-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=450)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-05 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    captures = (
        ("empty", 1180, 790),
        ("loading", 1180, 790),
        ("compatible", 1180, 790),
        ("compatible", 700, 780),
        ("incompatible-rf", 1180, 790),
        ("missing", 700, 780),
    )
    with tempfile.TemporaryDirectory(prefix="biocall-studio-st05-", dir="/tmp") as temporary:
        base = Path(temporary)
        exports = _train_exports(base / "train-collection")
        for index, (state, width, height) in enumerate(captures):
            root = base / f"{index:02d}-{state}"
            coordinator = StudioCoordinator(
                WorkspaceController(root / "train-settings"),
                detect_data_dir=root / "studio-data",
            )
            coordinator.start()
            coordinator.open_workspace(WorkspaceRoute.DETECT)
            controller = coordinator.detect_controller
            if state != "empty":
                controller.choose_source_root(str(exports.collection_root))
                _wait_until(lambda: controller.snapshot is not None and not controller.is_scanning)
                artifact = exports.rf if state == "incompatible-rf" else exports.cnn
                model_root = _copy_model(exports, artifact, root / "model-source")
                if state == "loading":
                    controller._model_step_delay_seconds = 2.0
                controller.choose_model_root(str(model_root))
                if state == "loading":
                    _wait_until(lambda: controller.model_state is ModelIntakeState.LOADING)
                else:
                    if not controller.wait_for_model(30_000):
                        raise TimeoutError("Model intake did not finish for native capture.")
                    QTest.qWait(100)
                    expected = (
                        ModelIntakeState.INCOMPATIBLE
                        if state == "incompatible-rf"
                        else ModelIntakeState.COMPATIBLE
                    )
                    if controller.model_state is not expected:
                        raise RuntimeError(
                            f"Unexpected Model state {controller.model_state}: "
                            f"{controller.model_reason}"
                        )
                if state == "missing":
                    model_root.rename(model_root.with_name("model-moved-away"))
                    controller.refresh()
                    if not controller.wait_for_model(30_000):
                        raise TimeoutError("Missing Model recheck did not finish.")
                    QTest.qWait(100)
                    if controller.model_state is not ModelIntakeState.MISSING:
                        raise RuntimeError(controller.model_reason)
            coordinator.shell_window.detect_page._set_route("setup")
            window = coordinator.shell_window
            window.resize(width, height)
            window.move(60, 24)
            size = "compact" if width < 760 else "normal"
            _capture(
                window,
                args.output_dir / f"model-{state}-{size}.png",
                settle_ms=args.settle_ms,
            )
            if state == "loading":
                if not controller.wait_for_model(30_000):
                    raise TimeoutError("Model intake did not finish after loading capture.")
                QTest.qWait(100)
            else:
                _wait_until(lambda: not controller.is_model_loading)
            coordinator.request_application_exit()
            QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
