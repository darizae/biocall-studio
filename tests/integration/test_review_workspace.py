# ruff: noqa: E501 -- approved Review interface copy is asserted verbatim.
from __future__ import annotations

import hashlib
import math
import os
import struct
import time
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from alp_ui.components import HelpHint
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
)

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
from biocall_studio.review.gui.models import ReviewCandidateTableModel, ReviewGalleryModel
from biocall_studio.review.gui.workspace import ReviewWorkspacePage

pytestmark = [pytest.mark.integration, pytest.mark.qt]


def _write_wav(path: Path, *, seconds: int = 10, sample_rate: int = 8_000) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(seconds * sample_rate):
        value = int(11_000 * math.sin(2 * math.pi * 750 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(frames)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _projection(count: int, *, source_sha256: str, recording_name: str) -> ReviewIntakeProjection:
    total_frames = (
        max(80_000, 8_000 + max(0, count - 1) * 6_000 + 2_000)
        if count <= 100
        else max(80_000, count * 10 + 1_000)
    )
    candidates = []
    for index in range(count):
        start_frame = 8_000 + index * 6_000 if count <= 100 else index * 10
        end_frame = start_frame + (2_000 if count <= 100 else 5)
        candidates.append(
            EligibleCandidate(
                ordinal=index,
                recording_ordinal=0,
                candidate_id=f"cand_{index:032x}",
                recording_ref="rec_" + "1" * 32,
                recording_key=f"recordings/{recording_name}",
                source_sha256=source_sha256,
                sample_rate_hz=8_000,
                frame_count=total_frames,
                channels=1,
                start_frame=start_frame,
                end_frame=end_frame,
                start_time_ns=(start_frame * 1_000_000_000 + 4_000) // 8_000,
                end_time_ns=(end_frame * 1_000_000_000 + 4_000) // 8_000,
                cnn_target_score=0.55 + (index % 40) / 100,
                rf_target_score=None,
                contributing_windows=1,
            )
        )
    recording = ReviewRecording(
        ordinal=0,
        recording_ref="rec_" + "1" * 32,
        recording_key=f"recordings/{recording_name}",
        source_sha256=source_sha256,
        sample_rate_hz=8_000,
        frame_count=total_frames,
        channels=1,
        failed=False,
        error_code="",
        eligible_candidate_count=count,
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
        source_time_semantics="zero_based_half_open_source_frames_with_integer_nanosecond_projection",
        recording_count=1,
        failed_recording_count=0,
        eligible_candidate_count=count,
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


def _session(
    root: Path,
    *,
    count: int,
    source_sha256: str,
    recording_name: str = "field-call.wav",
) -> tuple[ReviewSessionController, str]:
    controller = ReviewSessionController(root)
    projection = _projection(count, source_sha256=source_sha256, recording_name=recording_name)
    settings = _settings()
    controller.ensure_default_preset(settings, saved_at="2026-11-05T09:00:00.000Z")
    session = controller.store.create_session(
        name="Morning review",
        source=ReviewSessionSource.from_projection(
            projection,
            score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
            eligibility_threshold=0.5,
        ),
        candidates=projection.candidates,
        settings=settings,
        owner_id=controller.owner_id,
        created_at="2026-11-05T10:00:00.000Z",
        session_id="rsn_" + "a" * 32,
    )
    return controller, session.session_id


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


def _click_visible_message_button(text: str) -> None:
    dialog = _visible_message_box()
    assert dialog is not None
    _button(dialog, text).click()


def _capture_if_requested(widget, name: str) -> None:
    output = os.environ.get("BIOCALL_RV05_EVIDENCE_DIR")
    if not output:
        return
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    QApplication.processEvents()
    assert widget.grab().save(str(destination / name), "PNG")


def test_native_review_views_shortcuts_settings_and_compact_state(
    qapp, qtbot, tmp_path: Path
) -> None:
    """Case: IT-REVW-007."""
    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path)
    before = wav_path.read_bytes()
    controller, session_id = _session(tmp_path / "suite", count=4, source_sha256=source_sha256)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    page.resize(1180, 720)
    page.show()
    page.open_session(session_id)

    assert page.current_state is not None
    assert page.current_state.session.name == "Morning review"
    assert _button(page, "Gallery").isEnabled()
    assert _button(page, "List").isEnabled()
    one = _button(page, "One by one")
    qtbot.mouseClick(one, Qt.MouseButton.LeftButton)
    assert page.current_state.view.value == "one_by_one"
    _capture_if_requested(page, "review-one-by-one-normal.png")

    call = next(
        button
        for button in page.findChildren(QPushButton)
        if button.text() == "Call" and button.toolTip()
    )
    not_call = next(
        button
        for button in page.findChildren(QPushButton)
        if button.text() == "Not a call" and button.toolTip()
    )
    clear = _button(page, "Clear label")
    previous = _button(page, "Previous")
    play = _button(page, "Play")
    next_button = _button(page, "Next")
    undo = _button(page, "Undo")
    assert call.toolTip() == "Call · F"
    assert not_call.toolTip() == "Not a call · D"
    assert clear.toolTip() == "Clear label · S"
    assert previous.toolTip() == "Previous · J or ←"
    assert play.toolTip() == "Play / Pause · K or Space"
    assert next_button.toolTip() == "Next · L or →"
    assert undo.toolTip() == "Undo last label action · Ctrl/⌘+Z"

    first_id = page.current_state.current_candidate_id
    page.activateWindow()
    call.setFocus()
    qapp.processEvents()
    qtbot.keyClick(page, Qt.Key.Key_F)
    assert controller.store.candidate_by_id(session_id, first_id).label is ReviewLabel.CALL
    assert page.current_state.current_candidate_id != first_id

    name = page.findChild(QLineEdit, "reviewSessionName")
    assert name is not None
    name.setFocus()
    current = page.current_state.current_candidate_id
    qtbot.keyClick(name, Qt.Key.Key_D)
    assert page.current_state.current_candidate_id == current
    assert controller.store.candidate_by_id(session_id, current).label is ReviewLabel.UNREVIEWED

    shortcut_button = _button(page, "Keyboard shortcuts")
    qtbot.mouseClick(shortcut_button, Qt.MouseButton.LeftButton)
    dialog = QApplication.activeModalWidget()
    assert dialog is not None
    dialog_text = " ".join(
        child.text() for child in dialog.findChildren(QPushButton) if child.text()
    )
    assert "Close" in dialog_text
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: QApplication.activeModalWidget() is None)

    _button(page, "List").click()
    search = page.findChild(QLineEdit, "reviewRecordingSearch")
    assert search is not None and search.placeholderText() == "Search recordings"
    search.setText("field-call")
    qtbot.waitUntil(lambda: page.current_state.search == "field-call")
    assert page.findChild(QTableView, "reviewCandidateTable") is not None

    page.show_settings()
    assert len(page.settings_page.controls) == 8
    assert len(page.settings_page.findChildren(HelpHint)) == 8
    assert page.settings_page.preset_select.currentText() == "Default"
    assert not page.settings_page.edit_button.isEnabled()
    assert not page.settings_page.delete_button.isEnabled()
    assert page.settings_page.advanced_box.isChecked() is False
    assert _button(page.settings_page, "Test WAV").isEnabled()
    _capture_if_requested(page, "review-settings-normal.png")

    page.show_session()
    page.resize(700, 720)
    qtbot.waitUntil(lambda: page.compact)
    page.resize(700, 720)
    qtbot.waitUntil(lambda: page.width() <= 700)
    assert page.session_page.isVisible()
    assert page.current_state.search == "field-call"
    _capture_if_requested(page, "review-list-compact.png")
    assert wav_path.read_bytes() == before
    controller.shutdown()


def test_50k_native_models_page_without_eager_widgets_and_keep_event_loop_responsive(
    qapp, qtbot, tmp_path: Path
) -> None:
    """Case: IT-REVW-008."""
    controller, session_id = _session(
        tmp_path / "suite",
        count=50_000,
        source_sha256="2" * 64,
        recording_name="large-result.wav",
    )
    from biocall_studio.review.application.view_state import ReviewFilter, ReviewViewState

    state = ReviewViewState(controller, session_id)
    table = ReviewCandidateTableModel(state)
    gallery = ReviewGalleryModel(state)
    assert table.rowCount() == gallery.rowCount() == 50_000

    fired = False

    def mark_fired() -> None:
        nonlocal fired
        fired = True

    QTimer.singleShot(0, mark_fired)
    started = time.perf_counter()
    for row in (0, 1, 999, 25_000, 49_999):
        assert table.data(table.index(row, 0), Qt.ItemDataRole.DisplayRole)
        assert gallery.data(gallery.index(row, 0), Qt.ItemDataRole.DisplayRole)
    qapp.processEvents()
    elapsed = time.perf_counter() - started
    assert fired
    assert elapsed < 5.0
    assert table.cached_row_count <= 500
    assert gallery.cached_row_count <= 500

    state.set_query(filter_name=ReviewFilter.UNREVIEWED, search="large-result")
    table.refresh()
    gallery.refresh()
    assert table.rowCount() == gallery.rowCount() == 50_000
    assert table.cached_row_count == gallery.cached_row_count == 0
    assert table.rowCount(table.index(0, 0)) == 0
    controller.shutdown()


def test_native_cache_generation_preset_switch_and_saved_examples_are_bounded(
    qapp, qtbot, monkeypatch, tmp_path: Path
) -> None:
    """Case: IT-REVW-007."""
    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path)
    before = wav_path.read_bytes()
    controller, session_id = _session(tmp_path / "suite", count=4, source_sha256=source_sha256)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    page.resize(1180, 720)
    page.show()
    page.open_session(session_id)

    page.show_spectrograms()
    assert page.cache_page.output_value.text() == "Unknown"
    _button(page.cache_page, "Generate all").click()
    qtbot.waitUntil(lambda: _visible_message_box() is not None, timeout=10_000)
    _click_visible_message_button("Continue")
    qtbot.waitUntil(lambda: len(page.cache.valid_content_keys()) == 4, timeout=20_000)
    qtbot.waitUntil(
        lambda: page.cache_page.availability_label.text()
        == "4 of 4 spectrograms available",
        timeout=10_000,
    )

    page.show_session()
    _button(page, "Gallery").click()
    thumbnail = page.gallery_model.data(
        page.gallery_model.index(0, 0), Qt.ItemDataRole.DecorationRole
    )
    assert isinstance(thumbnail, QPixmap) and not thumbnail.isNull()
    page.session_page.gallery.doItemsLayout()
    qtbot.waitUntil(
        lambda: not page.session_page.gallery.visualRect(
            page.gallery_model.index(0, 0)
        ).isEmpty()
    )
    _capture_if_requested(page, "review-gallery-normal.png")
    labels_before = tuple(
        controller.store.candidate_by_id(session_id, f"cand_{index:032x}").label
        for index in range(4)
    )

    page.show_settings()
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Birdsong detail", True),
    )
    _button(page.settings_page, "New preset").click()
    palette = page.settings_page._controls_by_name["palette"]
    palette.setCurrentIndex(page.settings_page._control_values["palette"].index("viridis"))
    _button(page.settings_page, "Save changes").click()
    alternate = next(
        preset
        for preset in controller.list_presets()
        if preset.preset_name == "Birdsong detail"
    )
    assert alternate.effective_settings["palette"] == "viridis"
    original_session = controller.store.get_session(session_id)
    page.show_spectrograms()
    alternate_index = page.cache_page.preset_select.control.findData(alternate.preset_id)
    page.cache_page.preset_select.setCurrentIndex(alternate_index)
    _button(page.cache_page, "Change preset").click()
    qtbot.waitUntil(lambda: _visible_message_box() is not None, timeout=10_000)
    dialog = _visible_message_box()
    assert dialog is not None
    assert "Change Default to Birdsong detail?" in dialog.text()
    assert "Your labels won't change." in dialog.text()
    _click_visible_message_button("Change preset")
    qtbot.waitUntil(
        lambda: controller.store.load_settings(session_id).preset_id == alternate.preset_id,
        timeout=10_000,
    )
    changed_session = controller.store.get_session(session_id)
    assert changed_session.settings_epoch == original_session.settings_epoch + 1
    assert tuple(
        controller.store.candidate_by_id(session_id, f"cand_{index:032x}").label
        for index in range(4)
    ) == labels_before

    page.show_settings()
    alternate_settings_index = page.settings_page.preset_select.control.findData(
        alternate.preset_id
    )
    page.settings_page.preset_select.setCurrentIndex(alternate_settings_index)
    page.settings_page.preview_wav(wav_path)
    assert page.settings_page._preview_raster is not None
    _button(page.settings_page, "Save example").click()
    example_directory = page.settings_page.example_store._directory(alternate.preset_id)
    metadata_path = next(example_directory.glob("example_*.json"))
    metadata_text = metadata_path.read_text(encoding="utf-8")
    assert str(wav_path) not in metadata_text
    assert page.settings_page.examples_label.text() == "Saved example"

    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Birdsong refined", True),
    )
    _button(page.settings_page, "Rename").click()
    assert _button(page.settings_page, "Save changes").isEnabled()
    QTimer.singleShot(0, lambda: _click_visible_message_button("Save preset"))
    _button(page.settings_page, "Save changes").click()
    assert page.settings_page.preset_select.currentText() == "Birdsong refined"
    assert page.settings_page.examples_label.text() == "Saved example · earlier version"

    QTimer.singleShot(0, lambda: _click_visible_message_button("Delete"))
    _button(page.settings_page, "Delete").click()
    assert not example_directory.exists()
    assert wav_path.read_bytes() == before
    assert tuple(
        controller.store.candidate_by_id(session_id, f"cand_{index:032x}").label
        for index in range(4)
    ) == labels_before
    page.shutdown()
    controller.shutdown()
