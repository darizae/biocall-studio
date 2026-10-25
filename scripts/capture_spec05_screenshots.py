"""Capture Spec 05 Training, Run, and Model views from native macOS Cocoa."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from generate_example_collection import EXAMPLES, RATE, build_wave_bytes, write_wave
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.workflows.dataset_build import build_dataset


def _wait_until(predicate, *, timeout_ms: int = 20_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native Training configuration state.")
        QTest.qWait(20)


def _capture(
    window: QWidget,
    path: Path,
    *,
    settle_ms: int,
    foreground: QWidget | None = None,
) -> None:
    window.show()
    active = foreground or window
    active.raise_()
    active.activateWindow()
    QTest.qWait(settle_ms)
    origin = window.mapToGlobal(QPoint(0, 0))
    image = (
        window.windowHandle()
        .screen()
        .grabWindow(
            0,
            origin.x(),
            origin.y(),
            window.width(),
            window.height(),
        )
    )
    if image.isNull() or image.width() < 540 or image.height() < 300:
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


def _scroll_to_field(page, key: str, *, top_margin: int = 360) -> None:
    field = page.field_widgets[key]
    page.ensureWidgetVisible(field, 20, 100)
    QTest.qWait(100)
    y = field.mapTo(page.widget(), QPoint(0, 0)).y()
    page.verticalScrollBar().setValue(max(0, y - top_margin))
    QTest.qWait(100)


def _make_collection(root: Path) -> None:
    for source, start_ms, end_ms, label, period_a, period_b in EXAMPLES:
        frames = build_wave_bytes(period_a, period_b)
        write_wave(root / "recordings" / f"{source}.wav", frames, replace=False)
        start = start_ms * RATE // 1_000 * 2
        end = end_ms * RATE // 1_000 * 2
        write_wave(
            root
            / "positives"
            / f"{source}__start-{start_ms:05d}ms__end-{end_ms:05d}ms__{label}.wav",
            frames[start:end],
            replace=False,
        )


def _build_training_dataset(controller: WorkspaceController, root: Path):
    _wait_until(lambda: controller.scan_result is not None and not controller.is_scanning)
    scan = controller.scan_result
    if scan is None:
        raise RuntimeError("Collection Scan did not produce a result.")
    config = BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=250,
    )
    return build_dataset(root, scan, config, dataset_id="dataset-training-evidence")


def _capture_delete_confirmation(
    app, window: MainWindow, output: Path, preset_id: str, settle_ms: int
) -> None:
    captured = False

    def capture_and_cancel() -> None:
        nonlocal captured
        message = next(
            (widget for widget in app.topLevelWidgets() if isinstance(widget, QMessageBox)),
            None,
        )
        if message is None:
            QTimer.singleShot(50, capture_and_cancel)
            return
        _capture(window, output, settle_ms=settle_ms)
        captured = True
        message.done(QMessageBox.StandardButton.No.value)

    QTimer.singleShot(100, capture_and_cancel)
    window.training_page.delete_preset(preset_id)
    if not captured:
        raise RuntimeError("Preset delete confirmation was not captured.")


def _name_and_start_model(
    app,
    window: MainWindow,
    output: Path,
    settle_ms: int,
) -> str:
    captured = False

    def capture_and_accept() -> None:
        nonlocal captured
        dialog = next(
            (widget for widget in app.topLevelWidgets() if isinstance(widget, QInputDialog)),
            None,
        )
        if dialog is None:
            QTimer.singleShot(50, capture_and_accept)
            return
        dialog.setTextValue("Field evidence CNN")
        _capture(window, output, settle_ms=settle_ms, foreground=dialog)
        captured = True
        dialog.accept()

    QTimer.singleShot(100, capture_and_accept)
    window.training_page.start_button.click()
    if not captured or window.controller.active_run is None:
        raise RuntimeError("Model naming or CNN Training launch was not captured.")
    return window.controller.active_run.run_id


def _capture_showcase(output: Path, settle_ms: int) -> None:
    gallery = Path(__file__).resolve().parents[2] / "alp-ui" / "gallery"
    sys.path.insert(0, str(gallery))
    from showcase import build_showcase

    showcase = build_showcase()
    showcase.move(60, 24)
    showcase.resize(1180, 790)
    _capture(showcase, output, settle_ms=settle_ms)
    showcase.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/spec-05-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=700)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 05a evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')}"
    )

    with tempfile.TemporaryDirectory(prefix="alpaca-spec05-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec05Example"
        _make_collection(root)
        controller = WorkspaceController(temporary_root / "application-settings")
        window = MainWindow(controller)
        window.resize(1280, 900)
        window.move(60, 24)
        window.show()
        QTest.qWait(args.settle_ms)
        window.select_page.folder_picker.setFolderPath(str(root))
        dataset = _build_training_dataset(controller, root)
        window.open_training(dataset.dataset_id)
        page = window.training_page
        _capture(window, args.output_dir / "train-cnn.png", settle_ms=args.settle_ms)

        page.family_input.setCurrentIndex(1)
        _capture(window, args.output_dir / "train-rf.png", settle_ms=args.settle_ms)
        page.more_settings.setChecked(True)
        page.open_detail_section("Forest")
        page.set_field_value("random_state", 2026)
        _scroll_to_field(page, "random_state")
        _capture(window, args.output_dir / "train-rf-advanced.png", settle_ms=args.settle_ms)

        page.family_input.setCurrentIndex(0)
        page.more_settings.setChecked(True)
        page.open_detail_section("Spectrogram")
        page.set_field_value("spectrogram.n_fft", 2048)
        _scroll_to_field(page, "spectrogram.n_fft")
        _capture(window, args.output_dir / "train-cnn-advanced.png", settle_ms=args.settle_ms)

        preset = page.save_preset_as("Field laptop")
        page.open_preset_manager()
        _wait_until(lambda: page.manage_dialog is not None and page.manage_dialog.isVisible())
        _capture(
            window,
            args.output_dir / "presets-list.png",
            settle_ms=args.settle_ms,
            foreground=page.manage_dialog,
        )
        page.manage_dialog.close()
        page.set_field_value("training.batch_size", 32)
        page.more_settings.setChecked(False)
        _capture(window, args.output_dir / "presets-unsaved.png", settle_ms=args.settle_ms)
        _capture_delete_confirmation(
            app,
            window,
            args.output_dir / "presets-confirm-delete.png",
            preset.preset_id,
            args.settle_ms,
        )

        page.more_settings.setChecked(True)
        page.open_detail_section("Spectrogram")
        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and page._compact)
        page.field_controls["spectrogram.n_fft"].control.setFocus()
        _scroll_to_field(page, "spectrogram.n_fft", top_margin=310)
        _capture(
            window,
            args.output_dir / "train-cnn-narrow-focus.png",
            settle_ms=args.settle_ms,
        )

        window.resize(1280, 900)
        _wait_until(lambda: not window.is_compact and not page._compact)
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
            page.set_field_value(key, value)
        page.more_settings.setChecked(False)
        page.verticalScrollBar().setValue(0)
        run_id = _name_and_start_model(
            app,
            window,
            args.output_dir / "model-name.png",
            args.settle_ms,
        )
        _wait_until(
            lambda: any(run.run_id == run_id and run.terminal for run in controller.runs),
            timeout_ms=180_000,
        )
        completed = next(run for run in controller.runs if run.run_id == run_id)
        if completed.status.value != "completed":
            raise RuntimeError(f"CNN Training evidence Run failed: {completed.error}")

        window.open_run(run_id)
        window.run_detail_page.ensureWidgetVisible(
            window.run_detail_page.training_plot,
            20,
            180,
        )
        _capture(
            window,
            args.output_dir / "run-cnn-plot.png",
            settle_ms=args.settle_ms,
        )
        window.navigate("models")
        _capture(window, args.output_dir / "models.png", settle_ms=args.settle_ms)
        window.open_model(completed.output_id)
        _capture(window, args.output_dir / "model-detail.png", settle_ms=args.settle_ms)
        window.resize(700, 780)
        _wait_until(
            lambda: window.is_compact and window.model_detail_page.is_compact,
        )
        _capture(
            window,
            args.output_dir / "model-detail-narrow.png",
            settle_ms=args.settle_ms,
        )
        window.close()

    _capture_showcase(args.output_dir / "alp-ui-showcase-current.png", args.settle_ms)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
