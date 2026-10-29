"""Capture genuine native ST-10 frozen export and completed publication evidence."""

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

from biocall_studio.detect.detection import DetectionSettings
from biocall_studio.detect.exports import ExportState
from biocall_studio.detect.runs import DetectRunStatus
from biocall_studio.gui.app import create_application
from biocall_studio.gui.coordinator import StudioCoordinator
from biocall_studio.navigation import WorkspaceRoute
from biocall_studio_train.application.workspace import WorkspaceController


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/st-10-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=500)
    args = parser.parse_args(argv)
    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("ST-10 evidence must be captured by the native macOS Cocoa platform.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"platform={QGuiApplication.platformName()}"
    )

    with tempfile.TemporaryDirectory(prefix="biocall-studio-st10-", dir="/tmp") as temporary:
        root = Path(temporary)
        source = root / "Rainforest_2026"
        destination = root / "Published-corpora"
        destination.mkdir()
        print("Preparing genuine Train CNN Model and real WAV fixtures...", flush=True)
        model = _model(source)
        source_bytes = {path: path.read_bytes() for path in source.rglob("*.wav")}
        coordinator = StudioCoordinator(
            WorkspaceController(root / "train-settings"),
            detect_data_dir=root / "studio-data",
        )
        coordinator.start()
        coordinator.open_workspace(WorkspaceRoute.DETECT)
        controller = coordinator.detect_controller
        controller.choose_model_root(str(model.root))
        _wait_until(
            lambda: controller.model_reference is not None
            and not controller.is_model_loading
        )
        controller.choose_source_root(str(source))
        _wait_until(lambda: controller.inputs_ready)
        controller.start_detection(DetectionSettings(0.0, 50, 0, 8))
        _wait_until(
            lambda: controller.current_run is not None
            and controller.current_run.status is DetectRunStatus.COMPLETED
        )
        result = controller.current_result
        if result is None or result.candidate_count < 2:
            raise RuntimeError("Expected at least two genuine candidates for export evidence.")
        selected = tuple(
            candidate.candidate_id
            for recording in result.recordings
            for candidate in recording.candidates
        )[:3]
        for candidate_id in selected:
            controller.set_candidate_selected(candidate_id, True)

        page = coordinator.shell_window.detect_page
        page._open_export()
        export_page = page.export_page
        export_page.destination_picker.setFolderPath(str(destination))
        export_page.render()
        if not export_page.start_button.isEnabled():
            raise RuntimeError("Native export action did not become available.")

        window = coordinator.shell_window
        window.move(60, 24)
        window.resize(1180, 790)
        page.verticalScrollBar().setValue(0)
        _capture(
            window,
            args.output_dir / "export-ready-normal.png",
            settle_ms=args.settle_ms,
        )

        destination_y = export_page.destination_card.mapTo(
            page.content, export_page.destination_card.rect().topLeft()
        ).y()
        page.verticalScrollBar().setValue(max(0, destination_y - 150))
        _capture(
            window,
            args.output_dir / "export-ready-actions-normal.png",
            settle_ms=args.settle_ms,
        )

        window.resize(700, 780)
        _wait_until(lambda: page.is_compact and page.horizontalScrollBar().maximum() == 0)
        destination_y = export_page.destination_card.mapTo(
            page.content, export_page.destination_card.rect().topLeft()
        ).y()
        page.verticalScrollBar().setValue(max(0, destination_y - 110))
        _capture(
            window,
            args.output_dir / "export-ready-compact.png",
            settle_ms=args.settle_ms,
        )

        window.resize(1180, 790)
        export_page.start_button.click()
        _wait_until(
            lambda: controller.export_state is ExportState.SUCCESS
            and not controller.is_export_active
        )
        receipt = controller.verify_export_receipt()
        if not export_page.show_button.isVisible():
            raise RuntimeError("Successful native export did not expose Show in folder.")
        if {path: path.read_bytes() for path in source.rglob("*.wav")} != source_bytes:
            raise RuntimeError("ST-10 export changed a source WAV.")
        show_y = export_page.show_button.mapTo(
            page.content, export_page.show_button.rect().topLeft()
        ).y()
        page.verticalScrollBar().setValue(max(0, show_y - 560))
        _capture(
            window,
            args.output_dir / "export-success-normal.png",
            settle_ms=args.settle_ms,
        )
        print(
            f"Verified ExportReceipt={receipt.receipt_digest} destination="
            f"{receipt.final_destination}",
            flush=True,
        )
        controller.wait_for_export(30_000)
        coordinator.request_application_exit()
        QTest.qWait(100)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
