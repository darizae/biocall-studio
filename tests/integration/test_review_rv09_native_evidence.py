"""Visible Cocoa capture for the RV-09 owner-review evidence set."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import struct
import wave
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QTimer, qVersion
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from biocall_studio.detect.application.controller import DetectWorkspaceController
from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.domain.intake import (
    REVIEW_INTAKE_SCHEMA_VERSION,
    EligibleCandidate,
    ReviewIntakeManifest,
    ReviewIntakeProjection,
    ReviewRecording,
    ReviewResultKind,
    projection_digest,
)
from biocall_studio.review.domain.sessions import (
    DEFAULT_PRESET_ID,
    ReviewLabel,
    ReviewSessionSource,
    SpectrogramSettingsSnapshot,
)
from biocall_studio.review.domain.spectrograms import SpectrogramImageTier
from biocall_studio.review.gui.workspace import ReviewResultChoice, ReviewWorkspacePage
from biocall_studio.studio.application.app import create_application as create_studio_application
from biocall_studio.studio.application.navigation import WorkspaceRoute
from biocall_studio.studio.gui.shell import StudioWindow

pytestmark = [pytest.mark.integration, pytest.mark.qt, pytest.mark.native_cocoa]


def _write_wav(path: Path, *, seconds: int = 10, sample_rate: int = 8_000) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(seconds * sample_rate):
        carrier = 8_500 * math.sin(2 * math.pi * 740 * index / sample_rate)
        harmonic = 2_200 * math.sin(2 * math.pi * 1_480 * index / sample_rate)
        envelope = 0.45 + 0.55 * math.sin(2 * math.pi * 2.2 * index / sample_rate) ** 2
        frames.extend(struct.pack("<h", int((carrier + harmonic) * envelope)))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(frames)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _projection(*, source_sha256: str, recording_name: str) -> ReviewIntakeProjection:
    candidates = []
    for index in range(12):
        start_frame = 8_000 + index * 5_500
        end_frame = start_frame + 2_400
        candidates.append(
            EligibleCandidate(
                ordinal=index,
                recording_ordinal=0,
                candidate_id=f"cand_{index:032x}",
                recording_ref="rec_" + "1" * 32,
                recording_key=f"recordings/{recording_name}",
                source_sha256=source_sha256,
                sample_rate_hz=8_000,
                frame_count=80_000,
                channels=1,
                start_frame=start_frame,
                end_frame=end_frame,
                start_time_ns=(start_frame * 1_000_000_000 + 4_000) // 8_000,
                end_time_ns=(end_frame * 1_000_000_000 + 4_000) // 8_000,
                cnn_target_score=0.93 - index * 0.035,
                rf_target_score=None,
                contributing_windows=1 + index % 3,
            )
        )
    recording = ReviewRecording(
        ordinal=0,
        recording_ref="rec_" + "1" * 32,
        recording_key=f"recordings/{recording_name}",
        source_sha256=source_sha256,
        sample_rate_hz=8_000,
        frame_count=80_000,
        channels=1,
        failed=False,
        error_code="",
        eligible_candidate_count=len(candidates),
    )
    manifest = ReviewIntakeManifest(
        schema_version=REVIEW_INTAKE_SCHEMA_VERSION,
        projection_digest="0" * 64,
        result_kind=ReviewResultKind.CNN,
        collection_id="det_" + "3" * 32,
        result_id="pub_" + "4" * 32,
        result_digest="5" * 64,
        publication_digest="6" * 64,
        parent_result_id=None,
        parent_result_digest=None,
        binding_revision=1,
        inventory_id="inv_" + "7" * 32,
        inventory_digest="8" * 64,
        source_time_semantics=(
            "zero_based_half_open_source_frames_with_integer_nanosecond_projection"
        ),
        recording_count=1,
        failed_recording_count=0,
        eligible_candidate_count=len(candidates),
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, (recording,), candidates),
    )
    return ReviewIntakeProjection(manifest, (recording,), tuple(candidates))


def _settings() -> SpectrogramSettingsSnapshot:
    return SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version="review-stft-v1",
        render_version="review-raster-v1",
        effective_settings={
            "frequency_max_hz": 4_200,
            "sound_detail": "balanced",
            "context_seconds": 2,
            "contrast_db": 50,
            "palette": "magma",
            "exact_window_ms": None,
            "overlap_percent": 50,
            "frequency_min_hz": 0,
        },
    )


def _create_session(
    controller: ReviewSessionController,
    projection: ReviewIntakeProjection,
    settings: SpectrogramSettingsSnapshot,
    *,
    name: str,
    suffix: str,
    created_at: str,
):
    return controller.store.create_session(
        name=name,
        source=ReviewSessionSource.from_projection(
            projection,
            score_semantics=("binary_softmax_target_output_index_1; not_a_calibrated_probability"),
            eligibility_threshold=0.5,
        ),
        candidates=projection.candidates,
        settings=settings,
        owner_id=controller.owner_id,
        created_at=created_at,
        session_id="rsn_" + suffix * 32,
    )


def _label(
    controller: ReviewSessionController,
    session,
    projection: ReviewIntakeProjection,
    labels: tuple[ReviewLabel, ...],
):
    for index, label in enumerate(labels):
        session = controller.set_label(
            session.session_id,
            projection.candidates[index].candidate_id,
            label,
            expected_revision=session.revision,
            modified_at=f"2026-11-06T09:{10 + index:02d}:00.000Z",
        ).session
    return session


def _button(widget, text: str) -> QPushButton:
    return next(button for button in widget.findChildren(QPushButton) if button.text() == text)


def _visible_message_box() -> QMessageBox | None:
    return next(
        (
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMessageBox) and widget.isVisible()
        ),
        None,
    )


def _set_viewport(qtbot, window: StudioWindow, width: int, height: int) -> None:
    screen = window.screen() or QApplication.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry()
    assert width <= available.width() and height <= available.height()
    window.resize(width, height)
    window.move(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )
    window.show()
    window.raise_()
    window.activateWindow()
    qtbot.wait(500)
    actual = (window.size().width(), window.size().height())
    assert actual[0] == width
    assert height - 32 <= actual[1] <= height, (
        f"Cocoa viewport is {actual[0]}x{actual[1]}, expected approximately {width}x{height}"
    )


def _capture(
    qtbot,
    window: StudioWindow,
    output: Path,
    name: str,
    captures: list[dict[str, object]],
    *,
    modal: bool = False,
) -> None:
    if not modal:
        window.raise_()
        window.activateWindow()
    QApplication.processEvents()
    qtbot.wait(350)
    screen = window.screen() or QApplication.primaryScreen()
    assert screen is not None
    origin = window.mapToGlobal(QPoint(0, 0))
    pixmap = screen.grabWindow(
        0,
        origin.x(),
        origin.y(),
        window.width(),
        window.height(),
    )
    assert not pixmap.isNull(), "Cocoa desktop capture returned an empty image"
    destination = output / name
    assert pixmap.save(str(destination), "PNG")
    captures.append(
        {
            "file": name,
            "logical_viewport": [window.width(), window.height()],
            "png_pixels": [pixmap.width(), pixmap.height()],
            "pixmap_device_pixel_ratio": pixmap.devicePixelRatio(),
            "modal": modal,
        }
    )


def _capture_dialog_then_cancel(
    qtbot,
    window: StudioWindow,
    output: Path,
    name: str,
    captures: list[dict[str, object]],
) -> None:
    dialog = _visible_message_box()
    assert dialog is not None
    assert dialog.defaultButton() is not None
    assert dialog.defaultButton().text() == "Cancel"
    _capture(qtbot, window, output, name, captures, modal=True)
    _button(dialog, "Cancel").click()


def test_visible_cocoa_captures_complete_rv09_owner_review_set(qapp, qtbot, tmp_path: Path):
    """Cases: IT-REVW-013; IT-REVW-014."""
    requested_output = os.environ.get("BIOCALL_RV09_EVIDENCE_DIR")
    if not requested_output:
        pytest.skip("Set BIOCALL_RV09_EVIDENCE_DIR for the deliberate visible capture run.")
    assert qapp.platformName() == "cocoa"
    output = Path(requested_output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    create_studio_application()
    source_root = tmp_path / "field-recordings"
    recording_name = "woodland-dawn-2026-11-05.wav"
    source_sha256 = _write_wav(source_root / "recordings" / recording_name)
    projection = _projection(source_sha256=source_sha256, recording_name=recording_name)
    settings = _settings()
    suite_root = tmp_path / "application-data"
    controller = ReviewSessionController(suite_root)
    controller.ensure_default_preset(settings, saved_at="2026-11-06T09:00:00.000Z")

    finalized = _create_session(
        controller,
        projection,
        settings,
        name="Woodland dawn — finalized",
        suffix="f",
        created_at="2026-11-06T09:01:00.000Z",
    )
    finalized = _label(
        controller,
        finalized,
        projection,
        (ReviewLabel.CALL, ReviewLabel.CALL, ReviewLabel.NOT_CALL, ReviewLabel.CALL),
    )
    finalized = controller.finalize_session(
        finalized.session_id,
        expected_revision=finalized.revision,
        finalized_at="2026-11-06T09:30:00.000Z",
    )

    closed = _create_session(
        controller,
        projection,
        settings,
        name="Ridge recorder — paused",
        suffix="c",
        created_at="2026-11-06T09:31:00.000Z",
    )
    closed = _label(
        controller,
        closed,
        projection,
        (ReviewLabel.NOT_CALL, ReviewLabel.CALL, ReviewLabel.NOT_CALL),
    )
    closed = controller.close_session(
        closed.session_id,
        expected_revision=closed.revision,
        closed_at="2026-11-06T09:40:00.000Z",
    )

    active = _create_session(
        controller,
        projection,
        settings,
        name="Morning woodland review",
        suffix="a",
        created_at="2026-11-06T09:41:00.000Z",
    )
    active = _label(
        controller,
        active,
        projection,
        (
            ReviewLabel.CALL,
            ReviewLabel.NOT_CALL,
            ReviewLabel.CALL,
            ReviewLabel.CALL,
            ReviewLabel.NOT_CALL,
        ),
    )

    result_choices = (
        ReviewResultChoice(
            collection_id=projection.manifest.collection_id,
            result_id=projection.manifest.result_id,
            name="Woodland dawn survey",
            kind="Original",
            completed_at="2026-11-05T07:45:00.000Z",
            eligible_count=12,
        ),
        ReviewResultChoice(
            collection_id="det_" + "8" * 32,
            result_id="pub_" + "9" * 32,
            name="Ridge recorder survey",
            kind="RF refined",
            completed_at="2026-11-04T18:20:00.000Z",
            eligible_count=46,
        ),
    )
    page = ReviewWorkspacePage(
        controller,
        result_provider=lambda: result_choices,
        source_root_resolver=lambda _session: source_root,
    )
    detect_controller = DetectWorkspaceController(suite_root)
    window = StudioWindow(detect_controller, page)
    qtbot.addWidget(window)
    captures: list[dict[str, object]] = []

    try:
        _set_viewport(qtbot, window, 1280, 820)
        window.show_workspace(WorkspaceRoute.STUDIO)
        _capture(qtbot, window, output, "00-studio.png", captures)

        window.show_workspace(WorkspaceRoute.REVIEW)
        page.show_landing()
        _capture(qtbot, window, output, "01-choose-result.png", captures)

        page.show_sessions(select_session_id=active.session_id)
        _capture(qtbot, window, output, "02-sessions.png", captures)

        page.open_session(active.session_id)
        qtbot.waitUntil(
            lambda: len(page.cache.valid_content_keys()) >= len(projection.candidates),
            timeout=30_000,
        )
        qtbot.waitUntil(
            lambda: page.calibration_store.calibration(SpectrogramImageTier.THUMBNAIL) is not None,
            timeout=15_000,
        )
        page.show_spectrograms()
        _button(page.cache_page, "Generate all").click()
        qtbot.waitUntil(lambda: page._generation_batch_id is None, timeout=15_000)

        page.show_session()
        _button(page.session_page, "Gallery").click()
        qtbot.waitUntil(lambda: page.gallery_model.cached_thumbnail_count >= 3, timeout=15_000)
        _capture(qtbot, window, output, "03-gallery.png", captures)

        _button(page.session_page, "List").click()
        _capture(qtbot, window, output, "04-list.png", captures)

        _button(page.session_page, "One by one").click()
        qtbot.waitUntil(
            lambda: page.session_page.spectrogram.metadata is not None,
            timeout=15_000,
        )
        _capture(qtbot, window, output, "05-one-by-one.png", captures)

        page.show_spectrograms()
        _button(page.cache_page, "Generate all").click()
        qtbot.waitUntil(
            lambda: page.cache_page.availability_label.text() == "12 of 12 spectrograms available",
            timeout=15_000,
        )
        _capture(qtbot, window, output, "06-spectrograms.png", captures)

        page.show_session()
        _button(page.session_page, "One by one").click()
        QTimer.singleShot(
            250,
            lambda: _capture_dialog_then_cancel(qtbot, window, output, "07-finalize.png", captures),
        )
        _button(page.session_page, "Finalize").click()
        assert controller.store.get_session(active.session_id).revision == active.revision

        page.open_session(finalized.session_id)
        page.show_export()
        assert page.export_page.decisions_total.text() == "11 included · 1 excluded"
        assert page.export_page.previous_exports.text() == "No exports yet."
        _capture(qtbot, window, output, "08-export.png", captures)

        page.open_session(active.session_id)
        _set_viewport(qtbot, window, 700, 790)
        _button(page.session_page, "Gallery").click()
        qtbot.waitUntil(lambda: page.gallery_model.cached_thumbnail_count >= 2, timeout=15_000)
        page.session_page.gallery.doItemsLayout()
        qtbot.waitUntil(
            lambda: (
                not page.session_page.gallery.visualRect(page.gallery_model.index(1, 0)).isEmpty()
            )
        )
        first = page.session_page.gallery.visualRect(page.gallery_model.index(0, 0))
        second = page.session_page.gallery.visualRect(page.gallery_model.index(1, 0))
        assert first.y() == second.y() and first.x() != second.x()
        _capture(qtbot, window, output, "09-compact-gallery.png", captures)

        _button(page.session_page, "One by one").click()
        qtbot.waitUntil(
            lambda: page.session_page.spectrogram.metadata is not None,
            timeout=15_000,
        )
        _capture(qtbot, window, output, "10-compact-one-by-one.png", captures)

        _set_viewport(qtbot, window, 520, 790)
        assert not page.session_page.accept_all_button.isVisibleTo(window)
        _capture(qtbot, window, output, "11-narrow-one-by-one.png", captures)

        _set_viewport(qtbot, window, 1280, 820)
        page.show_settings()
        _capture(qtbot, window, output, "12-settings.png", captures)

        page.show_sessions(select_session_id=closed.session_id)
        QTimer.singleShot(
            250,
            lambda: _capture_dialog_then_cancel(
                qtbot, window, output, "13-delete-session.png", captures
            ),
        )
        _button(page.sessions_page, "Delete session").click()
        assert controller.store.get_session(closed.session_id) == closed

        page.show_data_settings()
        _capture(qtbot, window, output, "14-review-data-folder.png", captures)

        screen = window.screen() or QApplication.primaryScreen()
        assert screen is not None
        metadata = {
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "capture_mode": "visible Cocoa QScreen desktop capture of the live Studio client area",
            "os": platform.platform(),
            "qt_version": qVersion(),
            "qt_platform": qapp.platformName(),
            "screen": {
                "name": screen.name(),
                "geometry": [
                    screen.geometry().width(),
                    screen.geometry().height(),
                ],
                "available_geometry": [
                    screen.availableGeometry().width(),
                    screen.availableGeometry().height(),
                ],
                "device_pixel_ratio": screen.devicePixelRatio(),
            },
            "fixture": {
                "recording": recording_name,
                "wav_sha256": source_sha256,
                "sample_rate_hz": 8_000,
                "duration_seconds": 10,
                "eligible_candidates": len(projection.candidates),
                "sessions": [
                    "Morning woodland review (Open)",
                    "Ridge recorder — paused (Closed)",
                    "Woodland dawn — finalized (Finalized)",
                ],
            },
            "captures": captures,
        }
        (output / "capture-metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        assert len(captures) == 15
    finally:
        for dialog in QApplication.topLevelWidgets():
            if isinstance(dialog, QMessageBox):
                dialog.close()
        page.shutdown()
        controller.shutdown()
        detect_controller.shutdown()
        window.allow_application_close()
        window.close()
