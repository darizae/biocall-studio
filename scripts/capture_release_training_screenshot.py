"""Capture a visible active CNN Run with measured real-hum loss curves."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.run import RunStatus
from biocall_studio.train.domain.training import (
    DeviceCapabilities,
    TrainingDataset,
    TrainingDraft,
    freeze_training_config,
)
from biocall_studio.train.gui.window import MainWindow
from biocall_studio.train.persistence.collection_metadata import load_collection_metadata
from biocall_studio.train.persistence.datasets import list_datasets
from biocall_studio.train.workflows.dataset_build import build_dataset

DEFAULT_COLLECTION = Path("work/release-evidence/Verified Alpaca Hums")
DEFAULT_APP_DATA = Path("work/release-evidence/training-capture-app-data")
DEFAULT_OUTPUT = Path("docs/design/evidence/release-real-data")
SCREENSHOT_NAME = "02a-train-training-in-progress.png"
METADATA_NAME = "training-capture-metadata.json"
DATASET_ID = "dataset-release-real-hums-seed0"


def _wait_until(predicate, *, timeout_ms: int, interval_ms: int = 25) -> None:
    remaining = timeout_ms
    while remaining > 0:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(interval_ms)
        remaining -= interval_ms
    raise TimeoutError("The active Training release state did not become ready in time.")


def _set_viewport(window: QWidget, width: int = 1280, height: int = 807) -> None:
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for native release capture.")
    available = screen.availableGeometry()
    if width > available.width() or height > available.height():
        raise RuntimeError("The requested release viewport does not fit the active display.")
    window.resize(width, height)
    window.move(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(500)


def _capture(window: QWidget, target: Path) -> tuple[int, int]:
    window.raise_()
    window.activateWindow()
    QApplication.processEvents()
    QTest.qWait(450)
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for native release capture.")
    origin = window.mapToGlobal(QPoint(0, 0))
    pixmap = screen.grabWindow(
        0,
        origin.x(),
        origin.y(),
        window.width(),
        window.height(),
    )
    if pixmap.isNull() or not pixmap.save(str(target), "PNG"):
        raise RuntimeError(f"Could not capture {target}.")
    print(f"Captured {target.name}: {pixmap.width()}x{pixmap.height()}")
    return pixmap.width(), pixmap.height()


def _reset_app_data(root: Path) -> None:
    resolved = root.resolve(strict=False)
    allowed = Path("work/release-evidence").resolve(strict=False)
    if not resolved.is_relative_to(allowed) or resolved == allowed:
        raise ValueError("Training capture reset is restricted to a named folder under work/.")
    if resolved.exists():
        shutil.rmtree(resolved)


def _dataset(collection: Path):
    existing = next(
        (item for item in list_datasets(collection) if item.dataset_id == DATASET_ID),
        None,
    )
    if existing is not None:
        return existing
    scan = load_collection_metadata(collection)
    if not scan.valid:
        raise RuntimeError("The verified real-hum Collection is no longer valid.")
    config = BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=0,
        margin_ms=250,
    )
    return build_dataset(collection, scan, config, dataset_id=DATASET_ID)


def _training_config(dataset):
    draft = TrainingDraft.defaults("cnn")
    for key, value in {
        "run_name": "Train CNN · Verified Alpaca Hums",
        "sequence_length_ms": 250,
        "training.max_epochs": 48,
        "training.batch_size": 8,
        "training.learning_rate": 0.0001,
        "training.early_stopping_patience_epochs": 100,
        "training.lr_patience_epochs": 100,
        "training.epochs_per_eval": 1,
        "device": "cpu",
        "spectrogram.sample_rate": 16_000,
        "spectrogram.n_fft": 256,
        "spectrogram.hop_length": 64,
        "spectrogram.n_freq_bins": 64,
        "spectrogram.f_min": 100,
        "spectrogram.f_max": 7_000,
        "training.num_workers": 0,
        "training.pin_memory": False,
        "augmentation.enabled": False,
    }.items():
        draft.set(key, value)
    return freeze_training_config(
        draft,
        TrainingDataset.from_artifact(dataset),
        DeviceCapabilities.detect(),
    )


def _losses(run, phase: str) -> list[tuple[int, float]]:
    return [
        (int(row["epoch"]), float(row["loss"]))
        for row in run.measurements
        if row.get("phase") == phase
    ]


def _trend_ready(controller: WorkspaceController) -> bool:
    run = controller.active_run
    if run is None or run.status is not RunStatus.RUNNING:
        return False
    train = _losses(run, "train")
    val = _losses(run, "val")
    return (
        len(train) >= 4 and len(val) >= 4 and train[-1][1] < train[0][1] and val[-1][1] < val[0][1]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--app-data", type=Path, default=DEFAULT_APP_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    collection = args.collection.resolve(strict=True)
    app_data = args.app_data.resolve(strict=False)
    output = args.output_dir.resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / SCREENSHOT_NAME
    metadata_path = output / METADATA_NAME
    if (screenshot.exists() or metadata_path.exists()) and not args.replace:
        parser.error("Training release evidence already exists; pass --replace deliberately")
    _reset_app_data(app_data)

    metadata = load_collection_metadata(collection)
    dataset = _dataset(collection)
    config = _training_config(dataset)
    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Release screenshots must be captured by visible native macOS Cocoa.")

    controller = WorkspaceController(app_data, worker_step_delay_seconds=0.1)
    controller.bind_verified_collection(collection, metadata.collection_id)
    window = MainWindow(controller)
    _set_viewport(window)
    run_id: str | None = None
    captured_run = None
    try:
        run_id = controller.start_training(
            config,
            model_label="Verified Alpaca Hums CNN",
            model_id=f"model-release-capture-{uuid.uuid4().hex}",
        )
        window.open_run(run_id)
        _wait_until(lambda: _trend_ready(controller), timeout_ms=100_000)
        captured_run = controller.active_run
        if captured_run is None:
            raise RuntimeError("Training completed before its active release state was captured.")
        window.open_run(run_id)
        _wait_until(
            lambda: (
                window.run_detail_page.run is not None
                and window.run_detail_page.run.run_id == run_id
                and _trend_ready(controller)
            ),
            timeout_ms=5_000,
        )
        window.run_detail_page.verticalScrollBar().setValue(0)
        QApplication.processEvents()
        png_width, png_height = _capture(window, screenshot)

        train = _losses(captured_run, "train")
        val = _losses(captured_run, "val")
        evidence = {
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "capture_mode": "visible Cocoa QScreen capture of a live PySide6 window",
            "status_at_capture": captured_run.status.value,
            "current_stage_at_capture": captured_run.current_stage,
            "progress_at_capture": captured_run.progress,
            "run_id": run_id,
            "dataset_id": dataset.dataset_id,
            "collection_id": metadata.collection_id,
            "source_recordings": metadata.recording_count,
            "positive_examples": metadata.positive_count,
            "train_loss": [{"epoch": epoch, "loss": loss} for epoch, loss in train],
            "val_loss": [{"epoch": epoch, "loss": loss} for epoch, loss in val],
            "logical_viewport": [window.width(), window.height()],
            "png_pixels": [png_width, png_height],
            "qt_platform": app.platformName(),
        }
        metadata_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        if controller.active_run is not None:
            controller.cancel_active_run()
            try:
                _wait_until(lambda: controller.active_run is None, timeout_ms=15_000)
            except TimeoutError:
                pass
        window.close()
        controller.shutdown()
        app.processEvents()

    if captured_run is None:
        raise RuntimeError("No active Training state was captured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
