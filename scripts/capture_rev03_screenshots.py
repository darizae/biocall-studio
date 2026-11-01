"""Capture native REV-03 light-theme and plain-language evidence on macOS."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from alp_ui.theme import ALPACA_LIGHT
from capture_st07_screenshots import _capture, _model, _wait_until
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio.detect.application.controller import ModelIntakeState
from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.inventory import InclusionDecision
from biocall_studio.detect.domain.runs import DetectRunStatus
from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.collection_scan import scan_collection
from biocall_studio.train.application.workspace import WorkspaceController


def _wait_completed(controller) -> None:
    _wait_until(
        lambda: (
            controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.COMPLETED
        )
    )


def _capture_studio_pair(window, output: Path, settle_ms: int) -> None:
    for width, stem in ((1180, "studio-normal"), (700, "studio-compact")):
        window.resize(width, 790)
        _wait_until(lambda width=width: window.launchpad._compact == (width < 900))
        _capture(window, output / f"{stem}.png", settle_ms=settle_ms)


def _capture_train_pair(window, output: Path, settle_ms: int) -> None:
    for width, stem in ((1180, "train-normal"), (700, "train-compact")):
        window.resize(width, 790)
        _wait_until(lambda width=width: window.is_compact == (width < 900))
        window.training_page.verticalScrollBar().setValue(0)
        _capture(window, output / f"{stem}.png", settle_ms=settle_ms)


def _capture_detect_pair(page, window, output: Path, settle_ms: int) -> None:
    page._set_route("setup")
    for width, stem in (
        (1180, "detect-model-incompatible-normal"),
        (700, "detect-model-incompatible-compact"),
    ):
        window.resize(width, 790)
        _wait_until(lambda width=width: page.is_compact == (width < 900))
        page.verticalScrollBar().setValue(0)
        _capture(window, output / f"{stem}.png", settle_ms=settle_ms)


def _capture_result(
    page,
    window,
    output: Path,
    *,
    state: str,
    stem: str,
    settle_ms: int,
    normal: bool = False,
) -> None:
    page._set_route("results")
    explorer = page.result_explorer
    if normal:
        window.resize(1180, 790)
        _wait_until(lambda: not page.is_compact and explorer.current_state_key == state)
        page.verticalScrollBar().setValue(0)
        _capture(window, output / f"{stem}-normal.png", settle_ms=settle_ms)
    window.resize(700, 790)
    _wait_until(
        lambda: (
            page.is_compact
            and explorer.current_state_key == state
            and page.horizontalScrollBar().maximum() == 0
        )
    )
    page.verticalScrollBar().setValue(0)
    _capture(window, output / f"{stem}-compact.png", settle_ms=settle_ms)


def _host_appearance() -> str:
    result = subprocess.run(
        ["defaults", "read", "-g", "AppleInterfaceStyle"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "Light"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/rev-03-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)

    host_appearance = _host_appearance()
    if host_appearance != "Dark":
        raise SystemExit("REV-03 evidence requires macOS Dark appearance.")
    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("REV-03 evidence must be captured by native macOS Cocoa.")
    if app.styleHints().colorScheme() is not Qt.ColorScheme.Light:
        raise RuntimeError("BioCall Studio did not force Qt's light color scheme.")
    if app.property("alp_ui_theme") != ALPACA_LIGHT:
        raise RuntimeError("BioCall Studio did not install the approved alp-ui light theme.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} host-appearance={host_appearance} "
        f"Python={platform.python_version()} PySide6/Qt={pyside_version} "
        f"alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()} app-color-scheme=Light"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-rev03-", dir="/tmp") as temporary:
        root = Path(temporary)
        source = root / "Rainforest_2026"
        print("Preparing a genuine Train CNN Model and real WAV fixtures...", flush=True)
        model = _model(source)

        detect_inputs = root / "detect-inputs"
        detect_inputs.mkdir()
        for name in ("Stereo_8k.wav", "Unreadable_by_decoder.wav"):
            (source / "recordings" / name).rename(detect_inputs / name)
        scan = scan_collection(source)
        train_controller = WorkspaceController(root / "train-settings")
        train_controller.bind_verified_collection(source, scan.collection_id)
        coordinator = StudioCoordinator(
            train_controller,
            detect_data_dir=root / "studio-data",
        )
        coordinator.start()
        shell = coordinator.shell_window
        shell.move(60, 24)
        _capture_studio_pair(shell, args.output_dir, args.settle_ms)

        coordinator.open_workspace(WorkspaceRoute.TRAIN)
        train = coordinator.train_window
        train.move(60, 24)
        _wait_until(
            lambda: train.controller.scan_result is not None and not train.controller.is_scanning
        )
        train.open_training("dataset-st07-evidence")
        _wait_until(lambda: train.current_route == "training")
        _capture_train_pair(train, args.output_dir, args.settle_ms)

        coordinator.show_studio()
        for name in ("Stereo_8k.wav", "Unreadable_by_decoder.wav"):
            (detect_inputs / name).rename(source / "recordings" / name)
        coordinator.open_workspace(WorkspaceRoute.DETECT)
        controller = coordinator.detect_controller
        controller._worker_step_delay_seconds = 0.05
        page = shell.detect_page

        incompatible = root / "incompatible-model"
        incompatible.mkdir()
        controller.choose_model_root(str(incompatible))
        _wait_until(
            lambda: (
                controller.model_state is ModelIntakeState.INCOMPATIBLE
                and not controller.is_model_loading
            )
        )
        _capture_detect_pair(page, shell, args.output_dir, args.settle_ms)

        controller.choose_model_root(str(model.root))
        _wait_until(
            lambda: (
                controller.model_state is ModelIntakeState.COMPATIBLE
                and not controller.is_model_loading
            )
        )
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.inputs_ready)

        print("Publishing genuine partial Result...", flush=True)
        controller.start_detection(DetectionSettings(0.0, 50, 0, 8))
        _wait_completed(controller)
        partial = controller.current_result
        if partial is None or partial.failed_files != 1 or partial.candidate_count < 1:
            raise RuntimeError("Expected a populated partial Result.")
        _capture_result(
            page,
            shell,
            args.output_dir,
            state="partial",
            stem="results-partial",
            settle_ms=args.settle_ms,
            normal=True,
        )

        controller.set_inventory_decision(
            "recordings/Unreadable_by_decoder.wav",
            is_folder=False,
            decision=InclusionDecision.EXCLUDED,
        )
        controller.select_result(partial.result_id)
        _capture_result(
            page,
            shell,
            args.output_dir,
            state="stale",
            stem="results-stale",
            settle_ms=args.settle_ms,
        )

        print("Publishing genuine complete populated Result...", flush=True)
        controller.start_detection(DetectionSettings(0.0, 50, 0, 8))
        _wait_completed(controller)
        available = controller.current_result
        if available is None or available.failed_files or available.candidate_count < 1:
            raise RuntimeError("Expected a complete populated Result.")
        _capture_result(
            page,
            shell,
            args.output_dir,
            state="available",
            stem="results-available",
            settle_ms=args.settle_ms,
        )

        print("Publishing genuine complete zero-call Result...", flush=True)
        controller.start_detection(DetectionSettings(1.0, 50, 0, 8))
        _wait_completed(controller)
        empty = controller.current_result
        if empty is None or empty.failed_files or empty.candidate_count:
            raise RuntimeError("Expected a complete zero-call Result.")
        _capture_result(
            page,
            shell,
            args.output_dir,
            state="empty",
            stem="results-empty",
            settle_ms=args.settle_ms,
        )

        source.rename(root / "Rainforest_2026-offline")
        controller.refresh()
        controller.select_result(available.result_id)
        _capture_result(
            page,
            shell,
            args.output_dir,
            state="source-unavailable",
            stem="results-source-unavailable",
            settle_ms=args.settle_ms,
        )

        controller.wait_for_model(30_000)
        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
