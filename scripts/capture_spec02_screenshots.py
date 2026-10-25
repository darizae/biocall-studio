"""Capture the required Spec 02 views from a visible native macOS window."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from generate_example_collection import build_wave_bytes, write_wave
from PySide6.QtCore import QElapsedTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.window import MainWindow


def _wait_until(predicate, *, timeout_ms: int = 10_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native Collection Scan state.")
        QTest.qWait(20)


def _capture(window: MainWindow, path: Path, *, settle_ms: int) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    image = window.windowHandle().screen().grabWindow(int(window.winId()))
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


def _make_repairable_collection(root: Path) -> tuple[Path, Path]:
    frames = build_wave_bytes(73, 317)
    write_wave(root / "recordings" / "REC_A.wav", frames, replace=False)
    invalid = root / "positives" / "REC_A__call1.wav"
    write_wave(invalid, frames[16_000 * 2 : 32_000 * 2], replace=False)
    valid = root / "positives" / "REC_A__start-01000ms__end-02000ms__call1.wav"
    return invalid, valid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/spec-02-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=250)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 02 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="alpaca-spec02-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec02Example"
        invalid, valid = _make_repairable_collection(root)
        controller = WorkspaceController(
            temporary_root / "application-settings",
            scan_step_delay_seconds=0.35,
        )
        window = MainWindow(controller)
        window.resize(1180, 900)
        window.show()
        QTest.qWait(args.settle_ms)
        window.windowHandle().screen().grabWindow(int(window.winId()))

        window.select_page.folder_picker.setFolderPath(str(root))
        _wait_until(lambda: window.current_route == "scan")
        _wait_until(lambda: controller.scan_progress.total == 2)
        _capture(window, args.output_dir / "scanning.png", settle_ms=120)
        _wait_until(
            lambda: controller.scan_result is not None and not controller.is_scanning
        )
        _capture(window, args.output_dir / "validation-summary.png", settle_ms=args.settle_ms)
        window.collection_page.verticalScrollBar().setValue(
            window.collection_page.verticalScrollBar().maximum()
        )
        _capture(window, args.output_dir / "validation-errors.png", settle_ms=args.settle_ms)

        invalid.rename(valid)
        window.collection_page.rescan_button.click()
        _wait_until(lambda: window.current_route == "scan")
        _wait_until(
            lambda: controller.scan_result is not None
            and controller.scan_result.valid
            and not controller.is_scanning
        )
        window.collection_page.verticalScrollBar().setValue(0)
        _capture(window, args.output_dir / "collection-valid.png", settle_ms=args.settle_ms)
        window.collection_page.verticalScrollBar().setValue(
            window.collection_page.verticalScrollBar().maximum()
        )
        _capture(
            window,
            args.output_dir / "collection-valid-detail.png",
            settle_ms=args.settle_ms,
        )
        window.collection_page.verticalScrollBar().setValue(0)
        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and window.collection_page.is_compact)
        _capture(window, args.output_dir / "collection-narrow.png", settle_ms=args.settle_ms)
        _wait_until(lambda: controller._scan_thread is None)
        window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
