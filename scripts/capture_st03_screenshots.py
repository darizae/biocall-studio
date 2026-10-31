"""Capture ST-03 Detect Collection states from visible native macOS Cocoa windows."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.workspace import WorkspaceController


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
        default=Path("docs/design/evidence/st-03-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-03 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st03-", dir="/tmp") as temporary:
        base = Path(temporary)
        for width, height, size in ((1180, 790, "normal"), (700, 780, "compact")):
            for state in ("empty", "available", "missing", "relink"):
                root = base / f"{size}-{state}"
                source = root / "Rainforest_2026"
                source.mkdir(parents=True)
                coordinator = StudioCoordinator(
                    WorkspaceController(root / "train-settings"),
                    detect_data_dir=root / "studio-data",
                )
                coordinator.start()
                coordinator.open_workspace(WorkspaceRoute.DETECT)
                if state != "empty":
                    coordinator.detect_controller.choose_source_root(str(source))
                if state in {"missing", "relink"}:
                    moved = root / "Archive" / source.name
                    moved.parent.mkdir()
                    source.rename(moved)
                    coordinator.detect_controller.refresh()
                    if state == "relink":
                        coordinator.detect_controller.choose_source_root(str(moved))
                window = coordinator.shell_window
                window.resize(width, height)
                window.move(60, 24)
                _capture(
                    window,
                    args.output_dir / f"detect-{state}-{size}.png",
                    settle_ms=args.settle_ms,
                )
                coordinator.request_application_exit()
                QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
