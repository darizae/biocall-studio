from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from biocall_studio.review.application.storage import (
    assess_review_export_storage,
    estimate_review_export_artifacts,
)
from biocall_studio.review.domain.exports import (
    RIFF_MAX_DATA_BYTES,
    ReviewExportMode,
    ReviewExportSourceCandidate,
    ReviewSourceWaveFormat,
    create_review_export_plan,
    iter_plan_rows,
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
    DecisionOrigin,
    FinalizedCandidateDecision,
    ReviewFinalizationSnapshot,
    ReviewLabel,
    ReviewSessionSource,
    SpectrogramSettingsSnapshot,
)
from biocall_studio.shared.storage import CapacityObservation, StorageDecision


def _candidate(ordinal: int, *, channels: int = 1, frames: int = 200_000) -> EligibleCandidate:
    start = ordinal * 10
    return EligibleCandidate(
        ordinal=ordinal,
        recording_ordinal=0,
        candidate_id=f"cand_{ordinal + 1:032x}",
        recording_ref="rec_" + "1" * 32,
        recording_key="recordings/field.wav",
        source_sha256="2" * 64,
        sample_rate_hz=8_000,
        frame_count=frames,
        channels=channels,
        start_frame=start,
        end_frame=start + 5,
        start_time_ns=(start * 1_000_000_000 + 4_000) // 8_000,
        end_time_ns=((start + 5) * 1_000_000_000 + 4_000) // 8_000,
        cnn_target_score=0.75,
        rf_target_score=None,
        contributing_windows=1,
    )


def _finalized() -> tuple[
    ReviewFinalizationSnapshot, ReviewSessionSource, tuple[ReviewExportSourceCandidate, ...]
]:
    candidates = tuple(_candidate(index) for index in range(4))
    recording = ReviewRecording(
        ordinal=0,
        recording_ref=candidates[0].recording_ref,
        recording_key=candidates[0].recording_key,
        source_sha256=candidates[0].source_sha256,
        sample_rate_hz=8_000,
        frame_count=200_000,
        channels=1,
        failed=False,
        error_code="",
        eligible_candidate_count=4,
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
        eligible_candidate_count=4,
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
    settings = SpectrogramSettingsSnapshot.create(
        preset_id="rsp_" + "9" * 32,
        preset_name="Historical field preset",
        preset_revision=3,
        algorithm_version="spectrogram-contract-v1",
        render_version="raster-contract-v1",
        effective_settings={"frequency_limit_hz": 4_200},
    )
    decisions = (
        FinalizedCandidateDecision(
            0,
            candidates[0].candidate_id,
            ReviewLabel.CALL,
            DecisionOrigin.INDIVIDUAL,
            "2026-11-05T10:00:00.000Z",
        ),
        FinalizedCandidateDecision(
            1,
            candidates[1].candidate_id,
            ReviewLabel.CALL,
            DecisionOrigin.BULK,
            "2026-11-05T10:01:00.000Z",
        ),
        FinalizedCandidateDecision(
            2,
            candidates[2].candidate_id,
            ReviewLabel.NOT_CALL,
            DecisionOrigin.INDIVIDUAL,
            "2026-11-05T10:02:00.000Z",
        ),
        FinalizedCandidateDecision(
            3, candidates[3].candidate_id, ReviewLabel.UNREVIEWED, None, None
        ),
    )
    finalized = ReviewFinalizationSnapshot.create(
        session_id="rsn_" + "a" * 32,
        session_name="Final field review",
        source_digest=source.source_digest,
        settings=settings,
        parent_session_id=None,
        parent_snapshot_digest=None,
        finalized_at="2026-11-05T11:00:00.000Z",
        candidates=decisions,
    )
    return (
        finalized,
        source,
        tuple(
            ReviewExportSourceCandidate(candidate, decision)
            for candidate, decision in zip(candidates, decisions, strict=True)
        ),
    )


def test_finalized_projection_preserves_truth_inventory_and_order(tmp_path: Path) -> None:
    """Case: UT-REVW-010."""
    finalized, source, candidates = _finalized()
    formats = {candidates[0].candidate.recording_ref: ReviewSourceWaveFormat(8_000, 1, 2)}
    plan = create_review_export_plan(
        finalization=finalized,
        source=source,
        candidates=iter(candidates),
        source_formats=formats,
        mode=ReviewExportMode.BOTH,
        destination_parent=tmp_path,
        export_id="rexp_" + "b" * 32,
        created_at="2026-11-05T12:00:00.000Z",
    )
    rows = tuple(iter_plan_rows(plan, iter(candidates), formats))

    assert [row.candidate_id for row in rows] == [row.candidate.candidate_id for row in candidates]
    assert [row.export_status for row in rows] == [
        "human_individual",
        "human_bulk",
        "human_rejected",
        "model_only",
    ]
    assert [row.included for row in rows] == [True, True, False, True]
    assert rows[2].output_relative_path is None
    assert rows[2].concat_start_frame is None
    assert plan.included_count == 3
    assert plan.rejected_count == 1
    assert plan.settings_digest == finalized.settings.settings_digest
    assert plan.rows_sha256
    assert plan.eligible_count == len(rows)

    with pytest.raises(ValueError, match="finalized|decision"):
        create_review_export_plan(
            finalization=finalized,
            source=source,
            candidates=iter(candidates[:-1]),
            source_formats=formats,
            mode=ReviewExportMode.INDIVIDUAL,
            destination_parent=tmp_path,
            export_id="rexp_" + "c" * 32,
            created_at="2026-11-05T12:00:00.000Z",
        )
    extra_candidate = replace(
        candidates[-1].candidate,
        ordinal=4,
        candidate_id="cand_" + "e" * 32,
        start_frame=40,
        end_frame=45,
        start_time_ns=5_000_000,
        end_time_ns=5_625_000,
    )
    extra_decision = FinalizedCandidateDecision(
        4,
        extra_candidate.candidate_id,
        ReviewLabel.UNREVIEWED,
        None,
        None,
    )
    with pytest.raises(ValueError, match="outside the finalized inventory"):
        create_review_export_plan(
            finalization=finalized,
            source=source,
            candidates=iter(
                (*candidates, ReviewExportSourceCandidate(extra_candidate, extra_decision))
            ),
            source_formats=formats,
            mode=ReviewExportMode.INDIVIDUAL,
            destination_parent=tmp_path,
            export_id="rexp_" + "0" * 32,
            created_at="2026-11-05T12:00:00.000Z",
        )


def test_streamed_v2_arithmetic_has_no_10k_cap_and_guards_riff(tmp_path: Path) -> None:
    """Case: UT-REVW-011."""
    finalized, source, candidates = _finalized()
    formats = {candidates[0].candidate.recording_ref: ReviewSourceWaveFormat(8_000, 1, 2)}
    plan = create_review_export_plan(
        finalization=finalized,
        source=source,
        candidates=iter(candidates),
        source_formats=formats,
        mode=ReviewExportMode.COMBINED,
        destination_parent=tmp_path,
        export_id="rexp_" + "d" * 32,
        created_at="2026-11-05T12:00:00.000Z",
    )
    assert plan.expected_final_bytes > plan.rows_byte_size
    assert plan.concat_pcm_bytes == 3 * 5 * 2
    size_plan = estimate_review_export_artifacts(plan)
    assert size_plan.expected_final.high_bytes == plan.expected_final_bytes
    label = tmp_path.name
    capacity = CapacityObservation(
        label,
        "test-volume",
        2 * 1024**3,
        datetime.now(UTC),
    )
    ready = assess_review_export_storage(plan, capacity=capacity)
    assert ready.decision is StorageDecision.READY
    stale = assess_review_export_storage(
        plan,
        capacity=capacity,
        expected_input_digest="f" * 64,
    )
    assert stale.decision is StorageDecision.STALE

    mixed_formats = {candidates[0].candidate.recording_ref: ReviewSourceWaveFormat(8_000, 2, 2)}
    with pytest.raises(ValueError, match="mono|format"):
        create_review_export_plan(
            finalization=finalized,
            source=source,
            candidates=iter(candidates),
            source_formats=mixed_formats,
            mode=ReviewExportMode.COMBINED,
            destination_parent=tmp_path,
            export_id="rexp_" + "e" * 32,
            created_at="2026-11-05T12:00:00.000Z",
        )

    huge = replace(
        candidates[0].candidate,
        frame_count=RIFF_MAX_DATA_BYTES + 10,
        end_frame=RIFF_MAX_DATA_BYTES // 2 + 1,
        end_time_ns=((RIFF_MAX_DATA_BYTES // 2 + 1) * 1_000_000_000 + 4_000) // 8_000,
    )
    huge_decision = candidates[0].decision
    huge_source = ReviewExportSourceCandidate(huge, huge_decision)
    huge_recording = replace(
        source.recordings[0],
        frame_count=huge.frame_count,
        eligible_candidate_count=1,
    )
    huge_manifest = replace(
        source.manifest,
        projection_digest="0" * 64,
        eligible_candidate_count=1,
    )
    huge_manifest = replace(
        huge_manifest,
        projection_digest=projection_digest(huge_manifest, (huge_recording,), (huge,)),
    )
    huge_projection = ReviewIntakeProjection(
        huge_manifest,
        (huge_recording,),
        (huge,),
    )
    huge_session_source = ReviewSessionSource.from_projection(
        huge_projection,
        score_semantics=source.score_semantics,
        eligibility_threshold=source.eligibility_threshold,
    )
    huge_final = ReviewFinalizationSnapshot.create(
        session_id=finalized.session_id,
        session_name=finalized.session_name,
        source_digest=huge_session_source.source_digest,
        settings=finalized.settings,
        parent_session_id=None,
        parent_snapshot_digest=None,
        finalized_at=finalized.finalized_at,
        candidates=(replace(huge_decision, ordinal=0),),
    )
    with pytest.raises(ValueError, match="combined WAV would be too large"):
        create_review_export_plan(
            finalization=huge_final,
            source=huge_session_source,
            candidates=iter((huge_source,)),
            source_formats=formats,
            mode=ReviewExportMode.COMBINED,
            destination_parent=tmp_path,
            export_id="rexp_" + "f" * 32,
            created_at="2026-11-05T12:00:00.000Z",
        )


def test_pure_plan_accepts_more_than_ten_thousand_rows(tmp_path: Path) -> None:
    """Case: UT-REVW-011."""
    count = 10_001
    frame_count = count * 10 + 10
    candidates = tuple(_candidate(index, frames=frame_count) for index in range(count))
    _final, source, _rows = _finalized()
    recording = replace(
        source.recordings[0],
        frame_count=frame_count,
        eligible_candidate_count=count,
    )
    manifest = replace(
        source.manifest,
        projection_digest="0" * 64,
        eligible_candidate_count=count,
    )
    manifest = replace(
        manifest,
        projection_digest=projection_digest(manifest, (recording,), candidates),
    )
    projection = ReviewIntakeProjection(manifest, (recording,), candidates)
    large_source = ReviewSessionSource.from_projection(
        projection,
        score_semantics=source.score_semantics,
        eligibility_threshold=source.eligibility_threshold,
    )
    decisions = tuple(
        FinalizedCandidateDecision(
            index,
            candidate.candidate_id,
            ReviewLabel.UNREVIEWED,
            None,
            None,
        )
        for index, candidate in enumerate(candidates)
    )
    finalization = ReviewFinalizationSnapshot.create(
        session_id="rsn_" + "d" * 32,
        session_name="Large finalized review",
        source_digest=large_source.source_digest,
        settings=_final.settings,
        parent_session_id=None,
        parent_snapshot_digest=None,
        finalized_at="2026-11-05T12:00:00.000Z",
        candidates=decisions,
    )
    source_candidates = (
        ReviewExportSourceCandidate(candidate, decision)
        for candidate, decision in zip(candidates, decisions, strict=True)
    )
    plan = create_review_export_plan(
        finalization=finalization,
        source=large_source,
        candidates=source_candidates,
        source_formats={recording.recording_ref: ReviewSourceWaveFormat(8_000, 1, 2)},
        mode=ReviewExportMode.COMBINED,
        destination_parent=tmp_path,
        export_id="rexp_" + "1" * 32,
        created_at="2026-11-05T12:01:00.000Z",
    )
    assert plan.eligible_count == 10_001
    assert plan.model_only_count == 10_001
