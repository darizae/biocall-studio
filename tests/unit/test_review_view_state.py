from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.application.view_state import (
    ReviewFilter,
    ReviewShortcutAction,
    ReviewSort,
    ReviewView,
    ReviewViewState,
    shortcut_action,
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


def _candidate(
    ordinal: int,
    *,
    recording_ordinal: int,
    recording_name: str,
    start_frame: int,
    score: float,
) -> EligibleCandidate:
    return EligibleCandidate(
        ordinal=ordinal,
        recording_ordinal=recording_ordinal,
        candidate_id=f"cand_{ordinal:032x}",
        recording_ref=f"rec_{recording_ordinal + 1:032x}",
        recording_key=f"recordings/{recording_name}",
        source_sha256=f"{recording_ordinal + 1:x}" * 64,
        sample_rate_hz=8_000,
        frame_count=80_000,
        channels=1,
        start_frame=start_frame,
        end_frame=start_frame + 800,
        start_time_ns=start_frame * 125_000,
        end_time_ns=(start_frame + 800) * 125_000,
        cnn_target_score=score,
        rf_target_score=None,
        contributing_windows=1,
    )


def _projection() -> ReviewIntakeProjection:
    candidates = (
        _candidate(0, recording_ordinal=1, recording_name="zeta.wav", start_frame=8_000, score=0.6),
        _candidate(
            1, recording_ordinal=0, recording_name="alpha.wav", start_frame=16_000, score=0.9
        ),
        _candidate(
            2, recording_ordinal=0, recording_name="alpha.wav", start_frame=24_000, score=0.7
        ),
        _candidate(
            3, recording_ordinal=1, recording_name="zeta.wav", start_frame=32_000, score=0.8
        ),
    )
    recordings = (
        ReviewRecording(
            ordinal=0,
            recording_ref=f"rec_{1:032x}",
            recording_key="recordings/alpha.wav",
            source_sha256="1" * 64,
            sample_rate_hz=8_000,
            frame_count=80_000,
            channels=1,
            failed=False,
            error_code="",
            eligible_candidate_count=2,
        ),
        ReviewRecording(
            ordinal=1,
            recording_ref=f"rec_{2:032x}",
            recording_key="recordings/zeta.wav",
            source_sha256="2" * 64,
            sample_rate_hz=8_000,
            frame_count=80_000,
            channels=1,
            failed=False,
            error_code="",
            eligible_candidate_count=2,
        ),
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
        recording_count=2,
        failed_recording_count=0,
        eligible_candidate_count=4,
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, recordings, candidates),
    )
    return ReviewIntakeProjection(manifest, recordings, candidates)


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


def _state(tmp_path: Path) -> tuple[ReviewViewState, ReviewSessionController]:
    controller = ReviewSessionController(tmp_path)
    projection = _projection()
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
    return ReviewViewState(controller, session.session_id), controller


def test_filter_search_sort_navigation_and_persisted_view_state(tmp_path: Path) -> None:
    """Case: UT-REVW-009."""
    state, controller = _state(tmp_path)
    try:
        assert [row.recording_name for row in state.page(0, 10)] == [
            "alpha.wav",
            "alpha.wav",
            "zeta.wav",
            "zeta.wav",
        ]

        state.set_query(
            view=ReviewView.LIST,
            filter_name=ReviewFilter.ALL,
            sort=ReviewSort.RECORDING,
            search="alpha",
        )
        assert state.row_count == 2
        assert [row.start_time_ns for row in state.page(0, 10)] == [
            2_000_000_000,
            3_000_000_000,
        ]

        state.set_current("cand_" + f"{1:032x}")
        assert state.next().candidate_id == "cand_" + f"{2:032x}"
        state.set_query(sort=ReviewSort.PREDICTION_DESCENDING)
        assert [row.cnn_target_score for row in state.page(0, 10)] == [0.9, 0.7]

        state.set_selection(("cand_" + f"{1:032x}", "cand_" + f"{2:032x}"))
        state.scroll_offset = 37
        state.save_position()
        restored = ReviewViewState(controller, state.session.session_id)
        assert restored.view is ReviewView.LIST
        assert restored.filter is ReviewFilter.ALL
        assert restored.sort is ReviewSort.PREDICTION_DESCENDING
        assert restored.search == "alpha"
        assert restored.selected_candidate_ids == (
            "cand_" + f"{1:032x}",
            "cand_" + f"{2:032x}",
        )
        assert restored.scroll_offset == 37
    finally:
        controller.shutdown()


def test_label_save_precedes_auto_advance_and_failures_do_not_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case: UT-REVW-009."""
    state, controller = _state(tmp_path)
    try:
        state.set_query(view=ReviewView.ONE_BY_ONE, sort=ReviewSort.SOURCE_TIME)
        state.set_current("cand_" + f"{1:032x}")
        mutation = state.set_label(
            ReviewLabel.CALL,
            modified_at="2026-11-05T10:01:00.000Z",
        )
        assert mutation.changed_count == 1
        assert state.current_candidate_id == "cand_" + f"{2:032x}"
        assert (
            controller.store.decision_page(state.session.session_id, offset=1, limit=1)[0].label
            is ReviewLabel.CALL
        )

        current = state.current_candidate_id
        revision = state.session.revision

        def fail(*_args, **_kwargs):
            raise OSError("injected save failure")

        monkeypatch.setattr(controller, "set_label", fail)
        with pytest.raises(OSError, match="injected"):
            state.set_label(
                ReviewLabel.NOT_CALL,
                modified_at="2026-11-05T10:02:00.000Z",
            )
        assert state.current_candidate_id == current
        assert state.session.revision == revision

        monkeypatch.undo()
        state.set_label(
            ReviewLabel.UNREVIEWED,
            modified_at="2026-11-05T10:03:00.000Z",
        )
        assert state.current_candidate_id == current
    finally:
        controller.shutdown()


@pytest.mark.parametrize(
    ("key", "modifiers", "focus_kind", "state", "expected"),
    [
        ("F", frozenset(), "button", "open", ReviewShortcutAction.CALL),
        ("D", frozenset(), "button", "open", ReviewShortcutAction.NOT_CALL),
        ("S", frozenset(), "button", "open", ReviewShortcutAction.CLEAR_LABEL),
        ("J", frozenset(), "button", "finalized", ReviewShortcutAction.PREVIOUS),
        ("LEFT", frozenset(), "button", "open", ReviewShortcutAction.PREVIOUS),
        ("K", frozenset(), "button", "open", ReviewShortcutAction.PLAY_PAUSE),
        ("SPACE", frozenset(), "button", "open", ReviewShortcutAction.PLAY_PAUSE),
        ("L", frozenset(), "button", "open", ReviewShortcutAction.NEXT),
        ("Z", frozenset({"CTRL"}), "button", "open", ReviewShortcutAction.UNDO),
        ("F", frozenset(), "line_edit", "open", None),
        ("SPACE", frozenset(), "slider", "open", None),
        ("L", frozenset({"ALT"}), "button", "open", None),
        ("F", frozenset(), "button", "finalized", None),
    ],
)
def test_fixed_shortcut_scope(
    key: str,
    modifiers: frozenset[str],
    focus_kind: str,
    state: str,
    expected: ReviewShortcutAction | None,
) -> None:
    """Case: UT-REVW-009."""
    assert (
        shortcut_action(
            key,
            modifiers=modifiers,
            focus_kind=focus_kind,
            view=ReviewView.ONE_BY_ONE,
            session_state=state,
            auto_repeat=False,
            modal_open=False,
        )
        is expected
    )
    assert (
        shortcut_action(
            key,
            modifiers=modifiers,
            focus_kind=focus_kind,
            view=ReviewView.GALLERY,
            session_state=state,
            auto_repeat=False,
            modal_open=False,
        )
        is None
    )
    assert (
        shortcut_action(
            key,
            modifiers=modifiers,
            focus_kind=focus_kind,
            view=ReviewView.ONE_BY_ONE,
            session_state=state,
            auto_repeat=True,
            modal_open=False,
        )
        is None
    )
