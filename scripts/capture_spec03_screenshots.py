"""Capture Spec 03 Dataset Builder and Dataset views from native macOS Cocoa."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from generate_example_collection import EXAMPLES, RATE, build_wave_bytes, write_wave
from PySide6.QtCore import QElapsedTimer, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import MainWindow


def _wait_until(predicate, *, timeout_ms: int = 20_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native Dataset Build state.")
        QTest.qWait(20)


def _capture(window: MainWindow, path: Path, *, settle_ms: int) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    print(
        f"Capturing {path.name}: size={window.width()}x{window.height()} "
        f"position={window.x()},{window.y()}"
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/spec-03-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=1_000)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 03 evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="biocall-studio-train-spec03-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec03Example"
        _make_collection(root)
        controller = WorkspaceController(temporary_root / "application-settings")
        window = MainWindow(controller)
        window.resize(1280, 900)
        window.move(60, 24)
        window.show()
        QTest.qWait(args.settle_ms)
        window.windowHandle().screen().grabWindow(int(window.winId()))
        QTest.qWait(args.settle_ms)
        window.select_page.folder_picker.setFolderPath(str(root))
        _wait_until(lambda: controller.scan_result is not None and not controller.is_scanning)
        window.collection_page.build_button.click()
        _wait_until(lambda: window.current_route == "builder")
        _capture(window, args.output_dir / "builder.png", settle_ms=args.settle_ms)

        builder = window.builder_page
        builder.negative_amount.setValue(20)
        builder.margin.setCurrentIndex(builder.margin.count() - 1)
        _wait_until(lambda: builder.preview_alert.isVisible())
        _capture(window, args.output_dir / "builder-underfill.png", settle_ms=args.settle_ms)

        builder.negative_amount.setValue(2)
        builder.margin.setCurrentIndex(1)
        _wait_until(lambda: builder.build_button.isEnabled())
        builder.build_button.click()
        if not builder.build_button.isLoading():
            raise RuntimeError("Dataset Build did not enter the native busy state.")
        _capture(window, args.output_dir / "builder-busy.png", settle_ms=20)
        _wait_until(lambda: controller.active_run is None)
        window.run_detail_page.open_output_button.click()
        _wait_until(lambda: window.current_route == "dataset-detail")
        _capture(window, args.output_dir / "dataset-detail.png", settle_ms=args.settle_ms)

        window.navigate("datasets")
        window.resize(1280, 900)
        _capture(window, args.output_dir / "datasets.png", settle_ms=args.settle_ms)
        window.open_builder()
        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and window.builder_page.is_compact)
        _capture(window, args.output_dir / "builder-narrow.png", settle_ms=args.settle_ms)
        window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
