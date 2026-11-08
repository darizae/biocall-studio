"""Capture visible native release screenshots from the verified real-hum example pack."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.detect.application.navigation import DetectRoute
from biocall_studio.review.application.controller import (
    ReviewSessionController,
    default_spectrogram_snapshot,
)
from biocall_studio.review.domain.sessions import ReviewLabel, ReviewSessionState
from biocall_studio.review.domain.spectrograms import SpectrogramImageTier
from biocall_studio.studio.application.app import create_application
from biocall_studio.studio.application.coordinator import StudioCoordinator
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.train.application.workspace import WorkspaceController
from biocall_studio.train.persistence.collection_metadata import load_collection_metadata

DEFAULT_EXAMPLE_ROOT = Path("work/manual-review-real-hums")
DEFAULT_COLLECTION = Path("work/release-evidence/Verified Alpaca Hums")
DEFAULT_SUITE_ROOT = Path("work/release-evidence/app-data")
DEFAULT_OUTPUT = Path("docs/design/evidence/release-real-data")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _now(offset_seconds: int = 0) -> str:
    value = datetime.now(UTC) + timedelta(seconds=offset_seconds)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _wait_until(predicate, *, timeout_ms: int = 30_000, interval_ms: int = 25) -> None:
    deadline = timeout_ms
    while deadline > 0:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(interval_ms)
        deadline -= interval_ms
    raise TimeoutError("Native release screenshot state did not become ready in time.")


def _button(widget: QWidget, text: str) -> QPushButton:
    return next(button for button in widget.findChildren(QPushButton) if button.text() == text)


def _set_viewport(window: QWidget, width: int = 1280, height: int = 807) -> None:
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for native release capture.")
    available = screen.availableGeometry()
    if width > available.width() or height > available.height():
        raise RuntimeError("The requested release viewport does not fit the active display.")
    window.resize(width, height)
    window.move(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWait(500)


def _capture(
    window: QWidget,
    output: Path,
    name: str,
    captures: list[dict[str, object]],
) -> None:
    window.raise_()
    window.activateWindow()
    QApplication.processEvents()
    QTest.qWait(450)
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for native release capture.")
    origin = window.mapToGlobal(QPoint(0, 0))
    pixmap = screen.grabWindow(
        0,
        origin.x(),
        origin.y(),
        window.width(),
        window.height(),
    )
    if pixmap.isNull():
        raise RuntimeError(f"Visible Cocoa capture returned an empty image for {name}.")
    target = output / name
    if not pixmap.save(str(target), "PNG"):
        raise RuntimeError(f"Could not save {target}.")
    captures.append(
        {
            "file": name,
            "logical_viewport": [window.width(), window.height()],
            "png_pixels": [pixmap.width(), pixmap.height()],
            "device_pixel_ratio": pixmap.devicePixelRatio(),
        }
    )
    print(f"Captured {name}: {pixmap.width()}x{pixmap.height()}")


def _safe_reset_suite(root: Path) -> None:
    resolved = root.resolve(strict=False)
    allowed = Path("work/release-evidence").resolve(strict=False)
    if not resolved.is_relative_to(allowed) or resolved == allowed:
        raise ValueError("Release suite reset is restricted to a named folder under work/.")
    if resolved.exists():
        shutil.rmtree(resolved)


def _prepare_suite(example_root: Path, suite_root: Path) -> None:
    _safe_reset_suite(suite_root)
    detect_source = example_root / "app-data" / "detect"
    shutil.copytree(detect_source, suite_root / "detect")


def _prepare_review_session(example_root: Path) -> str:
    suite_root = example_root / "app-data"
    review_root = suite_root / "review" / "v1"
    provenance = json.loads((example_root / "REAL_HUM_PROVENANCE.json").read_text(encoding="utf-8"))
    if any(row["human_binary_target"] != "positive" for row in provenance["rows"]):
        raise RuntimeError("The release Review cohort contains an unexpected human label.")
    detect = DetectWorkspaceController(suite_root)
    controller = ReviewSessionController(suite_root, review_data_root=review_root)
    try:
        controller.ensure_default_preset(default_spectrogram_snapshot(), saved_at=_now())
        result = next(
            item.result
            for item in detect.result_history
            if item.available and item.result is not None
        )
        inspection = controller.intake.intake(result.collection_id, result.result_id)
        if inspection.manifest is None:
            raise RuntimeError("The real-hum Detect Result could not be opened by Review.")

        sessions = controller.list_sessions()
        open_session = next(
            (item for item in sessions if item.state is ReviewSessionState.OPEN), None
        )
        if open_session is not None:
            session = controller.recover_open_session(recovered_at=_now()) or open_session
        else:
            resumable = next(
                (item for item in sessions if item.state is ReviewSessionState.CLOSED), None
            )
            if resumable is not None:
                session, _availability = controller.resume_session(
                    resumable.session_id,
                    expected_revision=resumable.revision,
                    resumed_at=_now(),
                )
            else:
                session = controller.start_session(
                    result.collection_id,
                    result.result_id,
                    name="Alpaca hum verification",
                    settings=controller.list_presets()[0],
                    created_at=_now(),
                )

        if session.name != "Alpaca hum verification":
            session = controller.rename_session(
                session.session_id,
                "Alpaca hum verification",
                expected_revision=session.revision,
                renamed_at=_now(),
            )
        rows = controller.store.candidate_page(
            session.session_id,
            offset=0,
            limit=64,
            sort_name="source_time",
        )
        for index, row in enumerate(rows):
            label = ReviewLabel.CALL if index < 18 else ReviewLabel.UNREVIEWED
            if row.label is label:
                continue
            session = controller.set_label(
                session.session_id,
                row.candidate_id,
                label,
                expected_revision=session.revision,
                modified_at=_now(index + 1),
            ).session
        return session.session_id
    finally:
        controller.shutdown()
        detect.shutdown()


def _accept_existing_review_data() -> None:
    dialog = next(
        (
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMessageBox) and widget.isVisible()
        ),
        None,
    )
    if dialog is None:
        raise RuntimeError("The existing Review data confirmation did not open.")
    _button(dialog, "Use this data").click()


def _git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-root", type=Path, default=DEFAULT_EXAMPLE_ROOT)
    parser.add_argument("--train-collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--suite-root", type=Path, default=DEFAULT_SUITE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--warm-review-cache-only", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    example_root = args.example_root.resolve(strict=True)
    collection = args.train_collection.resolve(strict=True)
    suite_root = args.suite_root.resolve(strict=False)
    output = args.output_dir.resolve(strict=False)
    if output.exists() and any(output.iterdir()) and not args.replace:
        parser.error(f"{output} already contains evidence; pass --replace deliberately")
    output.mkdir(parents=True, exist_ok=True)
    if args.replace:
        for path in (*output.glob("*.png"), output / "capture-metadata.json"):
            if path.exists() and path.is_file() and not path.is_symlink():
                path.unlink()

    session_id = _prepare_review_session(example_root)
    _prepare_suite(example_root, suite_root)
    metadata = load_collection_metadata(collection)

    app = create_application([])
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        raise SystemExit("Release screenshots must be captured by visible native macOS Cocoa.")
    train = WorkspaceController(suite_root / "train" / "v1")
    train.bind_verified_collection(collection, metadata.collection_id)
    coordinator = StudioCoordinator(train, detect_data_dir=suite_root)
    captures: list[dict[str, object]] = []
    coordinator.start()

    try:
        if args.warm_review_cache_only:
            _set_viewport(coordinator.shell_window)
            coordinator.open_workspace(WorkspaceRoute.REVIEW)
            coordinator.review_page.show_data_settings()
            QTimer.singleShot(250, _accept_existing_review_data)
            target_review_root = example_root / "app-data" / "review" / "v1"
            coordinator.review_page.data_settings_page.folder_picker.setFolderPath(
                str(target_review_root)
            )
            _wait_until(
                lambda: coordinator.review_controller.store.root == target_review_root,
                timeout_ms=30_000,
            )
            review_page = coordinator.review_page
            review_page.open_session(session_id)
            review_page.show_spectrograms()
            _wait_until(
                lambda: (
                    review_page._generation_prepare_thread is None
                    and review_page.cache_page.generate_button.isEnabled()
                ),
                timeout_ms=45_000,
            )
            _button(review_page.cache_page, "Generate all").click()
            try:
                _wait_until(
                    lambda: (
                        review_page._generation_batch_id is None
                        and review_page._generation_prepare_thread is None
                        and review_page.cache_page.progress_label.text()
                        == "Retained 64 of 64 thumbnails."
                    ),
                    timeout_ms=100_000,
                )
            except TimeoutError:
                valid = sum(
                    1
                    for key in review_page.cache.valid_content_keys()
                    if (entry := review_page.cache.lookup(key)) is not None
                    and entry.tier is SpectrogramImageTier.THUMBNAIL
                )
                print(f"Cache warming paused at {valid} of 64 valid thumbnails.")
                return 0
            print("Cache warming completed with 64 of 64 valid thumbnails.")
            return 0

        _set_viewport(coordinator.shell_window)
        coordinator.open_workspace(WorkspaceRoute.STUDIO)
        _capture(coordinator.shell_window, output, "00-studio.png", captures)

        _wait_until(lambda: train.scan_result is not None and not train.is_scanning)
        if train.scan_result is None or not train.scan_result.valid:
            raise RuntimeError("The real-hum Train Collection did not reopen as valid.")
        coordinator.open_workspace(WorkspaceRoute.TRAIN)
        _set_viewport(coordinator.train_window)
        coordinator.train_window.collection_page.set_result(train.scan_result)
        coordinator.train_window.navigate("collection")
        _capture(coordinator.train_window, output, "01-train-collection.png", captures)
        coordinator.train_window.open_builder()
        _capture(coordinator.train_window, output, "02-train-dataset-builder.png", captures)

        coordinator.open_workspace(WorkspaceRoute.DETECT)
        _set_viewport(coordinator.shell_window)
        detect_page = coordinator.shell_window.detect_page
        detect_page._set_route(DetectRoute.RUNS)
        _capture(coordinator.shell_window, output, "03-detect-runs.png", captures)
        run = next(
            item for item in coordinator.detect_controller.runs if item.artifact_id is not None
        )
        detect_page._open_run(run.run_id)
        _capture(coordinator.shell_window, output, "04-detect-run.png", captures)
        detect_page._open_selected_run_result()
        _capture(coordinator.shell_window, output, "05-detect-results.png", captures)

        coordinator.open_workspace(WorkspaceRoute.REVIEW)
        coordinator.review_page.show_data_settings()
        QTimer.singleShot(250, _accept_existing_review_data)
        target_review_root = example_root / "app-data" / "review" / "v1"
        coordinator.review_page.data_settings_page.folder_picker.setFolderPath(
            str(target_review_root)
        )
        _wait_until(
            lambda: coordinator.review_controller.store.root == target_review_root,
            timeout_ms=30_000,
        )
        review_page = coordinator.review_page
        _capture(coordinator.shell_window, output, "06-review-data-folder.png", captures)

        review_page.show_sessions(select_session_id=session_id)
        _capture(coordinator.shell_window, output, "07-review-sessions.png", captures)
        review_page.open_session(session_id)
        _button(review_page.session_page, "Gallery").click()
        _wait_until(
            lambda: review_page.gallery_model.cached_thumbnail_count >= 8,
            timeout_ms=45_000,
        )
        _capture(coordinator.shell_window, output, "08-review-gallery.png", captures)

        if review_page.current_state is None:
            raise RuntimeError("The real-hum Review session did not open.")
        detail_row = review_page.current_state.page(12, 1)[0]
        review_page._open_candidate(detail_row.candidate_id)
        _wait_until(
            lambda: review_page.session_page.spectrogram.metadata is not None,
            timeout_ms=45_000,
        )
        _capture(coordinator.shell_window, output, "09-review-one-by-one.png", captures)

        review_page.show_spectrograms()
        _wait_until(
            lambda: (
                review_page.calibration_store.calibration(SpectrogramImageTier.THUMBNAIL)
                is not None
            ),
            timeout_ms=45_000,
        )
        _wait_until(
            lambda: (
                review_page._generation_prepare_thread is None
                and review_page.cache_page.generate_button.isEnabled()
            ),
            timeout_ms=45_000,
        )
        _button(review_page.cache_page, "Generate all").click()
        _wait_until(
            lambda: (
                review_page._generation_batch_id is None
                and review_page._generation_prepare_thread is None
                and review_page.cache_page.availability_label.text()
                == "64 of 64 spectrograms available"
                and review_page.cache_page.progress_label.text() == "Retained 64 of 64 thumbnails."
            ),
            timeout_ms=100_000,
        )
        _capture(coordinator.shell_window, output, "10-review-spectrograms.png", captures)

        screen = coordinator.shell_window.screen() or QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("No screen was available for release metadata.")
        release_session = coordinator.review_controller.store.get_session(session_id)
        diff = subprocess.check_output(["git", "diff", "--binary"])
        evidence = {
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "capture_mode": "visible Cocoa QScreen capture of live PySide6 windows",
            "application": {
                "branch": _git_value("branch", "--show-current"),
                "head": _git_value("rev-parse", "HEAD"),
                "working_tree_diff_sha256": hashlib.sha256(diff).hexdigest(),
            },
            "platform": {
                "os": platform.platform(),
                "qt_version": qVersion(),
                "qt_platform": app.platformName(),
                "alp_ui_version": importlib.metadata.version("alp-ui"),
                "screen": screen.name(),
                "screen_device_pixel_ratio": screen.devicePixelRatio(),
            },
            "real_example": {
                "name": "Verified real alpaca hums",
                "source_wav": str(
                    example_root / "source" / "recordings" / "verified-real-hums.wav"
                ),
                "source_wav_sha256": _sha256(
                    example_root / "source" / "recordings" / "verified-real-hums.wav"
                ),
                "provenance_sha256": _sha256(example_root / "REAL_HUM_PROVENANCE.json"),
                "review_candidates": 64,
                "review_call_labels": release_session.call_count,
                "review_not_call_labels": release_session.not_call_count,
                "review_unreviewed": release_session.unreviewed_count,
                "train_recordings": metadata.recording_count,
                "train_positive_examples": metadata.positive_count,
                "review_session_id": session_id,
            },
            "captures": captures,
        }
        (output / "capture-metadata.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if len(captures) != 11:
            raise RuntimeError(f"Expected 11 release screenshots, captured {len(captures)}.")
    finally:
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMessageBox):
                widget.close()
        coordinator.review_page.shutdown()
        coordinator.review_controller.shutdown()
        coordinator.detect_controller.shutdown()
        train.shutdown()
        coordinator.train_window.hide()
        coordinator.shell_window.allow_application_close()
        coordinator.shell_window.close()
        QApplication.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
