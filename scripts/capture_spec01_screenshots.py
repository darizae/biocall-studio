"""Capture the required Spec 01 views from a visible native macOS window."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio_train.application.workspace import WorkspaceController
from biocall_studio_train.gui.app import create_application
from biocall_studio_train.gui.window import MainWindow


def _capture(window: MainWindow, path: Path, *, settle_ms: int) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    screen = window.windowHandle().screen()
    image = screen.grabWindow(int(window.winId()))
    if image.isNull() or image.width() < 640 or image.height() < 600:
        raise RuntimeError(f"Native capture failed or was unexpectedly small: {path}")
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save native screenshot: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/spec-01-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=300)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 01 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="biocall-studio-train-spec01-settings-") as settings:
        window = MainWindow(WorkspaceController(Path(settings)))
        window.resize(1180, 790)
        window.show()
        QTest.qWait(args.settle_ms)
        # The first macOS window-server grab can reflect pre-layout backing-store geometry.
        window.windowHandle().screen().grabWindow(int(window.winId()))
        for route, filename in (
            ("select", "select.png"),
            ("wiki", "wiki.png"),
            ("settings", "settings.png"),
            ("collections", "empty-collections.png"),
            ("datasets", "empty-datasets.png"),
            ("models", "empty-models.png"),
            ("runs", "empty-runs.png"),
        ):
            window.navigate(route)
            _capture(window, args.output_dir / filename, settle_ms=args.settle_ms)
        window.resize(700, 780)
        window.navigate("select")
        _capture(window, args.output_dir / "select-narrow.png", settle_ms=args.settle_ms)
        window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
