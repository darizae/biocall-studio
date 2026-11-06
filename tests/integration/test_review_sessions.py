from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

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
    DecisionOrigin,
    ReviewLabel,
    ReviewSessionSource,
    ReviewSessionState,
    SpectrogramSettingsSnapshot,
)
from biocall_studio.review.persistence.sessions import (
    ReviewSessionConflict,
    ReviewSessionStore,
)

pytestmark = pytest.mark.integration


def _candidate(ordinal: int, *, total_frames: int = 500_100) -> EligibleCandidate:
    start = ordinal * 10
    return EligibleCandidate(
        ordinal=ordinal,
        recording_ordinal=0,
        candidate_id=f"cand_{ordinal:032x}",
        recording_ref="rec_" + "1" * 32,
        recording_key="recordings/session-source.wav",
        source_sha256="2" * 64,
        sample_rate_hz=8_000,
        frame_count=total_frames,
        channels=1,
        start_frame=start,
        end_frame=start + 5,
        start_time_ns=(start * 1_000_000_000 + 4_000) // 8_000,
        end_time_ns=((start + 5) * 1_000_000_000 + 4_000) // 8_000,
        cnn_target_score=0.75,
        rf_target_score=None,
        contributing_windows=1,
    )


def _projection(count: int) -> ReviewIntakeProjection:
    candidates = tuple(_candidate(index) for index in range(count))
    recording = ReviewRecording(
        ordinal=0,
        recording_ref="rec_" + "1" * 32,
        recording_key="recordings/session-source.wav",
        source_sha256="2" * 64,
        sample_rate_hz=8_000,
        frame_count=500_100,
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
    return ReviewIntakeProjection(manifest, (recording,), candidates)


def _source(projection: ReviewIntakeProjection) -> ReviewSessionSource:
    return ReviewSessionSource.from_projection(
        projection,
        score_semantics="binary_softmax_target_output_index_1; not_a_calibrated_probability",
        eligibility_threshold=0.5,
    )


def _settings(
    *, preset_id: str = DEFAULT_PRESET_ID, name: str = "Default", revision: int = 1
) -> SpectrogramSettingsSnapshot:
    return SpectrogramSettingsSnapshot.create(
        preset_id=preset_id,
        preset_name=name,
        preset_revision=revision,
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
        effective_settings={"frequency_limit_hz": 4_200, "palette": "viridis"},
    )


def test_sqlite_annotations_restart_scale_close_resume_and_process_loss(tmp_path: Path) -> None:
    """Case: IT-REVW-002."""
    source_result = tmp_path / "result.json"
    source_wav = tmp_path / "session-source.wav"
    source_result.write_bytes(b'{"immutable":"result"}\n')
    source_wav.write_bytes(b"RIFF-immutable-source")
    result_hash = hashlib.sha256(source_result.read_bytes()).hexdigest()
    wav_hash = hashlib.sha256(source_wav.read_bytes()).hexdigest()

    root = tmp_path / "review" / "v1"
    store = ReviewSessionStore(root)
    projection = _projection(50_000)
    settings = _settings()
    store.ensure_default_preset(settings, saved_at="2026-11-04T09:00:00.000Z")
    session = store.create_session(
        name="Large migration review",
        source=_source(projection),
        candidates=projection.candidates,
        settings=settings,
        owner_id="review_owner_" + "a" * 32,
        created_at="2026-11-04T10:00:00.000Z",
        session_id="rsn_" + "a" * 32,
    )

    session = store.set_label(
        session.session_id,
        projection.candidates[0].candidate_id,
        ReviewLabel.NOT_CALL,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-04T10:01:00.000Z",
    ).session
    session = store.set_label(
        session.session_id,
        projection.candidates[1].candidate_id,
        ReviewLabel.CALL,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-04T10:02:00.000Z",
    ).session
    accepted = store.accept_all(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-04T10:03:00.000Z",
    )
    assert accepted.changed_count == 49_998
    assert accepted.session.call_count == 49_999
    assert accepted.session.not_call_count == 1

    undone = store.undo(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=accepted.session.revision,
        modified_at="2026-11-04T10:04:00.000Z",
    )
    assert undone.changed_count == 49_998
    assert undone.session.unreviewed_count == 49_998
    redone = store.redo(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=undone.session.revision,
        modified_at="2026-11-04T10:05:00.000Z",
    )
    assert redone.session.call_count == 49_999

    individual = store.set_label(
        session.session_id,
        projection.candidates[2].candidate_id,
        ReviewLabel.NOT_CALL,
        owner_id=session.owner_id,
        expected_revision=redone.session.revision,
        modified_at="2026-11-04T10:05:10.000Z",
    )
    individual_undone = store.undo(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=individual.session.revision,
        modified_at="2026-11-04T10:05:20.000Z",
    )
    individual_redone = store.redo(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=individual_undone.session.revision,
        modified_at="2026-11-04T10:05:30.000Z",
    )
    individual_undone_again = store.undo(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=individual_redone.session.revision,
        modified_at="2026-11-04T10:05:40.000Z",
    )
    assert individual_undone_again.session.call_count == 49_999
    assert individual_undone_again.session.not_call_count == 1

    position = store.save_position(
        session.session_id,
        candidate_id=projection.candidates[40_000].candidate_id,
        view="list",
        filter_name="unreviewed",
        scroll_offset=40_000,
        selected_candidate_ids=(projection.candidates[40_000].candidate_id,),
        owner_id=session.owner_id,
        expected_view_revision=0,
    )
    assert position.current_candidate_id == projection.candidates[40_000].candidate_id

    restarted = ReviewSessionStore(root)
    reopened = restarted.get_session(session.session_id)
    assert reopened.call_count == 49_999
    assert restarted.load_position(session.session_id) == position
    page = restarted.decision_page(session.session_id, offset=0, limit=3)
    assert page[0].label is ReviewLabel.NOT_CALL
    assert page[1].label is ReviewLabel.CALL
    assert page[2].origin is DecisionOrigin.BULK

    with pytest.raises(ReviewSessionConflict, match="owner"):
        restarted.set_label(
            session.session_id,
            projection.candidates[2].candidate_id,
            ReviewLabel.NOT_CALL,
            owner_id="review_owner_" + "b" * 32,
            expected_revision=reopened.revision,
            modified_at="2026-11-04T10:06:00.000Z",
        )
    assert restarted.get_session(session.session_id) == reopened

    closed = restarted.close_session(
        session.session_id,
        owner_id=reopened.owner_id,
        expected_revision=reopened.revision,
        closed_at="2026-11-04T10:07:00.000Z",
    )
    assert closed.state is ReviewSessionState.CLOSED
    resumed = restarted.resume_session(
        session.session_id,
        owner_id="review_owner_" + "b" * 32,
        expected_revision=closed.revision,
        resumed_at="2026-11-04T10:08:00.000Z",
    )
    assert resumed.state is ReviewSessionState.OPEN
    assert resumed.call_count == 49_999

    code = """
import os, sys
from pathlib import Path
from biocall_studio.review.domain.sessions import ReviewLabel
from biocall_studio.review.persistence.sessions import ReviewSessionStore
root, session_id, candidate_id, owner_id, revision = sys.argv[1:]
store = ReviewSessionStore(Path(root))
store.set_label(session_id, candidate_id, ReviewLabel.NOT_CALL, owner_id=owner_id,
                expected_revision=int(revision), modified_at='2026-11-04T10:09:00.000Z')
os._exit(91)
"""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(root),
            session.session_id,
            projection.candidates[2].candidate_id,
            resumed.owner_id,
            str(resumed.revision),
        ],
        check=False,
    )
    assert child.returncode == 91
    survived = restarted.get_session(session.session_id)
    assert survived.not_call_count == 2
    assert hashlib.sha256(source_result.read_bytes()).hexdigest() == result_hash
    assert hashlib.sha256(source_wav.read_bytes()).hexdigest() == wav_hash

    first_controller = ReviewSessionController(tmp_path, store=restarted)
    second_controller = ReviewSessionController(tmp_path, store=restarted)
    try:
        claimed = first_controller.recover_open_session(recovered_at="2026-11-04T10:10:00.000Z")
        assert claimed is not None and claimed.owner_id == first_controller.owner_id
        with pytest.raises(ReviewSessionConflict, match="another running Studio"):
            second_controller.recover_open_session(recovered_at="2026-11-04T10:11:00.000Z")
    finally:
        second_controller.shutdown()
        first_controller.shutdown()


def test_finalization_child_presets_lock_crash_and_digest_verification(tmp_path: Path) -> None:
    """Case: IT-REVW-003."""
    root = tmp_path / "review" / "v1"
    store = ReviewSessionStore(root, busy_timeout_seconds=0.15)
    projection = _projection(3)
    default = _settings()
    store.ensure_default_preset(default, saved_at="2026-11-04T09:00:00.000Z")
    user = store.create_preset(
        name="Woodland",
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
        effective_settings={"frequency_limit_hz": 5_000, "palette": "magma"},
        saved_at="2026-11-04T09:10:00.000Z",
        preset_id="rsp_" + "2" * 32,
    )
    session = store.create_session(
        name="Partial review",
        source=_source(projection),
        candidates=projection.candidates,
        settings=user,
        owner_id="review_owner_" + "a" * 32,
        created_at="2026-11-04T10:00:00.000Z",
        session_id="rsn_" + "a" * 32,
    )
    first = store.set_label(
        session.session_id,
        projection.candidates[0].candidate_id,
        ReviewLabel.CALL,
        owner_id=session.owner_id,
        expected_revision=session.revision,
        modified_at="2026-11-04T10:01:00.000Z",
    ).session
    second = store.set_label(
        session.session_id,
        projection.candidates[1].candidate_id,
        ReviewLabel.NOT_CALL,
        owner_id=session.owner_id,
        expected_revision=first.revision,
        modified_at="2026-11-04T10:02:00.000Z",
    ).session
    source_digest = second.source_digest
    settings_digest = second.settings_digest
    labels_digest = store.annotation_digest(session.session_id)

    renamed = store.update_preset(
        user.preset_id,
        expected_revision=1,
        name="Woodland calls",
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
        effective_settings={"frequency_limit_hz": 6_000, "palette": "magma"},
        saved_at="2026-11-04T10:03:00.000Z",
    )
    impact = store.preset_impact(user.preset_id)
    assert (impact.open_count, impact.closed_count, impact.finalized_count) == (1, 0, 0)
    store.delete_preset(
        user.preset_id,
        expected_revision=renamed.preset_revision,
        deleted_at="2026-11-04T10:04:00.000Z",
    )
    unchanged = store.get_session(session.session_id)
    assert unchanged.settings_digest == settings_digest
    assert unchanged.source_digest == source_digest
    assert store.annotation_digest(session.session_id) == labels_digest

    with pytest.raises(ReviewSessionConflict, match="revision"):
        store.change_settings(
            session.session_id,
            default,
            owner_id=session.owner_id,
            expected_revision=second.revision,
            expected_settings_epoch=second.settings_epoch - 1,
            changed_at="2026-11-04T10:05:00.000Z",
        )
    assert store.get_session(session.session_id) == unchanged

    switched = store.change_settings(
        session.session_id,
        default,
        owner_id=session.owner_id,
        expected_revision=second.revision,
        expected_settings_epoch=second.settings_epoch,
        changed_at="2026-11-04T10:06:00.000Z",
    )
    assert switched.settings_digest == default.settings_digest
    assert switched.source_digest == source_digest
    assert store.annotation_digest(session.session_id) == labels_digest
    renamed_session = store.rename_session(
        session.session_id,
        "Partial woodland review",
        owner_id=session.owner_id,
        expected_revision=switched.revision,
        renamed_at="2026-11-04T10:07:00.000Z",
    )

    finalized = store.finalize_session(
        session.session_id,
        owner_id=session.owner_id,
        expected_revision=renamed_session.revision,
        finalized_at="2026-11-04T11:00:00.000Z",
    )
    assert finalized.state is ReviewSessionState.FINALIZED
    assert (finalized.call_count, finalized.not_call_count, finalized.unreviewed_count) == (1, 1, 1)
    assert store.verify_finalization(session.session_id)
    frozen = store.finalization_document(session.session_id)
    frozen_digest = finalized.final_snapshot_digest

    with pytest.raises(ReviewSessionConflict, match="Finalized"):
        store.set_label(
            session.session_id,
            projection.candidates[2].candidate_id,
            ReviewLabel.CALL,
            owner_id=session.owner_id,
            expected_revision=finalized.revision,
            modified_at="2026-11-04T11:01:00.000Z",
        )
    child = store.continue_in_new_session(
        session.session_id,
        name="Partial review continued",
        owner_id="review_owner_" + "a" * 32,
        created_at="2026-11-04T11:02:00.000Z",
        session_id="rsn_" + "b" * 32,
    )
    assert child.parent_session_id == session.session_id
    assert child.parent_snapshot_digest == frozen_digest
    assert child.settings_digest == default.settings_digest
    assert (child.call_count, child.not_call_count, child.unreviewed_count) == (1, 1, 1)
    child = store.set_label(
        child.session_id,
        projection.candidates[2].candidate_id,
        ReviewLabel.CALL,
        owner_id=child.owner_id,
        expected_revision=child.revision,
        modified_at="2026-11-04T11:03:00.000Z",
    ).session
    assert store.finalization_document(session.session_id) == frozen
    assert store.verify_finalization(session.session_id)

    child = store.close_session(
        child.session_id,
        owner_id=child.owner_id,
        expected_revision=child.revision,
        closed_at="2026-11-04T11:04:00.000Z",
    )
    interrupted = store.create_session(
        name="Interrupted finalization",
        source=_source(projection),
        candidates=projection.candidates,
        settings=default,
        owner_id="review_owner_" + "c" * 32,
        created_at="2026-11-04T12:00:00.000Z",
        session_id="rsn_" + "c" * 32,
    )
    crash_code = """
import os, sqlite3, sys
db, session_id = sys.argv[1:]
connection = sqlite3.connect(db)
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE sessions SET state = 'finalized' WHERE session_id = ?", (session_id,))
os._exit(92)
"""
    crashed = subprocess.run(
        [sys.executable, "-c", crash_code, str(store.database_path), interrupted.session_id],
        check=False,
    )
    assert crashed.returncode == 92
    assert store.get_session(interrupted.session_id).state is ReviewSessionState.OPEN
    assert store.finalization_document(interrupted.session_id) is None

    signal = tmp_path / "locked"
    release = tmp_path / "release"
    lock_code = """
import sqlite3, sys, time
from pathlib import Path
db, signal, release = map(Path, sys.argv[1:])
connection = sqlite3.connect(db)
connection.execute('BEGIN IMMEDIATE')
signal.write_text('locked')
while not release.exists():
    time.sleep(0.01)
connection.rollback()
"""
    locker = subprocess.Popen(
        [sys.executable, "-c", lock_code, str(store.database_path), str(signal), str(release)]
    )
    try:
        deadline = time.monotonic() + 5
        while not signal.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert signal.exists()
        before_lock = store.get_session(interrupted.session_id)
        with pytest.raises(ReviewSessionConflict, match="busy|locked"):
            store.set_label(
                interrupted.session_id,
                projection.candidates[0].candidate_id,
                ReviewLabel.CALL,
                owner_id=interrupted.owner_id,
                expected_revision=interrupted.revision,
                modified_at="2026-11-04T12:01:00.000Z",
            )
        assert store.get_session(interrupted.session_id) == before_lock
    finally:
        release.write_text("release")
        assert locker.wait(timeout=5) == 0

    corrupt_root = tmp_path / "corrupt-review" / "v1"
    corrupt_root.mkdir(parents=True)
    corrupt_db = corrupt_root / "sessions.sqlite3"
    corrupt_db.write_bytes(store.database_path.read_bytes())
    connection = sqlite3.connect(corrupt_db)
    connection.execute(
        "UPDATE decisions SET label = 'call' WHERE session_id = ? AND candidate_id = ?",
        (session.session_id, projection.candidates[1].candidate_id),
    )
    connection.commit()
    connection.close()
    corrupt = ReviewSessionStore(corrupt_root)
    assert not corrupt.verify_finalization(session.session_id)


def test_transactional_session_delete_blocks_descendants_and_preserves_external_state(
    tmp_path: Path,
) -> None:
    """Case: UT-REVW-013."""
    source_result = tmp_path / "detect-result.json"
    source_wav = tmp_path / "recordings" / "source.wav"
    source_wav.parent.mkdir()
    source_result.write_bytes(b'{"result":"immutable"}\n')
    source_wav.write_bytes(b"RIFF-immutable-source")
    source_bytes = (source_result.read_bytes(), source_wav.read_bytes())

    root = tmp_path / "review" / "v1"
    store = ReviewSessionStore(root)
    projection = _projection(3)
    settings = _settings()
    owner = "review_owner_" + "d" * 32
    store.ensure_default_preset(settings, saved_at="2026-11-06T09:00:00.000Z")

    closed = store.create_session(
        name="Closed review",
        source=_source(projection),
        candidates=projection.candidates,
        settings=settings,
        owner_id=owner,
        created_at="2026-11-06T09:01:00.000Z",
        session_id="rsn_" + "d" * 32,
    )
    closed = store.set_label(
        closed.session_id,
        projection.candidates[0].candidate_id,
        ReviewLabel.CALL,
        owner_id=owner,
        expected_revision=closed.revision,
        modified_at="2026-11-06T09:02:00.000Z",
    ).session
    closed = store.close_session(
        closed.session_id,
        owner_id=owner,
        expected_revision=closed.revision,
        closed_at="2026-11-06T09:03:00.000Z",
    )

    parent = store.create_session(
        name="Final review",
        source=_source(projection),
        candidates=projection.candidates,
        settings=settings,
        owner_id=owner,
        created_at="2026-11-06T09:04:00.000Z",
        session_id="rsn_" + "e" * 32,
    )
    parent = store.finalize_session(
        parent.session_id,
        owner_id=owner,
        expected_revision=parent.revision,
        finalized_at="2026-11-06T09:05:00.000Z",
    )
    child = store.continue_in_new_session(
        parent.session_id,
        name="Follow-up",
        owner_id=owner,
        created_at="2026-11-06T09:06:00.000Z",
        session_id="rsn_" + "f" * 32,
    )
    child = store.close_session(
        child.session_id,
        owner_id=owner,
        expected_revision=child.revision,
        closed_at="2026-11-06T09:07:00.000Z",
    )

    cache_marker = root / "cache" / "spectrograms" / "objects" / "shared.png"
    export_marker = root / "export-history" / "published-receipt.json"
    cache_marker.parent.mkdir(parents=True)
    export_marker.parent.mkdir(parents=True)
    cache_marker.write_bytes(b"shared-cache-object")
    export_marker.write_bytes(b"independent-export-history")

    with pytest.raises(ReviewSessionConflict, match="successor"):
        store.delete_session(parent.session_id, expected_revision=parent.revision)
    assert store.get_session(parent.session_id) == parent
    assert store.get_session(child.session_id) == child

    store.delete_session(child.session_id, expected_revision=child.revision)
    with pytest.raises(KeyError):
        store.get_session(child.session_id)
    store.delete_session(parent.session_id, expected_revision=parent.revision)
    with pytest.raises(KeyError):
        store.get_session(parent.session_id)

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ReviewSessionConflict, match="cancelled"):
        store.delete_session(
            closed.session_id,
            expected_revision=closed.revision,
            cancel_requested=cancelled,
        )
    assert store.get_session(closed.session_id) == closed
    store.delete_session(closed.session_id, expected_revision=closed.revision)
    with pytest.raises(KeyError):
        store.get_session(closed.session_id)

    opened = store.create_session(
        name="Open review",
        source=_source(projection),
        candidates=projection.candidates,
        settings=settings,
        owner_id=owner,
        created_at="2026-11-06T09:08:00.000Z",
        session_id="rsn_" + "1" * 32,
    )
    store.delete_session(
        opened.session_id,
        expected_revision=opened.revision,
        owner_id=owner,
    )
    with pytest.raises(KeyError):
        store.get_session(opened.session_id)

    assert store.list_presets() == (settings,)
    assert cache_marker.read_bytes() == b"shared-cache-object"
    assert export_marker.read_bytes() == b"independent-export-history"
    assert (source_result.read_bytes(), source_wav.read_bytes()) == source_bytes
