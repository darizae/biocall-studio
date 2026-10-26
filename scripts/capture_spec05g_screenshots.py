"""Capture Spec 05g safe-exit and keep-awake additions from native macOS Cocoa."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
import tempfile
from pathlib import Path

from generate_example_collection import EXAMPLES, RATE, build_wave_bytes, write_wave
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QElapsedTimer, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from alpaca_desktop.application.collection_scan import scan_collection
from alpaca_desktop.application.power import PowerInhibitionUnavailable
from alpaca_desktop.application.workspace import WorkspaceController
from alpaca_desktop.domain.dataset import BuildConfig
from alpaca_desktop.gui.app import create_application
from alpaca_desktop.gui.window import MainWindow
from alpaca_desktop.persistence.collection_metadata import publish_collection_metadata
from alpaca_desktop.workflows.dataset_build import build_dataset


class UnavailablePowerAdapter:
    def acquire(self) -> None:
        raise PowerInhibitionUnavailable(
            "Automatic idle-sleep prevention is unavailable on this system."
        )

    def release(self) -> None:
        return


def _wait_until(predicate, *, timeout_ms: int = 60_000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timer.elapsed() > timeout_ms:
            raise TimeoutError("Timed out waiting for native Spec 05g evidence state.")
        QTest.qWait(20)


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
    if image.isNull() or image.width() < 540 or image.height() < 300:
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
        default=Path("docs/design/evidence/spec-05g-native"),
    )
    parser.add_argument("--settle-ms", type=int, default=700)
    args = parser.parse_args(argv)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Spec 05g evidence must be captured by native macOS Cocoa.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"macOS={platform.mac_ver()[0]} Python={platform.python_version()} "
        f"PySide6/Qt={pyside_version} alp-ui={importlib.metadata.version('alp-ui')} "
        f"appearance={app.styleHints().colorScheme().name}"
    )

    with tempfile.TemporaryDirectory(prefix="alpaca-spec05g-", dir="/tmp") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "Spec05gExample"
        _make_collection(root)
        scan = publish_collection_metadata(root, scan_collection(root))
        config = BuildConfig(
            selected_recording_ids=tuple(record.id for record in scan.records),
            negative_mode="ratio",
            negative_ratio=1.0,
            negative_count=0,
            allocation="proportional",
            train_percent=80,
            balance_classes=True,
            seed=42,
            margin_ms=250,
        )
        dataset = build_dataset(
            root,
            scan,
            config,
            dataset_id="dataset-long-running-evidence",
        )
        controller = WorkspaceController(
            temporary_root / "application-settings",
            worker_step_delay_seconds=0.8,
        )
        controller.bind_verified_collection(root, scan.collection_id)
        window = MainWindow(controller)
        window.resize(1280, 807)
        window.move(60, 24)
        window.show()
        _wait_until(lambda: controller.scan_result is not None and not controller.is_scanning)

        window.navigate("settings")
        window.settings_page.ensureWidgetVisible(window.settings_page.power_card, 20, 180)
        _capture(window, args.output_dir / "settings-power-off.png", settle_ms=args.settle_ms)
        window.settings_page.keep_awake_toggle.click()
        if not controller.keep_awake_active:
            raise RuntimeError(controller.keep_awake_error or "macOS keep-awake did not activate")
        _capture(window, args.output_dir / "settings-power-on.png", settle_ms=args.settle_ms)

        window.open_training(dataset.dataset_id)
        window.training_page.ensureWidgetVisible(window.training_page.start_card, 20, 160)
        _capture(window, args.output_dir / "train-power-on.png", settle_ms=args.settle_ms)

        window.resize(700, 780)
        _wait_until(lambda: window.is_compact and window.training_page._compact)
        window.training_page.ensureWidgetVisible(window.training_page.start_card, 20, 140)
        _wait_until(lambda: window.training_page.verticalScrollBar().maximum() > 0)
        QTest.qWait(200)
        window.training_page.verticalScrollBar().setValue(
            window.training_page.verticalScrollBar().maximum()
        )
        _capture(window, args.output_dir / "train-power-narrow.png", settle_ms=args.settle_ms)

        window.resize(1280, 807)
        window.navigate("wiki")
        window.wiki_page.ensureWidgetVisible(window.wiki_page.keep_awake_card, 20, 140)
        _capture(window, args.output_dir / "wiki-keep-awake.png", settle_ms=args.settle_ms)

        run_id = controller.start_dataset_build(
            config,
            dataset_id="dataset-safe-exit-evidence",
        )
        _wait_until(
            lambda: (
                controller.active_run is not None
                and controller.active_run.run_id == run_id
                and controller.active_run.status.value == "running"
            )
        )
        window.open_run(run_id)
        _capture(
            window,
            args.output_dir / "active-run-light-theme.png",
            settle_ms=args.settle_ms,
        )
        window.close()
        _wait_until(lambda: window.close_dialog is not None and window.close_dialog.isVisible())
        _capture(
            window,
            args.output_dir / "active-run-exit-confirmation.png",
            settle_ms=args.settle_ms,
        )
        window.close_dialog.defaultButton().click()
        controller.cancel_active_run()
        _wait_until(lambda: controller.active_run is None)

        window.resize(700, 780)
        window.navigate("settings")
        _wait_until(lambda: window.settings_page.is_compact)
        window.settings_page.ensureWidgetVisible(window.settings_page.power_card, 20, 140)
        power_y = window.settings_page.power_card.mapTo(
            window.settings_page.widget(), QPoint(0, 0)
        ).y()
        window.settings_page.verticalScrollBar().setValue(max(0, power_y - 100))
        _capture(
            window,
            args.output_dir / "settings-power-narrow.png",
            settle_ms=args.settle_ms,
        )
        controller.set_keep_awake(False)
        window.close()

        unavailable_controller = WorkspaceController(
            temporary_root / "unavailable-settings",
            power_adapter=UnavailablePowerAdapter(),
        )
        unavailable_window = MainWindow(unavailable_controller)
        unavailable_window.resize(1280, 807)
        unavailable_window.move(60, 24)
        unavailable_window.show()
        unavailable_window.navigate("settings")
        unavailable_window.settings_page.keep_awake_toggle.click()
        unavailable_window.settings_page.ensureWidgetVisible(
            unavailable_window.settings_page.power_card,
            20,
            180,
        )
        unavailable_power_y = unavailable_window.settings_page.power_card.mapTo(
            unavailable_window.settings_page.widget(), QPoint(0, 0)
        ).y()
        unavailable_window.settings_page.verticalScrollBar().setValue(
            max(0, unavailable_power_y - 80)
        )
        _capture(
            unavailable_window,
            args.output_dir / "settings-power-unavailable.png",
            settle_ms=args.settle_ms,
        )
        unavailable_window.close()

    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
