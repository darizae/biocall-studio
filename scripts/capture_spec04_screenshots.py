"""Capture Spec 04 Run lifecycle views from native macOS Cocoa."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from generate_example_collection import EXAMPLES, RATE, build_wave_bytes, write_wave
from PySide6.QtCore import QElapsedTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from biocall_studio.studio.application.app import create_application
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.domain.run import RunStatus
from biocall_studio.train.gui.window import MainWindow
from biocall_studio.train.workflows.dataset_build import build_dataset


def _wait_until(predicate, *, timeout_ms: int = 20_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native Run state.")
        QTest.qWait(20)


def _capture(window: MainWindow, path: Path, *, settle_ms: int) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(settle_ms)
    print(
        f"Capturing {path.name}: size={window.width()}x{window.height()} "
        f"position={window.x()},{window.y()}"
    )
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


def _make_collection(root: Path) -> None:
    for source, start_ms, end_ms, label, period_a, period_b in EXAMPLES:
        frames = build_wave_bytes(period_a, period_b)
        write_wave(root / "recordings" / f"{source}.wav", frames, replace=False)
        start = start_ms * RATE // 1_000 * 2
        end = end_ms * RATE // 1_000 * 2
        write_wave(
            root
            / "positives"
            / f"{source}__start-{start_ms:05d}ms__end-{end_ms:05d}ms__{label}.wav",
            frames[start:end],
            replace=False,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/evidence/spec-04-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=800)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 04 evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="biocall-studio-spec04-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec04Example"
        _make_collection(root)
        controller = WorkspaceController(
            temporary_root / "application-settings",
            worker_step_delay_seconds=0.35,
            cancel_grace_ms=2_000,
            kill_grace_ms=3_000,
        )
        window = MainWindow(controller)
        window.resize(1280, 900)
        window.move(60, 24)
        window.show()
        QTest.qWait(args.settle_ms)
        window.windowHandle().screen().grabWindow(int(window.winId()))
        QTest.qWait(args.settle_ms)
        window.select_page.folder_picker.setFolderPath(str(root))
        _wait_until(lambda: controller.scan_result is not None and not controller.is_scanning)
        window.open_builder()
        builder = window.builder_page
        _wait_until(lambda: builder.build_button.isEnabled())
        config = builder.config()

        controller.start_dataset_build(config, dataset_id="dataset-cancelled-evidence")
        _wait_until(
            lambda: (
                controller.active_run is not None
                and controller.active_run.status is RunStatus.RUNNING
                and controller.active_run.progress >= 2
            )
        )
        _capture(window, args.output_dir / "run-active.png", settle_ms=300)
        controller.cancel_active_run()
        _wait_until(
            lambda: (
                controller.active_run is not None
                and controller.active_run.status is RunStatus.CANCELLING
            )
        )
        _capture(window, args.output_dir / "run-cancelling.png", settle_ms=50)
        _wait_until(lambda: controller.active_run is None)

        scan = controller.scan_result
        if scan is None:
            raise RuntimeError("Collection Scan was not available for failure evidence.")
        build_dataset(root, scan, config, dataset_id="dataset-collision-evidence")
        controller.start_dataset_build(config, dataset_id="dataset-collision-evidence")
        _wait_until(lambda: controller.active_run is None)
        if window.run_detail_page.run is None or (
            window.run_detail_page.run.status is not RunStatus.FAILED
        ):
            raise RuntimeError("Collision did not produce the expected failed Run view.")
        _capture(window, args.output_dir / "run-failed.png", settle_ms=args.settle_ms)

        controller.start_dataset_build(config, dataset_id="dataset-completed-evidence")
        _wait_until(lambda: controller.active_run is None)
        if window.run_detail_page.run is None or (
            window.run_detail_page.run.status is not RunStatus.COMPLETED
        ):
            raise RuntimeError("Dataset Build did not produce the completed Run view.")
        _capture(window, args.output_dir / "run-completed.png", settle_ms=args.settle_ms)

        window.navigate("runs")
        _capture(window, args.output_dir / "runs-history.png", settle_ms=args.settle_ms)

        completed = next(run for run in controller.runs if run.status is RunStatus.COMPLETED)
        window.open_run(completed.run_id)
        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and window.run_detail_page.is_compact)
        window.nav_scroll.horizontalScrollBar().setValue(
            window.nav_scroll.horizontalScrollBar().maximum()
        )
        _capture(window, args.output_dir / "run-narrow.png", settle_ms=args.settle_ms)
        if controller.active_run is not None or controller._run_process is not None:
            raise RuntimeError("Evidence capture left a Worker active.")
        window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
