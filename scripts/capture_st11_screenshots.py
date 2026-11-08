"""Capture visible native ST-11 Studio parity and shared-exit evidence on macOS."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from capture_st02_screenshots import _capture
from capture_st07_screenshots import _wait_until, _wav
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.dataset import BuildConfig
from biocall_studio.train.domain.run import RunStatus
from biocall_studio.train.persistence.collection_metadata import publish_collection_metadata


def _collection(root: Path):
    for index in range(3):
        stem = f"ST11_{index + 1:02d}"
        _wav(root / "recordings" / f"{stem}.wav", frames=32_000)
        _wav(
            root / "positives" / f"{stem}__start-00500ms__end-01000ms__call.wav",
            frames=8_000,
        )
    return publish_collection_metadata(root, scan_collection(root))


def _build_config(scan) -> BuildConfig:
    return BuildConfig(
        selected_recording_ids=tuple(record.id for record in scan.records),
        negative_mode="ratio",
        negative_ratio=1.0,
        negative_count=0,
        allocation="proportional",
        train_percent=80,
        balance_classes=True,
        seed=42,
        margin_ms=100,
    )


def _capture_window(window: QWidget, path: Path, *, settle_ms: int) -> None:
    """Capture the actual visible native window by its platform window identifier."""
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    handle = window.windowHandle()
    position = handle.position()
    image = handle.screen().grabWindow(
        0,
        position.x(),
        position.y(),
        window.width(),
        window.height(),
    )
    if image.isNull() or image.width() < 640 or image.height() < 600:
        raise RuntimeError(f"Native window capture failed or was unexpectedly small: {path}")
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
        default=Path("docs/design/evidence/st-11-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-11 evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st11-", dir="/tmp") as temporary:
        root = Path(temporary)
        collection = root / "qualification-collection"
        scan = _collection(collection)
        controller = WorkspaceController(
            root / "suite-data" / "train" / "v1",
            worker_step_delay_seconds=0.4,
            cancel_grace_ms=200,
            kill_grace_ms=800,
        )
        controller.bind_verified_collection(collection, scan.collection_id)
        coordinator = StudioCoordinator(
            controller,
            detect_data_dir=root / "suite-data",
        )
        coordinator.start()
        _wait_until(lambda: controller.scan_result is not None)
        coordinator.shell_window.show()
        coordinator.shell_window.raise_()
        coordinator.shell_window.activateWindow()
        QTest.qWait(1_000)

        for width, height, label in ((1180, 790, "normal"), (700, 780, "compact")):
            for route in (
                WorkspaceRoute.STUDIO,
                WorkspaceRoute.TRAIN,
                WorkspaceRoute.DETECT,
                WorkspaceRoute.REVIEW,
            ):
                coordinator.open_workspace(route)
                window = (
                    coordinator.train_window
                    if route is WorkspaceRoute.TRAIN
                    else coordinator.shell_window
                )
                window.show()
                window.raise_()
                window.activateWindow()
                QTest.qWait(150)
                window.resize(width, height)
                window.windowHandle().setPosition(QPoint(60, 60))
                QTest.qWait(250)
                _capture_window(
                    window,
                    args.output_dir / f"{route.value}-{label}.png",
                    settle_ms=args.settle_ms,
                )

        run_id = controller.start_dataset_build(
            _build_config(scan), dataset_id="dataset-st11-exit-evidence"
        )
        _wait_until(
            lambda: (
                controller.active_run is not None
                and controller.active_run.run_id == run_id
                and controller.active_run.status is RunStatus.RUNNING
            )
        )
        coordinator.show_studio()
        coordinator.shell_window.show()
        coordinator.shell_window.raise_()
        coordinator.shell_window.activateWindow()
        QTest.qWait(150)
        coordinator.shell_window.resize(1180, 790)
        coordinator.shell_window.move(60, 24)
        QTest.qWait(250)
        coordinator.shell_window.close()
        _wait_until(
            lambda: coordinator.exit_dialog is not None and coordinator.exit_dialog.isVisible()
        )
        _capture(
            coordinator.shell_window,
            args.output_dir / "shared-exit-confirmation.png",
            settle_ms=args.settle_ms,
        )
        dialog = coordinator.exit_dialog
        if dialog is None:
            raise RuntimeError("Shared exit confirmation disappeared before capture.")
        stop = next(button for button in dialog.buttons() if button.text() == "Stop work and Exit")
        stop.click()
        _wait_until(
            lambda: (
                controller._shutdown_finished and coordinator.detect_controller._shutdown_finished
            )
        )
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
