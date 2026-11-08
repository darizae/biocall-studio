from __future__ import annotations

import errno
import hashlib
import json
import time
import tracemalloc
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.domain.exports import ReviewExportMode
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
from biocall_studio.review.gui.workspace import ReviewWorkspacePage
from biocall_studio.review.persistence.export_history import ReviewExportHistoryStore
from biocall_studio.review.persistence.sessions import ReviewSessionStore
from biocall_studio.review.workflows.exports import (
    ReviewExportCancelledError,
    ReviewExportConflictError,
    ReviewExportError,
    plan_review_export,
    publish_review_export,
    reconcile_private_staging,
    verify_review_export_directory,
)

pytestmark = pytest.mark.integration


def _button(widget, text: str) -> QPushButton:
    return next(button for button in widget.findChildren(QPushButton) if button.text() == text)


def _write_wav(path: Path, frames: int, *, rate: int = 8_000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        payload = b"".join(
            int((index % 101) * 200 - 10_000).to_bytes(2, "little", signed=True)
            for index in range(frames)
        )
        stream.writeframes(payload)
    return path


def _pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as stream:
        return stream.readframes(stream.getnframes())


def _settings() -> SpectrogramSettingsSnapshot:
    return SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
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


def _store(
    root: Path,
    source_root: Path,
    *,
    count: int,
    interval_frames: int,
) -> tuple[ReviewSessionStore, str, Path, tuple[EligibleCandidate, ...]]:
    source_path = _write_wav(
        source_root / "recordings" / "field.wav",
        max(64, count * interval_frames + 8),
    )
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    recording_ref = "rec_" + "1" * 32
    candidates = tuple(
        EligibleCandidate(
            ordinal=index,
            recording_ordinal=0,
            candidate_id=f"cand_{index + 1:032x}",
            recording_ref=recording_ref,
            recording_key="recordings/field.wav",
            source_sha256=source_digest,
            sample_rate_hz=8_000,
            frame_count=max(64, count * interval_frames + 8),
            channels=1,
            start_frame=index * interval_frames,
            end_frame=(index + 1) * interval_frames,
            start_time_ns=(index * interval_frames * 1_000_000_000 + 4_000) // 8_000,
            end_time_ns=((index + 1) * interval_frames * 1_000_000_000 + 4_000) // 8_000,
            cnn_target_score=0.8,
            rf_target_score=None,
            contributing_windows=1,
        )
        for index in range(count)
    )
    recording = ReviewRecording(
        ordinal=0,
        recording_ref=recording_ref,
        recording_key="recordings/field.wav",
        source_sha256=source_digest,
        sample_rate_hz=8_000,
        frame_count=max(64, count * interval_frames + 8),
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
    projection = ReviewIntakeProjection(manifest, (recording,), candidates)
    source = ReviewSessionSource.from_projection(
        projection,
        score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
        eligibility_threshold=0.5,
    )
    store = ReviewSessionStore(root)
    default_settings = _settings()
    store.ensure_default_preset(default_settings, saved_at="2026-11-05T08:00:00.000Z")
    settings = store.create_preset(
        name="Field preset",
        algorithm_version=default_settings.algorithm_version,
        render_version=default_settings.render_version,
        effective_settings=default_settings.effective_settings,
        saved_at="2026-11-05T08:01:00.000Z",
    )
    session_id = "rsn_" + "a" * 32
    store.create_session(
        name="Field review",
        source=source,
        candidates=candidates,
        settings=settings,
        owner_id="review_owner_" + "b" * 32,
        created_at="2026-11-05T09:00:00.000Z",
        session_id=session_id,
    )
    return store, session_id, source_path, candidates


def _finalize_mixed(
    store: ReviewSessionStore,
    session_id: str,
    candidates: tuple[EligibleCandidate, ...],
) -> None:
    session = store.get_session(session_id)
    session = store.set_label(
        session_id,
        candidates[0].candidate_id,
        ReviewLabel.CALL,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-05T09:10:00.000Z",
    ).session
    session = store.set_label(
        session_id,
        candidates[2].candidate_id,
        ReviewLabel.NOT_CALL,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-05T09:11:00.000Z",
    ).session
    session = store.accept_all(
        session_id,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-05T09:12:00.000Z",
    ).session
    session = store.set_label(
        session_id,
        candidates[-1].candidate_id,
        ReviewLabel.UNREVIEWED,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-05T09:13:00.000Z",
    ).session
    store.finalize_session(
        session_id,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        finalized_at="2026-11-05T10:00:00.000Z",
    )


def test_all_formats_pcm_raven_truth_and_failure_recovery(tmp_path: Path, monkeypatch) -> None:
    """Case: IT-REVW-010."""
    source_root = tmp_path / "source"
    store, session_id, source_path, candidates = _store(
        tmp_path / "review" / "v1",
        source_root,
        count=4,
        interval_frames=8,
    )
    _finalize_mixed(store, session_id, candidates)
    before_source = source_path.read_bytes()
    before_finalization = json.dumps(
        store.finalization_document(session_id), sort_keys=True
    ).encode()
    destination = tmp_path / "exports"
    destination.mkdir()

    receipts = []
    for index, mode in enumerate(ReviewExportMode, 1):
        plan = plan_review_export(
            store,
            session_id,
            source_root=source_root,
            destination_parent=destination,
            mode=mode,
            export_id="rexp_" + f"{index:x}" * 32,
            created_at="2026-11-05T11:00:00.000Z",
        )
        receipt = publish_review_export(
            plan,
            store,
            source_root=source_root,
            completed_at="2026-11-05T11:01:00.000Z",
        )
        assert verify_review_export_directory(Path(receipt.final_destination)) == receipt
        receipts.append(receipt)

        rows = [
            json.loads(line)
            for line in (Path(receipt.final_destination) / "review-export-rows.jsonl")
            .read_text()
            .splitlines()
        ]
        assert [row["export_status"] for row in rows] == [
            "human_individual",
            "human_bulk",
            "human_rejected",
            "model_only",
        ]
        assert [row["included"] for row in rows] == [True, True, False, True]

        source_pcm = _pcm(source_path)
        if mode.includes_individual:
            for row in rows:
                if not row["included"]:
                    assert row["output_relative_path"] is None
                    continue
                output = Path(receipt.final_destination) / row["output_relative_path"]
                start = row["source_start_frame"] * 2
                end = row["source_end_frame"] * 2
                assert _pcm(output) == source_pcm[start:end]
        if mode.includes_combined:
            expected = b"".join(
                source_pcm[row["source_start_frame"] * 2 : row["source_end_frame"] * 2]
                for row in rows
                if row["included"]
            )
            assert _pcm(Path(receipt.final_destination) / "corpus.wav") == expected
            raven = (Path(receipt.final_destination) / "corpus.Table.1.selections.txt").read_text()
            assert "human_individual\tcall\tindividual" in raven
            assert "human_bulk\tcall\tbulk" in raven
            assert "model_only\tunreviewed\t" in raven
            assert candidates[2].candidate_id not in raven

    assert source_path.read_bytes() == before_source
    assert (
        json.dumps(store.finalization_document(session_id), sort_keys=True).encode()
        == before_finalization
    )

    historical_settings = store.load_settings(session_id)
    updated_settings = store.update_preset(
        historical_settings.preset_id,
        expected_revision=historical_settings.preset_revision,
        name="Renamed field preset",
        algorithm_version=historical_settings.algorithm_version,
        render_version=historical_settings.render_version,
        effective_settings={
            **historical_settings.effective_settings,
            "frequency_max_hz": 3_800,
        },
        saved_at="2026-11-05T11:10:00.000Z",
    )
    store.delete_preset(
        updated_settings.preset_id,
        expected_revision=updated_settings.preset_revision,
        deleted_at="2026-11-05T11:11:00.000Z",
    )
    cache_file = store.root / "cache" / "spectrograms" / "discarded.png"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"not-scientific-export-input")
    cache_file.unlink()
    child = store.continue_in_new_session(
        session_id,
        name="Changed successor",
        owner_id="review_owner_" + "e" * 32,
        created_at="2026-11-05T11:11:30.000Z",
        session_id="rsn_" + "e" * 32,
    )
    store.set_label(
        child.session_id,
        candidates[0].candidate_id,
        ReviewLabel.NOT_CALL,
        owner_id=child.owner_id,
        expected_revision=child.revision,
        modified_at="2026-11-05T11:11:40.000Z",
    )
    repeat_plan = plan_review_export(
        store,
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.COMBINED,
        export_id="rexp_" + "c" * 32,
        created_at="2026-11-05T11:12:00.000Z",
    )
    repeat = publish_review_export(
        repeat_plan,
        store,
        source_root=source_root,
        completed_at="2026-11-05T11:13:00.000Z",
    )
    for name in ("corpus.wav", "corpus.Table.1.selections.txt"):
        assert (Path(repeat.final_destination) / name).read_bytes() == (
            Path(receipts[1].final_destination) / name
        ).read_bytes()
    assert store.load_settings(session_id) == historical_settings
    assert (
        json.dumps(store.finalization_document(session_id), sort_keys=True).encode()
        == before_finalization
    )

    collision_plan = plan_review_export(
        store,
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.COMBINED,
        export_id="rexp_" + "f" * 32,
        created_at="2026-11-05T12:00:00.000Z",
    )
    collision_plan.final_destination.mkdir()
    with pytest.raises(ReviewExportConflictError):
        publish_review_export(collision_plan, store, source_root=source_root)

    cancel_plan = plan_review_export(
        store,
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.BOTH,
        export_id="rexp_" + "e" * 32,
        created_at="2026-11-05T12:00:00.000Z",
    )
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > 6

    with pytest.raises(ReviewExportCancelledError):
        publish_review_export(
            cancel_plan,
            store,
            source_root=source_root,
            cancel_requested=cancel,
        )
    assert not cancel_plan.final_destination.exists()
    assert source_path.read_bytes() == before_source

    disk_full_plan = plan_review_export(
        store,
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.COMBINED,
        export_id="rexp_" + "a" * 32,
        created_at="2026-11-05T12:01:00.000Z",
    )
    original_write_bytes = Path.write_bytes

    def fail_manifest(path: Path, payload: bytes) -> int:
        if path.name == "review-export-manifest.json":
            raise OSError(errno.ENOSPC, "injected disk full")
        return original_write_bytes(path, payload)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "write_bytes", fail_manifest)
        with pytest.raises(ReviewExportError, match="No partial corpus"):
            publish_review_export(disk_full_plan, store, source_root=source_root)
    assert not disk_full_plan.final_destination.exists()
    assert not tuple(destination.glob(".*.staging-*"))

    abandoned = destination / (".biocall-review-export-deadbeef.staging-" + "0" * 32)
    abandoned.mkdir()
    (abandoned / "incomplete").write_bytes(b"partial")
    assert reconcile_private_staging(destination) == (abandoned.name,)
    assert not abandoned.exists()

    corrupt = Path(receipts[-1].final_destination) / "review-export-rows.jsonl"
    original = corrupt.read_bytes()
    altered = bytearray(original)
    altered[-20] ^= 1
    corrupt.write_bytes(altered)
    with pytest.raises(ReviewExportError):
        verify_review_export_directory(Path(receipts[-1].final_destination))
    corrupt.write_bytes(original)
    assert verify_review_export_directory(Path(receipts[-1].final_destination)) == receipts[-1]

    class _FailingHistory:
        def save(self, _record) -> None:
            raise OSError("injected history write failure")

    controller = ReviewSessionController(
        tmp_path / "suite",
        store=store,
        export_history=_FailingHistory(),
    )
    history_plan = controller.plan_export(
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.COMBINED,
        export_id="rexp_" + "d" * 32,
        created_at="2026-11-05T12:10:00.000Z",
    )
    estimate = controller.estimate_export_storage(history_plan)
    outcome = controller.publish_export(
        history_plan,
        source_root=source_root,
        storage_input_digest=estimate.input_digest,
        completed_at="2026-11-05T12:11:00.000Z",
    )
    assert not outcome.history_saved
    assert "history" in outcome.message
    assert (
        verify_review_export_directory(Path(outcome.receipt.final_destination)) == outcome.receipt
    )
    controller.export_history = ReviewExportHistoryStore(store.root)
    recovered = controller.recover_export_history(Path(outcome.receipt.final_destination))
    assert recovered.receipt_digest == outcome.receipt.receipt_digest
    assert controller.list_export_history() == (recovered,)
    controller.shutdown()


def test_fifty_thousand_row_streamed_combined_publication(tmp_path: Path, record_property) -> None:
    """Case: IT-REVW-009."""
    source_root = tmp_path / "source"
    store, session_id, source_path, _candidates = _store(
        tmp_path / "review" / "v1",
        source_root,
        count=50_000,
        interval_frames=1,
    )
    session = store.get_session(session_id)
    store.finalize_session(
        session_id,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        finalized_at="2026-11-05T10:00:00.000Z",
    )
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    finalization_digest = store.get_session(session_id).final_snapshot_digest
    destination = tmp_path / "exports"
    destination.mkdir()

    tracemalloc.start()
    started = time.monotonic()
    plan = plan_review_export(
        store,
        session_id,
        source_root=source_root,
        destination_parent=destination,
        mode=ReviewExportMode.COMBINED,
        export_id="rexp_" + "9" * 32,
        created_at="2026-11-05T11:00:00.000Z",
    )
    receipt = publish_review_export(
        plan,
        store,
        source_root=source_root,
        completed_at="2026-11-05T11:01:00.000Z",
    )
    reopened = verify_review_export_directory(Path(receipt.final_destination))
    elapsed = time.monotonic() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    record_property("rv06_50000_elapsed_seconds", round(elapsed, 3))
    record_property("rv06_50000_peak_tracemalloc_bytes", peak)
    record_property("rv06_50000_output_bytes", plan.expected_final_bytes)
    assert reopened == receipt
    assert receipt.row_count == 50_000
    assert plan.included_count == 50_000
    assert plan.model_only_count == 50_000
    assert plan.concat_frame_count == 50_000
    assert peak < 512 * 1024 * 1024
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_digest
    assert store.get_session(session_id).final_snapshot_digest == finalization_digest

    rows = Path(receipt.final_destination) / "review-export-rows.jsonl"
    with rows.open("r+b") as stream:
        stream.seek(-64, 2)
        original = stream.read(1)
        stream.seek(-1, 1)
        stream.write(b"x" if original != b"x" else b"y")
    with pytest.raises(ReviewExportError):
        verify_review_export_directory(Path(receipt.final_destination))


@pytest.mark.qt
def test_native_finalized_export_preflight_publish_and_history(qapp, qtbot, tmp_path: Path) -> None:
    """Case: IT-REVW-010."""
    source_root = tmp_path / "source"
    store, session_id, _source_path, candidates = _store(
        tmp_path / "review" / "v1",
        source_root,
        count=4,
        interval_frames=8,
    )
    _finalize_mixed(store, session_id, candidates)
    controller = ReviewSessionController(tmp_path / "suite", store=store)
    page = ReviewWorkspacePage(
        controller,
        source_root_resolver=lambda _session: source_root,
    )
    qtbot.addWidget(page)
    page.resize(920, 680)
    page.show()
    page.open_session(session_id)

    export_button = _button(page.session_page, "Export")
    assert export_button.isEnabled()
    qtbot.mouseClick(export_button, Qt.MouseButton.LeftButton)
    assert page.currentWidget() is page.export_page
    assert page.export_page.session_label.text().startswith("Field review")

    destination = tmp_path / "exports"
    destination.mkdir()
    page.export_page.destination.setText(str(destination))
    qtbot.mouseClick(page.export_page.prepare_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: page.export_page.plan is not None, timeout=10_000)
    assert page.export_page.estimate is not None
    assert page.export_page.publish_button.isEnabled()

    qtbot.mouseClick(page.export_page.publish_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: page.export_page.receipt is not None, timeout=10_000)
    assert page.export_page.show_button.isVisible()
    assert page.export_page.status_label.text() == "Export complete."

    page.show_exports()
    assert page.currentWidget() is page.exports_page
    assert page.exports_page.exports.rowCount() == 1
    assert page.exports_page.exports.item(0, 0).text() == "Field review"
    assert "rexp_" not in page.exports_page.exports.item(0, 0).text()
    page.shutdown()
