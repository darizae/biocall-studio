from __future__ import annotations

from dataclasses import replace

import pytest

from biocall_studio.review.domain.sessions import (
    AnnotationBook,
    DecisionOrigin,
    FinalizedCandidateDecision,
    ReviewFinalizationSnapshot,
    ReviewLabel,
    ReviewRevisionConflict,
    ReviewSessionState,
    SpectrogramSettingsSnapshot,
    require_session_transition,
)


def _settings(*, revision: int = 1, name: str = "Default") -> SpectrogramSettingsSnapshot:
    return SpectrogramSettingsSnapshot.create(
        preset_id="rsp_" + "1" * 32,
        preset_name=name,
        preset_revision=revision,
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
        effective_settings={
            "frequency_limit_hz": 4_200,
            "palette": "viridis",
            "advanced": {"channel_policy": "per-channel-power"},
        },
    )


def test_review_labels_bulk_provenance_and_bounded_undo_are_pure() -> None:
    """Case: UT-REVW-003."""
    first = "cand_" + "1" * 32
    second = "cand_" + "2" * 32
    third = "cand_" + "3" * 32
    book = AnnotationBook.create((first, second, third))

    book, call = book.set_label(
        first,
        ReviewLabel.CALL,
        expected_revision=0,
        modified_at="2026-11-04T10:00:00.000Z",
    )
    book, rejection = book.set_label(
        second,
        ReviewLabel.NOT_CALL,
        expected_revision=1,
        modified_at="2026-11-04T10:01:00.000Z",
    )
    book, batch = book.accept_all(
        expected_revision=2,
        modified_at="2026-11-04T10:02:00.000Z",
    )

    assert call.kind == "individual"
    assert rejection.kind == "individual"
    assert batch.kind == "accept_all"
    assert batch.changed_count == 1
    assert book.decision(first).origin is DecisionOrigin.INDIVIDUAL
    assert book.decision(second).label is ReviewLabel.NOT_CALL
    assert book.decision(third).origin is DecisionOrigin.BULK

    undone = book.undo(batch, expected_revision=3)
    assert undone.label_for(first) is ReviewLabel.CALL
    assert undone.label_for(second) is ReviewLabel.NOT_CALL
    assert undone.label_for(third) is ReviewLabel.UNREVIEWED
    redone = undone.redo(batch, expected_revision=4)
    assert redone.label_for(third) is ReviewLabel.CALL
    assert redone.decision(third).origin is DecisionOrigin.BULK

    cleared, clear = redone.set_label(
        first,
        ReviewLabel.UNREVIEWED,
        expected_revision=5,
        modified_at="2026-11-04T10:03:00.000Z",
    )
    assert clear.kind == "individual"
    assert cleared.label_for(first) is ReviewLabel.UNREVIEWED

    before = cleared
    with pytest.raises(KeyError, match="eligible"):
        cleared.set_label(
            "cand_" + "f" * 32,
            ReviewLabel.CALL,
            expected_revision=6,
            modified_at="2026-11-04T10:04:00.000Z",
        )
    with pytest.raises(ReviewRevisionConflict):
        cleared.set_label(
            first,
            ReviewLabel.CALL,
            expected_revision=5,
            modified_at="2026-11-04T10:04:00.000Z",
        )
    assert cleared == before


def test_session_transitions_finalization_and_settings_snapshots_are_immutable() -> None:
    """Case: UT-REVW-004."""
    require_session_transition(ReviewSessionState.OPEN, ReviewSessionState.CLOSED)
    require_session_transition(ReviewSessionState.CLOSED, ReviewSessionState.OPEN)
    require_session_transition(ReviewSessionState.OPEN, ReviewSessionState.FINALIZED)
    with pytest.raises(ValueError, match="Finalized"):
        require_session_transition(ReviewSessionState.FINALIZED, ReviewSessionState.OPEN)

    original_settings = _settings()
    edited_preset = _settings(revision=2, name="Low-frequency field work")
    assert edited_preset.settings_digest != original_settings.settings_digest
    assert original_settings.preset_name == "Default"
    assert original_settings.effective_settings["frequency_limit_hz"] == 4_200
    assert SpectrogramSettingsSnapshot.from_dict(original_settings.to_dict()) == original_settings
    with pytest.raises(ValueError, match="digest"):
        SpectrogramSettingsSnapshot.from_dict(
            {**original_settings.to_dict(), "settings_digest": "f" * 64}
        )

    rows = (
        FinalizedCandidateDecision(
            0,
            "cand_" + "1" * 32,
            ReviewLabel.CALL,
            DecisionOrigin.INDIVIDUAL,
            "2026-11-04T10:00:00.000Z",
        ),
        FinalizedCandidateDecision(
            1,
            "cand_" + "2" * 32,
            ReviewLabel.NOT_CALL,
            DecisionOrigin.INDIVIDUAL,
            "2026-11-04T10:01:00.000Z",
        ),
        FinalizedCandidateDecision(
            2,
            "cand_" + "3" * 32,
            ReviewLabel.UNREVIEWED,
            None,
            None,
        ),
    )
    snapshot = ReviewFinalizationSnapshot.create(
        session_id="rsn_" + "a" * 32,
        session_name="Autumn survey review",
        source_digest="b" * 64,
        settings=original_settings,
        parent_session_id=None,
        parent_snapshot_digest=None,
        finalized_at="2026-11-04T11:00:00.000Z",
        candidates=rows,
    )
    assert (snapshot.call_count, snapshot.not_call_count, snapshot.unreviewed_count) == (1, 1, 1)
    assert snapshot.partial
    assert ReviewFinalizationSnapshot.from_dict(snapshot.to_dict()) == snapshot
    with pytest.raises(ValueError, match="digest"):
        replace(snapshot, session_name="Changed")

    child_settings = SpectrogramSettingsSnapshot.from_dict(snapshot.settings.to_dict())
    assert child_settings == original_settings
    assert child_settings is not original_settings
