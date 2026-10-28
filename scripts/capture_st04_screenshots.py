"""Capture ST-04 recording inventory states from visible native macOS windows."""

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

from biocall_studio.detect.controller import InventoryState
from biocall_studio.gui.app import create_application
from biocall_studio.gui.coordinator import StudioCoordinator
from biocall_studio.navigation import WorkspaceRoute
from biocall_studio_train.application.workspace import WorkspaceController


def _wav(path: Path, *, frames: int, rate: int = 16_000, channels: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        for channel in range(channels):
            payload.extend(struct.pack("<h", ((frame * 97 + channel * 701) % 20_000) - 10_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)


def _wait_until(predicate, *, timeout_ms: int = 15_000) -> None:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout_ms:
            raise TimeoutError("Timed out preparing native ST-04 evidence state.")
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


def _source(root: Path, *, invalid: bool = False, scale: int = 0) -> Path:
    source = root / "Rainforest_2026"
    _wav(source / "recordings" / "Dawn_A01.wav", frames=32_000)
    _wav(
        source / "recordings" / "night" / "Dawn_A02.wav",
        frames=24_000,
        rate=48_000,
        channels=2,
    )
    _wav(source / "incoming" / "new-recorder.wav", frames=8_000)
    _wav(source / "positives" / "Dawn_A01-call.wav", frames=4_000)
    if invalid:
        (source / "recordings" / "broken.wav").write_bytes(b"RIFF\x00\x00")
    template = (source / "recordings" / "Dawn_A01.wav").read_bytes()
    for index in range(scale):
        path = source / "incoming" / f"field-{index:04d}.wav"
        path.write_bytes(template)
    return source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/st-04-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=450)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-04 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    captures = (
        ("ready", 1180, 790),
        ("ready", 700, 780),
        ("scanning", 1180, 790),
        ("cancelled", 1180, 790),
        ("invalid", 700, 780),
        ("stale", 1180, 790),
        ("missing", 700, 780),
    )
    with tempfile.TemporaryDirectory(prefix="biocall-studio-st04-", dir="/tmp") as temporary:
        base = Path(temporary)
        for index, (state, width, height) in enumerate(captures):
            root = base / f"{index:02d}-{state}"
            source = _source(
                root,
                invalid=state == "invalid",
                scale=180 if state in {"scanning", "cancelled"} else 0,
            )
            coordinator = StudioCoordinator(
                WorkspaceController(root / "train-settings"),
                detect_data_dir=root / "studio-data",
            )
            coordinator.detect_controller._scan_step_delay_seconds = (
                0.006 if state in {"scanning", "cancelled"} else 0.0
            )
            coordinator.start()
            coordinator.open_workspace(WorkspaceRoute.DETECT)
            coordinator.detect_controller.choose_source_root(str(source))
            controller = coordinator.detect_controller
            if state == "scanning":
                _wait_until(lambda: controller.is_scanning)
                QTest.qWait(180)
            elif state == "cancelled":
                _wait_until(lambda: controller.is_scanning)
                QTest.qWait(100)
                controller.cancel_scan()
                _wait_until(lambda: not controller.is_scanning)
                if controller.inventory_state is not InventoryState.CANCELLED:
                    raise RuntimeError("Cancelled evidence state was not reached.")
            else:
                _wait_until(lambda: controller.snapshot is not None and not controller.is_scanning)
                if state == "stale":
                    recording = source / "recordings" / "Dawn_A01.wav"
                    recording.write_bytes(recording.read_bytes() + b"changed")
                    controller.refresh()
                elif state == "missing":
                    moved = root / "Archive" / source.name
                    moved.parent.mkdir()
                    source.rename(moved)
                    controller.refresh()
            window = coordinator.shell_window
            window.resize(width, height)
            window.move(60, 24)
            size = "compact" if width < 760 else "normal"
            _capture(
                window,
                args.output_dir / f"recordings-{state}-{size}.png",
                settle_ms=args.settle_ms,
            )
            if controller.is_scanning:
                controller.cancel_scan()
                _wait_until(lambda: not controller.is_scanning)
            coordinator.request_application_exit()
            QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
