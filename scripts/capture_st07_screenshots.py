"""Capture genuine native ST-07 setup and CNN Result states on macOS."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from biocall_studio.detect.detection import DetectionSettings
from biocall_studio.detect.runs import DetectRunStatus
from biocall_studio.gui.app import create_application
from biocall_studio.gui.coordinator import StudioCoordinator
from biocall_studio.navigation import WorkspaceRoute
from biocall_studio_train.application.collection_scan import scan_collection
from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.domain.dataset import BuildConfig
from biocall_studio_train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio_train.persistence.collection_metadata import publish_collection_metadata
from biocall_studio_train.workflows.cnn_training import CnnTrainingRequest, train_cnn_model
from biocall_studio_train.workflows.dataset_build import build_dataset


def _wav(
    path: Path,
    *,
    frames: int,
    rate: int = 16_000,
    channels: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        for channel in range(channels):
            payload.extend(
                struct.pack("<h", ((frame * 97 + channel * 701) % 20_000) - 10_000)
            )
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)


def _model(root: Path):
    for index in range(3):
        stem = f"Dawn_{index + 1:02d}"
        _wav(root / "recordings" / f"{stem}.wav", frames=32_000)
        _wav(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call.wav",
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
        dataset_id="dataset-st07-evidence",
    )
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
    config = freeze_training_config(
        draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities(cuda=False, mps=False, cpu_count=8),
    )
    model = train_cnn_model(
        root,
        CnnTrainingRequest(
            run_id="run-st07-evidence",
            request_id="request-st07-evidence",
            collection_root=str(root),
            collection_id=scan.collection_id,
            config=config,
            model_id="model-st07-evidence",
            model_label="Alpaca call detector",
        ),
    )
    _wav(root / "recordings" / "Stereo_8k.wav", frames=6_125, rate=8_000, channels=2)
    _wav(root / "recordings" / "Unreadable_by_decoder.wav", frames=1, channels=2_048)
    return model


def _wait_until(predicate, *, timeout_ms: int = 120_000) -> None:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout_ms:
            raise TimeoutError("Timed out preparing native ST-07 evidence state.")
        QGuiApplication.processEvents()
        time.sleep(0.025)
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
        default=Path("docs/design/evidence/st-07-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=450)
    args = parser.parse_args(argv)
    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-07 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st07-", dir="/tmp") as temporary:
        root = Path(temporary)
        source = root / "Rainforest_2026"
        print("Preparing genuine Train CNN Model and real WAV fixtures...", flush=True)
        model = _model(source)
        print("Prepared genuine Model; opening native Detect workspace...", flush=True)
        coordinator = StudioCoordinator(
            WorkspaceController(root / "train-settings"),
            detect_data_dir=root / "studio-data",
        )
        coordinator.start()
        coordinator.open_workspace(WorkspaceRoute.DETECT)
        controller = coordinator.detect_controller
        controller._worker_step_delay_seconds = 0.15
        controller.choose_model_root(str(model.root))
        _wait_until(
            lambda: controller.model_reference is not None
            and not controller.is_model_loading
        )
        print("Accepted Model; scanning recording inventory...", flush=True)
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.inputs_ready)
        print("Accepted inventory; capturing setup states...", flush=True)
        page = coordinator.shell_window.detect_page
        page._set_route("setup")
        window = coordinator.shell_window
        window.move(60, 24)
        window.resize(1180, 790)
        _capture(
            window,
            args.output_dir / "setup-overview-normal.png",
            settle_ms=args.settle_ms,
        )
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        _capture(
            window,
            args.output_dir / "setup-settings-normal.png",
            settle_ms=args.settle_ms,
        )
        window.resize(700, 780)
        for _ in range(40):
            QGuiApplication.processEvents()
            time.sleep(0.025)
        print(
            "Compact geometry: "
            f"page={page.width()} content={page.content.width()} "
            f"compact={page.is_compact} horizontal-range="
            f"{page.horizontalScrollBar().maximum()} content-min="
            f"{page.content.minimumSizeHint().width()} setup-min="
            f"{page.setup_view.minimumSizeHint().width()} route-min="
            f"{page.route_stack.minimumSizeHint().width()}",
            flush=True,
        )
        _wait_until(
            lambda: page.is_compact and page.horizontalScrollBar().maximum() == 0
        )
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        _capture(
            window,
            args.output_dir / "setup-settings-compact.png",
            settle_ms=args.settle_ms,
        )

        window.resize(1180, 790)
        page._set_route("run")
        controller.start_detection(DetectionSettings(1.0, 50, 200, 16))
        print("Started real CNN detection Worker; capturing Run states...", flush=True)
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.RUNNING
            and controller.current_run.progress >= 10
        )
        _capture(
            window,
            args.output_dir / "run-cnn-running-normal.png",
            settle_ms=200,
        )
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.COMPLETED
        )
        if controller.current_result is None or controller.current_result.failed_files != 1:
            raise RuntimeError("Native ST-07 completion did not preserve the file failure.")
        window.resize(700, 780)
        _capture(
            window,
            args.output_dir / "run-result-partial-compact.png",
            settle_ms=args.settle_ms,
        )
        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
