"""Capture real ST-06 Detect Run/QProcess states from native macOS windows."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import struct
import sys
import tempfile
import wave
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from biocall_studio.detect.runs import DetectRunRequest, DetectRunStatus
from biocall_studio.gui.app import create_application
from biocall_studio.gui.coordinator import StudioCoordinator
from biocall_studio.navigation import WorkspaceRoute
from biocall_studio_train.application.workspace import WorkspaceController


def _wav(path: Path, *, frames: int, rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        payload.extend(struct.pack("<h", ((frame * 97) % 20_000) - 10_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)


def _wait_until(predicate, *, timeout_ms: int = 15_000) -> None:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout_ms:
            raise TimeoutError("Timed out preparing native ST-06 evidence state.")
        QTest.qWait(25)
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


def _request(controller, token: str) -> DetectRunRequest:
    snapshot = controller.snapshot
    collection = controller.active_collection
    if snapshot is None or collection is None:
        raise RuntimeError("Native ST-06 evidence inputs are not ready.")
    return DetectRunRequest.create(
        run_id=f"drun_{token * 32}",
        request_id=f"dreq_{token * 32}",
        launch_id=f"launch_{token * 32}",
        reservation_owner_id=controller.reservation_owner_id,
        collection_id=collection.ref.collection_id,
        binding_revision=collection.ref.binding_revision,
        inventory_id=snapshot.inventory_id,
        inventory_digest=snapshot.digest,
        selected_recording_keys=snapshot.included_keys,
        model_snapshot_id="mdl_0123456789abcdef0123456789abcdef",
        model_digest="b" * 64,
        settings={"fixture_contract": "lifecycle-v1"},
        artifact_id=f"pub_{token * 32}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/st-06-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=450)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-06 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st06-", dir="/tmp") as temporary:
        root = Path(temporary)
        source = root / "Rainforest_2026"
        _wav(source / "recordings" / "Dawn_A01.wav", frames=32_000)
        _wav(source / "recordings" / "Dawn_A02.wav", frames=24_000)
        coordinator = StudioCoordinator(
            WorkspaceController(root / "train-settings"),
            detect_data_dir=root / "studio-data",
        )
        controller = coordinator.detect_controller
        controller._worker_step_delay_seconds = 0.05
        controller._cancel_grace_ms = 1_500
        controller._kill_grace_ms = 2_500
        coordinator.start()
        coordinator.open_workspace(WorkspaceRoute.DETECT)
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.snapshot is not None and not controller.is_scanning)
        page = coordinator.shell_window.detect_page
        page._set_route("run")
        window = coordinator.shell_window
        window.move(60, 24)
        window.resize(1180, 790)
        _capture(
            window,
            args.output_dir / "run-idle-normal.png",
            settle_ms=args.settle_ms,
        )

        controller.start_lifecycle_fixture(_request(controller, "1"), behavior="stubborn")
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.RUNNING
        )
        _capture(
            window,
            args.output_dir / "run-running-normal.png",
            settle_ms=250,
        )
        controller.cancel_active_run()
        if controller.current_run.status is not DetectRunStatus.CANCELLING:
            raise RuntimeError("Cancelling evidence state was not reached.")
        _capture(
            window,
            args.output_dir / "run-cancelling-normal.png",
            settle_ms=300,
        )
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.CANCELLED
        )
        window.resize(700, 780)
        _capture(
            window,
            args.output_dir / "run-cancelled-compact.png",
            settle_ms=args.settle_ms,
        )

        window.resize(1180, 790)
        controller.start_lifecycle_fixture(_request(controller, "2"), behavior="fail")
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.FAILED
        )
        _capture(
            window,
            args.output_dir / "run-failed-normal.png",
            settle_ms=args.settle_ms,
        )

        controller.start_lifecycle_fixture(_request(controller, "3"), behavior="crash")
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.INTERRUPTED
        )
        _capture(
            window,
            args.output_dir / "run-interrupted-normal.png",
            settle_ms=args.settle_ms,
        )

        controller.start_lifecycle_fixture(_request(controller, "4"), behavior="success")
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.COMPLETED
        )
        window.resize(700, 780)
        _capture(
            window,
            args.output_dir / "run-completed-compact.png",
            settle_ms=args.settle_ms,
        )
        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
