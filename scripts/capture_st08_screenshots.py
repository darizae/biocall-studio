"""Capture genuine native ST-08 Result history and state evidence on macOS."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from capture_st07_screenshots import _capture, _model, _wait_until
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.inventory import InclusionDecision
from biocall_studio.detect.domain.result_views import ResultSourceState
from biocall_studio.detect.domain.runs import DetectRunStatus
from biocall_studio.detect.persistence.runs import DetectRunRepository
from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.workspace import WorkspaceController


def _wait_completed(controller) -> None:
    _wait_until(
        lambda: (
            controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.COMPLETED
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/st-08-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)
    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-08 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st08-", dir="/tmp") as temporary:
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
        controller.choose_model_root(str(model.root))
        _wait_until(
            lambda: controller.model_reference is not None and not controller.is_model_loading
        )
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.inputs_ready)

        print("Publishing populated partial ST-07 Result...", flush=True)
        controller.start_detection(DetectionSettings(0.0, 50, 0, 8))
        _wait_completed(controller)
        partial = controller.current_result
        if partial is None or partial.failed_files != 1 or partial.candidate_count < 2:
            raise RuntimeError("Expected a populated partial ST-07 Result.")
        repository = DetectRunRepository(
            controller.store.application_data_root,
            controller.active_collection.ref.collection_id,
        )
        partial_path = repository.result_path(partial.result_id) / "result.json"
        immutable_result_bytes = partial_path.read_bytes()

        page = coordinator.shell_window.detect_page
        page._set_route("results")
        explorer = page.result_explorer
        candidate_recording_row = next(
            index
            for index, recording in enumerate(controller.selected_result_projection.recordings)
            if recording.candidates
        )
        explorer.recording_table.setCurrentIndex(
            explorer.recording_model.index(candidate_recording_row, 0)
        )
        explorer.candidate_table.setCurrentIndex(explorer.candidate_model.index(0, 0))
        explorer.candidate_table.setFocus()
        QTest.keyClick(explorer.candidate_table, Qt.Key.Key_Space)
        if not controller.result_selection.candidate_ids:
            raise RuntimeError("Native Result selection was not persisted.")
        if partial_path.read_bytes() != immutable_result_bytes:
            raise RuntimeError("Changing Result selection mutated the ST-07 artifact.")

        window = coordinator.shell_window
        window.move(60, 24)
        window.resize(1180, 790)
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "results-history-partial-normal.png",
            settle_ms=args.settle_ms,
        )
        table_y = explorer.recording_card.mapTo(
            page.content, explorer.recording_card.rect().topLeft()
        ).y()
        page.verticalScrollBar().setValue(max(0, table_y - 170))
        _capture(
            window,
            args.output_dir / "results-candidates-selected-normal.png",
            settle_ms=args.settle_ms,
        )

        window.resize(700, 780)
        _wait_until(lambda: page.is_compact and page.horizontalScrollBar().maximum() == 0)
        QTest.qWait(250)
        candidate_y = explorer.candidate_card.mapTo(
            page.content, explorer.candidate_card.rect().topLeft()
        ).y()
        page.verticalScrollBar().setValue(max(0, candidate_y - 80))
        QTest.qWait(100)
        page.verticalScrollBar().setValue(max(0, candidate_y - 80))
        _capture(
            window,
            args.output_dir / "results-candidates-selected-compact.png",
            settle_ms=args.settle_ms,
        )

        controller.set_inventory_decision(
            "recordings/Unreadable_by_decoder.wav",
            is_folder=False,
            decision=InclusionDecision.EXCLUDED,
        )
        controller.select_result(partial.result_id)
        if controller.selected_result_projection.source_state is not ResultSourceState.STALE:
            raise RuntimeError("Prior Result did not become visibly stale after inventory change.")
        window.resize(1180, 790)
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "results-stale-normal.png",
            settle_ms=args.settle_ms,
        )

        print("Publishing genuine zero-candidate complete ST-07 Result...", flush=True)
        controller.start_detection(DetectionSettings(1.0, 50, 0, 8))
        _wait_completed(controller)
        empty = controller.current_result
        if empty is None or empty.failed_files or empty.candidate_count:
            raise RuntimeError("Expected a complete zero-candidate ST-07 Result.")
        empty_path = repository.result_path(empty.result_id) / "result.json"
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "results-empty-normal.png",
            settle_ms=args.settle_ms,
        )

        missing = root / "Rainforest_2026-offline"
        source.rename(missing)
        controller.refresh()
        controller.select_result(partial.result_id)
        page._set_route("results")
        window.resize(700, 780)
        _wait_until(
            lambda: (
                page.is_compact
                and explorer.current_state_key == "source-unavailable"
                and page.horizontalScrollBar().maximum() == 0
            )
        )
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "results-source-unavailable-compact.png",
            settle_ms=args.settle_ms,
        )

        empty_path.write_bytes(b"{corrupt")
        controller.refresh()
        controller.select_result(empty.result_id)
        page._set_route("results")
        window.resize(1180, 790)
        _wait_until(lambda: explorer.current_state_key == "result-error")
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "results-corrupt-normal.png",
            settle_ms=args.settle_ms,
        )
        if partial_path.read_bytes() != immutable_result_bytes:
            raise RuntimeError("ST-08 changed the selected immutable Result.")
        controller.wait_for_model(30_000)
        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
