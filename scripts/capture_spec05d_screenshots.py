"""Capture Spec 05d local diagnostics additions from native macOS Cocoa."""

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
from PySide6.QtWidgets import QMessageBox, QWidget

from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.gui.window import MainWindow


def _wait_until(predicate, *, timeout_ms: int = 30_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native diagnostics evidence state.")
        QTest.qWait(20)


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


def _capture_export_confirmation(
    app, window: MainWindow, output: Path, settle_ms: int
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
    window.settings_page.export_diagnostics_button.click()
    if not captured:
        raise RuntimeError("Diagnostics privacy confirmation was not captured.")


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
        default=Path("docs/design/evidence/spec-05d-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=700)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 05d evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')}"
    )

    with tempfile.TemporaryDirectory(
        prefix="biocall-studio-spec05d-", dir="/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec05dExample"
        _make_collection(root)
        controller = WorkspaceController(
            temporary_root / "application-settings",
            worker_step_delay_seconds=0.08,
        )
        window = MainWindow(controller)
        window.resize(1280, 900)
        window.move(60, 24)
        window.show()
        QTest.qWait(args.settle_ms)
        window.select_page.folder_picker.setFolderPath(str(root))
        _wait_until(lambda: controller.scan_result is not None and not controller.is_scanning)
        scan = controller.scan_result
        if scan is None:
            raise RuntimeError("Collection Scan did not produce evidence inputs.")
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
        run_id = controller.start_dataset_build(config, dataset_id="dataset-diagnostics-evidence")
        _wait_until(lambda: controller.active_run is None)

        window.open_run(run_id)
        window.run_detail_page.ensureWidgetVisible(window.run_detail_page.activity, 20, 180)
        _capture(window, args.output_dir / "run-open-log.png", settle_ms=args.settle_ms)

        window.navigate("settings")
        window.settings_page.ensureWidgetVisible(
            window.settings_page.diagnostics_card,
            20,
            180,
        )
        _capture(window, args.output_dir / "settings-diagnostics.png", settle_ms=args.settle_ms)
        _capture_export_confirmation(
            app,
            window,
            args.output_dir / "export-privacy-confirmation.png",
            args.settle_ms,
        )

        window.open_run(run_id)
        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and window.run_detail_page.is_compact)
        window.run_detail_page.verticalScrollBar().setValue(0)
        _capture(window, args.output_dir / "run-open-log-narrow.png", settle_ms=args.settle_ms)

        window.navigate("settings")
        _wait_until(lambda: window.settings_page.is_compact)
        window.settings_page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "settings-stacked-narrow.png",
            settle_ms=args.settle_ms,
        )
        window.settings_page.ensureWidgetVisible(
            window.settings_page.diagnostics_card,
            20,
            120,
        )
        window.settings_page.verticalScrollBar().setValue(
            window.settings_page.verticalScrollBar().maximum()
        )
        _capture(
            window,
            args.output_dir / "settings-diagnostics-narrow.png",
            settle_ms=args.settle_ms,
        )
        window.close()

    _capture_showcase(args.output_dir / "alp-ui-showcase-current.png", args.settle_ms)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
