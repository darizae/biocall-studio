# ruff: noqa: E501 -- approved Review interface copy is asserted verbatim.
from __future__ import annotations

import errno
import gc
import hashlib
import json
import math
import os
import resource
import struct
import time
import tracemalloc
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from alp_ui.components import HelpHint
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    Qt,
    QTimer,
)
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
from biocall_studio.review.application.generation import (
    GenerationCompletion,
    GenerationToken,
)
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


def _write_wav(path: Path, *, seconds: int | float = 10, sample_rate: int = 8_000) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(round(seconds * sample_rate)):
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
    page.resize(520, 720)
    _button(page, "One by one").click()
    qtbot.waitUntil(lambda: page.navigation.narrow)
    assert page.session_page.detail_card.isVisibleTo(page)
    assert page.session_page.action_card.isVisibleTo(page)
    assert all(
        button.isVisibleTo(page)
        for button in (
            page.session_page.call_button,
            page.session_page.not_call_button,
            page.session_page.previous_button,
            page.session_page.next_button,
        )
    )
    _capture_if_requested(page, "review-one-by-one-narrow.png")
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


def test_empty_cache_gallery_generates_visible_and_nearby_rows_without_bulk(
    qapp, qtbot, monkeypatch, tmp_path: Path
) -> None:
    """Case: IT-REVW-015."""
    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path, seconds=27.5)
    source_before = wav_path.read_bytes()
    controller, session_id = _session(tmp_path / "suite", count=36, source_sha256=source_sha256)

    import biocall_studio.review.gui.workspace as workspace_module
    import biocall_studio.review.workflows.audio as audio_module

    real_read = workspace_module.read_candidate_audio
    real_hash = audio_module._hash_stream
    hash_calls = 0

    def delayed_read(*args, **kwargs):
        time.sleep(0.12)
        return real_read(*args, **kwargs)

    def counted_hash(stream, cancelled):
        nonlocal hash_calls
        hash_calls += 1
        return real_hash(stream, cancelled)

    monkeypatch.setattr(workspace_module, "read_candidate_audio", delayed_read)
    monkeypatch.setattr(audio_module, "_hash_stream", counted_hash)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    painted_rows: list[int] = []
    page.resize(920, 620)
    page.show()
    page.open_session(session_id)
    page.gallery_model.dataChanged.connect(
        lambda first, _last, _roles: painted_rows.append(first.row())
    )
    page.session_page.gallery.doItemsLayout()

    qtbot.waitUntil(
        lambda: page.gallery_model.cached_thumbnail_count >= 2 or bool(page._spectrogram_failures),
        timeout=15_000,
    )
    assert not page._spectrogram_failures
    start, end = page._visible_gallery_rows()
    assert end > start
    assert painted_rows
    assert all(0 <= row < page.gallery_model.rowCount() for row in painted_rows)
    assert page.gallery_model.cached_thumbnail_count <= 64
    assert page.supervisor.pending_count <= page.supervisor.max_pending
    assert page.cache.valid_content_keys()
    assert page._generation_batch_id is None

    dropped: list[str] = []
    real_drop = page.supervisor.drop_prefetch_except

    def record_drop(retained):
        result = real_drop(retained)
        dropped.extend(result)
        return result

    monkeypatch.setattr(page.supervisor, "drop_prefetch_except", record_drop)
    page.session_page.gallery.scrollTo(
        page.gallery_model.index(page.gallery_model.rowCount() - 1, 0),
        page.session_page.gallery.ScrollHint.PositionAtTop,
    )
    monkeypatch.setattr(page, "_visible_gallery_rows", lambda: (24, 30))
    page._schedule_gallery_window()
    qtbot.waitUntil(lambda: bool(dropped), timeout=10_000)
    qtbot.waitUntil(lambda: page.gallery_model.cached_thumbnail_count >= 4, timeout=15_000)
    assert hash_calls == 1
    assert wav_path.read_bytes() == source_before

    state = page.current_state
    assert state is not None
    snapshot = controller.store.load_settings(session_id)
    row = page.gallery_model.candidate_at(0)
    token = GenerationToken(
        session_id,
        state.session.settings_epoch,
        snapshot.settings_digest,
        row.source_sha256,
        request_epoch=page._gallery_epoch,
    )
    for index in range(10_000):
        page._spectrogram_job_ready(
            (
                "thumbnail",
                0,
                row.candidate_id,
                page._gallery_epoch,
                GenerationCompletion(
                    content_key=f"spec_{index:064x}",
                    outcome="failed",
                    token=token,
                    entry=None,
                    prepared=None,
                    display_payload=None,
                    elapsed_milliseconds=1,
                    error=f"failure-{index:05d}:" + "x" * 600,
                ),
            )
        )
    assert len(page._spectrogram_failures) == 64
    assert all(len(message) <= 512 for message in page._spectrogram_failures)
    assert page._spectrogram_failures[0].startswith("failure-09936:")
    assert page._spectrogram_failures[-1].startswith("failure-09999:")

    for _cycle in range(10):
        page._set_search("no matching recording")
        assert page.gallery_model.cached_thumbnail_count == 0
        page._set_search("")
        assert page.gallery_model.cached_thumbnail_count == 0
        page._set_filter("call")
        assert page.gallery_model.cached_thumbnail_count == 0
        page._set_filter("all")
        assert page.gallery_model.cached_thumbnail_count == 0
        page.open_session(session_id)
        assert page.gallery_model.cached_thumbnail_count == 0
        if page.gallery_model.rowCount():
            first = page.gallery_model.index(0, 0)
            assert page.gallery_model.data(first, Qt.ItemDataRole.DecorationRole) is None
            assert page.gallery_model.data(first, Qt.ItemDataRole.UserRole + 1) is None
    page.shutdown()
    controller.shutdown()


@pytest.mark.native_cocoa
def test_native_cocoa_review_navigation_records_memory_diagnostics(
    qapp, qtbot, tmp_path: Path
) -> None:
    """Case: IT-REVW-015."""
    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path)
    source_before = wav_path.read_bytes()
    controller, first_session_id = _session(
        tmp_path / "suite", count=8, source_sha256=source_sha256
    )
    first = controller.store.get_session(first_session_id)
    controller.close_session(
        first_session_id,
        expected_revision=first.revision,
        closed_at="2026-11-07T09:00:00.000Z",
    )
    projection = _projection(
        8,
        source_sha256=source_sha256,
        recording_name="field-call.wav",
    )
    second = controller.store.create_session(
        name="Afternoon review",
        source=ReviewSessionSource.from_projection(
            projection,
            score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
            eligibility_threshold=0.5,
        ),
        candidates=projection.candidates,
        settings=_settings(),
        owner_id=controller.owner_id,
        created_at="2026-11-07T10:00:00.000Z",
        session_id="rsn_" + "b" * 32,
    )

    tracemalloc.start()
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    page.resize(980, 700)
    page.show()
    page.open_session(second.session_id)
    page._set_view("gallery")
    qtbot.waitUntil(lambda: page.gallery_model.cached_thumbnail_count > 0, timeout=20_000)
    gc.collect()
    traced_start, traced_peak_start = tracemalloc.get_traced_memory()
    rss_start = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    max_gallery_pairs = page.gallery_model.cached_thumbnail_count
    max_failure_count = len(page._spectrogram_failures)

    for cycle in range(8):
        page.open_session(first_session_id if cycle % 2 else second.session_id)
        page._set_view("gallery")
        page._set_search("field-call")
        page._set_filter("all")
        qtbot.waitUntil(
            lambda: page.gallery_model.cached_thumbnail_count > 0,
            timeout=20_000,
        )
        page.show_spectrograms()
        page.show_session()
        qapp.processEvents()
        assert page.gallery_model.cached_thumbnail_count <= 64
        assert len(page._spectrogram_failures) <= 64
        max_gallery_pairs = max(
            max_gallery_pairs,
            page.gallery_model.cached_thumbnail_count,
        )
        max_failure_count = max(max_failure_count, len(page._spectrogram_failures))

    qtbot.waitUntil(
        lambda: page.supervisor.pending_count == 0 and page.supervisor.active_count == 0,
        timeout=20_000,
    )
    terminal_batches = tuple(batch for batch in page.supervisor._batches.values() if batch.done)
    assert terminal_batches
    assert all(not batch.states and batch.iterator is None for batch in terminal_batches)
    terminal_batch_count = len(terminal_batches)
    gallery_pairs = page.gallery_model.cached_thumbnail_count
    failure_count = len(page._spectrogram_failures)
    retained_state_keys = sum(len(batch.states) for batch in terminal_batches)

    page.shutdown()
    page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    del terminal_batches
    page = None
    gc.collect()
    traced_end, traced_peak_end = tracemalloc.get_traced_memory()
    rss_end = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    tracemalloc.stop()
    controller.shutdown()
    assert wav_path.read_bytes() == source_before

    report = {
        "gallery_pair_count": gallery_pairs,
        "iterations": 8,
        "max_gallery_pair_count": max_gallery_pairs,
        "max_retained_failure_count": max_failure_count,
        "retained_failure_count": failure_count,
        "terminal_batch_count": terminal_batch_count,
        "terminal_state_key_count": retained_state_keys,
        "max_rss_bytes": {
            "start": rss_start,
            "end": rss_end,
            "delta": rss_end - rss_start,
        },
        "tracemalloc_bytes": {
            "start_current": traced_start,
            "start_peak": traced_peak_start,
            "end_current": traced_end,
            "end_peak": traced_peak_end,
            "current_delta": traced_end - traced_start,
        },
    }
    report_path = Path(
        os.environ.get(
            "BIOCALL_STUDIO_REVIEW_MEMORY_REPORT",
            tmp_path / "review-memory-retention.json",
        )
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert report_path.is_file()


def test_rapid_detail_navigation_labels_and_play_do_not_block_or_paint_stale(
    qapp, qtbot, monkeypatch, tmp_path: Path
) -> None:
    """Case: IT-REVW-016."""
    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path)
    controller, session_id = _session(tmp_path / "suite", count=6, source_sha256=source_sha256)

    import biocall_studio.review.gui.workspace as workspace_module
    import biocall_studio.review.workflows.audio as audio_module

    real_read = workspace_module.read_candidate_audio
    real_render = workspace_module.render_spectrogram
    real_hash = audio_module._hash_stream
    hash_calls = 0
    rendered: list[str] = []

    def delayed_read(*args, **kwargs):
        time.sleep(0.12)
        return real_read(*args, **kwargs)

    def delayed_render(samples, request):
        time.sleep(0.08)
        rendered.append(request.candidate_id)
        return real_render(samples, request)

    def counted_hash(stream, cancelled):
        nonlocal hash_calls
        hash_calls += 1
        return real_hash(stream, cancelled)

    monkeypatch.setattr(workspace_module, "read_candidate_audio", delayed_read)
    monkeypatch.setattr(workspace_module, "render_spectrogram", delayed_render)
    monkeypatch.setattr(audio_module, "_hash_stream", counted_hash)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    loaded_clips: list[bytes] = []
    played: list[bool] = []
    monkeypatch.setattr(page.playback, "load_clip", loaded_clips.append)
    monkeypatch.setattr(page.playback, "play", lambda: played.append(True))
    page.resize(980, 650)
    page.show()
    page.open_session(session_id)

    beats = 0
    heartbeat = QTimer(page)
    heartbeat.setInterval(10)

    def beat() -> None:
        nonlocal beats
        beats += 1

    heartbeat.timeout.connect(beat)
    heartbeat.start()
    started = time.perf_counter()
    page._set_view("one_by_one")
    first = page.current_state.current_candidate_id
    page._shortcut_triggered("F")
    second = page.current_state.current_candidate_id
    page._shortcut_triggered("D")
    third = page.current_state.current_candidate_id
    page._shortcut_triggered("S")
    page._shortcut_triggered("K")
    page._next()
    action_elapsed = time.perf_counter() - started
    current = page.current_state.current_candidate_id
    assert len({first, second, third, current}) >= 3
    assert action_elapsed < 0.25
    assert played == []

    qtbot.waitUntil(lambda: page.session_page.play_button.isEnabled(), timeout=20_000)
    qtbot.waitUntil(lambda: beats >= 10, timeout=5_000)
    assert page.session_page.spectrogram.metadata is not None
    assert page.session_page.spectrogram.metadata.candidate_id == current
    assert len(loaded_clips) == 1
    assert hash_calls == 1

    rendered_before_revisit = rendered.count(current)
    page._previous()
    qtbot.waitUntil(lambda: page.session_page.play_button.isEnabled(), timeout=15_000)
    page._next()
    qtbot.waitUntil(
        lambda: (
            page.session_page.play_button.isEnabled()
            and page.session_page.spectrogram.metadata is not None
            and page.session_page.spectrogram.metadata.candidate_id == current
        ),
        timeout=15_000,
    )
    assert rendered.count(current) == rendered_before_revisit
    heartbeat.stop()
    page.shutdown()
    controller.shutdown()


def test_measured_retention_pressure_clear_disk_full_restart_and_delete(
    qapp, qtbot, monkeypatch, tmp_path: Path
) -> None:
    """Case: IT-REVW-017."""
    import biocall_studio.review.gui.workspace as workspace_module
    import biocall_studio.review.persistence.cache as cache_module

    source_root = tmp_path / "source"
    wav_path = source_root / "recordings" / "field-call.wav"
    source_sha256 = _write_wav(wav_path, seconds=23)
    source_before = wav_path.read_bytes()
    suite_root = tmp_path / "suite"
    controller, session_id = _session(suite_root, count=30, source_sha256=source_sha256)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    page.resize(920, 620)
    page.show()
    page.open_session(session_id)

    # Before a ten-image local cohort exists, bulk sizing stays honestly Unknown.
    page.show_spectrograms()
    assert page.cache_page.output_value.text() == "Unknown"
    page.show_session()
    qtbot.waitUntil(
        lambda: (
            page.calibration_store.calibration(
                page._request_for_row(
                    page.gallery_model.candidate_at(0),
                    controller.store.load_settings(session_id),
                    tier=workspace_module.SpectrogramImageTier.THUMBNAIL,
                ).tier
            )
            is not None
        ),
        timeout=20_000,
    )

    calibration = page.calibration_store.calibration(
        workspace_module.SpectrogramImageTier.THUMBNAIL
    )
    assert calibration is not None and calibration.sample_count >= 10
    page.cache.set_limit_bytes(1)
    page.show_spectrograms()
    assert page.cache_page.output_value.text() != "Unknown"
    _button(page.cache_page, "Generate all").click()
    qtbot.waitUntil(
        lambda: (
            page._generation_batch_id is not None
            or "Retained" in page.cache_page.progress_label.text()
        ),
        timeout=20_000,
    )
    qtbot.waitUntil(
        lambda: (
            page._generation_batch_id is None
            and "Retained 30 of 30" in page.cache_page.progress_label.text()
        ),
        timeout=30_000,
    )
    assert page.cache.limit_bytes > 1
    assert len(page.cache.valid_content_keys()) == 30

    page.show_session()
    page._set_view("list")
    selection = QItemSelection(
        page.table_model.index(0, 0),
        page.table_model.index(29, page.table_model.columnCount() - 1),
    )
    page.session_page.table.selectionModel().select(
        selection,
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert len(page.current_state.selected_candidate_ids) == 30
    assert page.session_page.selection_label.text() == "30 selected"
    cleared: list[str] = []
    real_clear = page.supervisor.clear_cache

    def record_clear(keys):
        cleared.extend(keys)
        return real_clear(keys)

    monkeypatch.setattr(page.supervisor, "clear_cache", record_clear)
    page._clear_selected_spectrograms()
    assert len(cleared) == 60
    assert page.cache.valid_content_keys() == ()

    # A failed atomic publication leaves no object or staging bytes and does not touch sources.
    page._set_view("gallery")
    snapshot = controller.store.load_settings(session_id)
    row = page.gallery_model.candidate_at(0)
    request = page._request_for_row(
        row, snapshot, tier=workspace_module.SpectrogramImageTier.THUMBNAIL
    )
    failed_key = workspace_module.spectrogram_content_key(request)
    real_replace = cache_module.os.replace

    def disk_full(source_path, target_path):
        if Path(target_path) == page.cache.object_path(failed_key):
            raise OSError(errno.ENOSPC, "injected cache pressure")
        return real_replace(source_path, target_path)

    monkeypatch.setattr(cache_module.os, "replace", disk_full)
    failures_before = len(page._spectrogram_failures)
    page._queue_thumbnail(
        0,
        row,
        snapshot,
        source_root,
        priority=workspace_module.CachePriority.VISIBLE_THUMBNAIL,
        gallery_epoch=page._gallery_epoch,
    )
    qtbot.waitUntil(
        lambda: len(page._spectrogram_failures) > failures_before,
        timeout=15_000,
    )
    assert page.cache.lookup(failed_key) is None
    assert tuple(page.cache.staging_root.iterdir()) == ()
    monkeypatch.setattr(cache_module.os, "replace", real_replace)

    # Session deletion cancels newly queued work; relocation remains blocked while it is open.
    assert not page.data_location_change_allowed
    page._requested_thumbnails.discard((page._gallery_epoch, failed_key))
    page._queue_thumbnail(
        0,
        row,
        snapshot,
        source_root,
        priority=workspace_module.CachePriority.VISIBLE_THUMBNAIL,
        gallery_epoch=page._gallery_epoch,
    )
    session = controller.store.get_session(session_id)
    QTimer.singleShot(0, lambda: _click_visible_message_button("Delete"))
    page._confirm_delete_session(session)
    qtbot.waitUntil(lambda: controller.list_sessions() == (), timeout=20_000)
    assert wav_path.read_bytes() == source_before
    page.shutdown()
    controller.shutdown()

    reopened = ReviewSessionController(suite_root)
    assert reopened.list_sessions() == ()
    assert wav_path.read_bytes() == source_before
    reopened.shutdown()


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

    qtbot.waitUntil(lambda: len(page.cache.valid_content_keys()) == 4, timeout=20_000)
    page.show_spectrograms()
    assert page.cache_page.output_value.text() == "Unknown"
    _button(page.cache_page, "Generate all").click()
    qtbot.waitUntil(
        lambda: page.cache_page.availability_label.text() == "4 of 4 spectrograms available",
        timeout=10_000,
    )

    page.show_session()
    _button(page, "Gallery").click()
    qtbot.waitUntil(lambda: page.gallery_model.cached_thumbnail_count > 0, timeout=10_000)
    thumbnail = page.gallery_model.data(
        page.gallery_model.index(0, 0), Qt.ItemDataRole.DecorationRole
    )
    assert isinstance(thumbnail, QPixmap) and not thumbnail.isNull()
    page.session_page.gallery.doItemsLayout()
    qtbot.waitUntil(
        lambda: not page.session_page.gallery.visualRect(page.gallery_model.index(0, 0)).isEmpty()
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
        preset for preset in controller.list_presets() if preset.preset_name == "Birdsong detail"
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
    assert (
        tuple(
            controller.store.candidate_by_id(session_id, f"cand_{index:032x}").label
            for index in range(4)
        )
        == labels_before
    )

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
    assert (
        tuple(
            controller.store.candidate_by_id(session_id, f"cand_{index:032x}").label
            for index in range(4)
        )
        == labels_before
    )
    page.shutdown()
    controller.shutdown()


def test_sessions_delete_is_confirmed_background_safe_and_returns_to_sessions(
    qapp, qtbot, tmp_path: Path
) -> None:
    """Case: IT-REVW-014."""
    controller, session_id = _session(tmp_path / "suite", count=4, source_sha256="2" * 64)
    opened = controller.store.get_session(session_id)
    closed = controller.close_session(
        session_id,
        expected_revision=opened.revision,
        closed_at="2026-11-06T11:00:00.000Z",
    )
    page = ReviewWorkspacePage(controller)
    qtbot.addWidget(page)
    page.resize(700, 720)
    page.show()
    page.show_sessions()
    assert page.currentWidget() is page.sessions_page
    assert page.navigation.active_route == "sessions"
    assert page.sessions_page.sessions.rowCount() == 1

    delete_button = _button(page.sessions_page, "Delete session")

    def cancel_delete() -> None:
        dialog = _visible_message_box()
        assert dialog is not None
        assert dialog.defaultButton().text() == "Cancel"
        _button(dialog, "Cancel").click()

    QTimer.singleShot(0, cancel_delete)
    delete_button.click()
    assert controller.store.get_session(session_id) == closed

    QTimer.singleShot(0, lambda: _click_visible_message_button("Delete"))
    delete_button.click()
    qtbot.waitUntil(
        lambda: not controller.list_sessions(),
        timeout=10_000,
    )
    assert page.currentWidget() is page.sessions_page
    assert page.navigation.active_route == "sessions"
    assert page.sessions_page.sessions.rowCount() == 0
    page.shutdown()
    controller.shutdown()
