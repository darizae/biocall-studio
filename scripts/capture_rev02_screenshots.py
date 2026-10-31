"""Capture native REV-02 guided Detect workflow evidence on macOS."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from capture_st07_screenshots import _capture, _model, _wait_until
from PySide6 import __version__ as pyside_version
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio.detect.application.controller import ModelIntakeState
from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.workspace import WorkspaceController


def _capture_route_pair(page, window, route: str, stem: str, output: Path, settle_ms: int) -> None:
    page._set_route(route)
    window.resize(1180, 790)
    _wait_until(lambda: not page.is_compact)
    QTest.qWait(settle_ms)
    page.back_button.setFocus()
    QTest.qWait(50)
    page.verticalScrollBar().setValue(0)
    _capture(window, output / f"{stem}-normal.png", settle_ms=0)

    window.resize(700, 780)
    _wait_until(lambda: page.is_compact and page.horizontalScrollBar().maximum() == 0)
    QTest.qWait(settle_ms)
    page.back_button.setFocus()
    QTest.qWait(50)
    page.verticalScrollBar().setValue(0)
    _capture(window, output / f"{stem}-compact.png", settle_ms=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/rev-02-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("REV-02 evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-rev02-", dir="/tmp") as temporary:
        root = Path(temporary)
        source = root / "Rainforest_2026"
        print("Preparing genuine Train CNN Model and real WAV fixtures...", flush=True)
        model = _model(source)
        coordinator = StudioCoordinator(
            WorkspaceController(root / "train-settings"),
            detect_data_dir=root / "studio-data",
        )
        coordinator.start()
        coordinator.open_workspace(WorkspaceRoute.DETECT)
        controller = coordinator.detect_controller
        page = coordinator.shell_window.detect_page
        window = coordinator.shell_window
        window.move(60, 24)

        controller.choose_model_root(str(model.root))
        _wait_until(
            lambda: (
                controller.model_state is ModelIntakeState.COMPATIBLE
                and not controller.is_model_loading
            )
        )
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.inputs_ready)

        _capture_route_pair(page, window, "setup", "setup", args.output_dir, args.settle_ms)
        _capture_route_pair(
            page, window, "recordings", "recordings", args.output_dir, args.settle_ms
        )
        _capture_route_pair(page, window, "run", "run-ready", args.output_dir, args.settle_ms)
        _capture_route_pair(
            page,
            window,
            "export",
            "export-no-selection",
            args.output_dir,
            args.settle_ms,
        )
        if controller.export_snapshot is not None or controller.export_receipt is not None:
            raise RuntimeError("Selection-free Export created publication state.")

        incomplete = source / ".alpaca" / "models" / "incomplete-rev02"
        incomplete.mkdir()
        controller.choose_model_root(str(incomplete))
        _wait_until(
            lambda: (
                controller.model_state is ModelIntakeState.INCOMPATIBLE
                and not controller.is_model_loading
            )
        )
        _capture_route_pair(
            page,
            window,
            "setup",
            "model-incompatible",
            args.output_dir,
            args.settle_ms,
        )

        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
