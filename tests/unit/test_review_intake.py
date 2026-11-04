from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from biocall_studio.detect.domain.detection import DetectionSettings
from biocall_studio.detect.domain.inventory import (
    ChangeKind,
    DecisionOrigin,
    InclusionDecision,
    InventoryRecording,
    InventorySnapshot,
    RecordingStatus,
    WavMetadata,
)
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    RecordingOutcome,
    candidate_identity,
    recording_identity,
)
from biocall_studio.detect.domain.rf_refinement import (
    DerivedResult,
    RefinementDecision,
)
from biocall_studio.review.domain.intake import (
    REVIEW_INTAKE_SCHEMA_VERSION,
    ReviewResultKind,
    build_review_projection,
)


def _inventory_row(
    key: str,
    source_sha256: str,
    *,
    sample_rate_hz: int = 8_000,
    frame_count: int = 16_000,
    channels: int = 2,
) -> InventoryRecording:
    return InventoryRecording(
        recording_key=key,
        size_bytes=64_044,
        mtime_ns=123_456_789,
        content_sha256=source_sha256,
        wav=WavMetadata(sample_rate_hz, channels, frame_count, "pcm_s16le"),
        decision=InclusionDecision.INCLUDED,
        status=RecordingStatus.VALID,
        reason="Included by the recordings policy.",
        decision_origin=DecisionOrigin.POLICY,
        decision_path="recordings",
        change=ChangeKind.ADDED,
    )


def _inventory(*rows: InventoryRecording) -> InventorySnapshot:
    return InventorySnapshot.create(
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        recordings=rows,
        scanned_at=datetime(2026, 11, 4, 9, 0, tzinfo=UTC),
    )


def _parent(
    inventory: InventorySnapshot,
    *,
    candidate_frames: tuple[tuple[int, int], ...] = (
        (800, 1_600),
        (3_200, 4_000),
        (6_400, 7_200),
    ),
    failed_second: bool = False,
) -> DetectionResult:
    recordings: list[RecordingOutcome] = []
    for row_index, row in enumerate(inventory.recordings):
        assert row.content_sha256 is not None and row.wav is not None
        recording_ref = recording_identity(
            inventory.inventory_id,
            row.recording_key,
            row.content_sha256,
        )
        if failed_second and row_index == 1:
            recordings.append(
                RecordingOutcome.failed(
                    recording_ref=recording_ref,
                    recording_key=row.recording_key,
                    source_sha256=row.content_sha256,
                    sample_rate_hz=row.wav.sample_rate_hz,
                    frame_count=row.wav.frame_count,
                    channels=row.wav.channels,
                    error_code="audio_decode_failed",
                )
            )
            continue
        frames = candidate_frames if row_index == 0 else ()
        candidates = tuple(
            CandidateInterval.create(
                candidate_id=candidate_identity(
                    recording_ref,
                    start,
                    end,
                    f"rv01-cnn-{row_index}-{index}",
                ),
                recording_ref=recording_ref,
                start_frame=start,
                end_frame=end,
                sample_rate_hz=row.wav.sample_rate_hz,
                max_target_score=0.9 - index / 10,
                contributing_windows=index + 1,
            )
            for index, (start, end) in enumerate(frames)
        )
        recordings.append(
            RecordingOutcome.succeeded(
                recording_ref=recording_ref,
                recording_key=row.recording_key,
                source_sha256=row.content_sha256,
                sample_rate_hz=row.wav.sample_rate_hz,
                frame_count=row.wav.frame_count,
                channels=row.wav.channels,
                candidates=candidates,
            )
        )
    settings = DetectionSettings(0.5, 50, 125, 8)
    return DetectionResult.create(
        result_id="pub_" + "a" * 32,
        run_id="drun_" + "b" * 32,
        request_id="dreq_" + "c" * 32,
        collection_id=inventory.collection_id,
        binding_revision=inventory.binding_revision,
        inventory_id=inventory.inventory_id,
        inventory_digest=inventory.digest,
        model_id="model-cnn",
        model_snapshot_id="mdl_" + "3" * 32,
        model_manifest_sha256="4" * 64,
        model_artifact_sha256="5" * 64,
        model_snapshot_digest="6" * 64,
        settings=settings,
        window_length_samples=4_000,
        hop_samples=settings.hop_samples(4_000),
        model_sample_rate_hz=16_000,
        backend_distribution="bioacoustics-dl-toolbox",
        backend_version="0.2.0",
        backend_revision="22c1b342",
        completed_at="2026-11-04T09:01:00.000Z",
        recordings=tuple(recordings),
    )


def _derived(
    parent: DetectionResult,
    decisions: dict[str, RefinementDecision],
    *,
    result_token: str = "e",
) -> DerivedResult:
    return DerivedResult.create(
        result_id="pub_" + result_token * 32,
        run_id="drun_" + "f" * 32,
        request_id="dreq_" + "0" * 32,
        parent=parent,
        rf_model_id="model-rf",
        rf_model_snapshot_id="mdl_" + "8" * 32,
        rf_model_manifest_sha256="9" * 64,
        rf_model_artifact_sha256="a" * 64,
        rf_model_snapshot_digest="b" * 64,
        threshold=0.6,
        probability_class_order=(0, 1),
        target_probability_column=1,
        feature_family="robust-mfcc-v1",
        feature_names=("mfcc_mean_1", "mfcc_std_1"),
        feature_config=(("sample_rate_hz", 8_000), ("min_duration_s", 0.5)),
        preprocessing_order=("decode", "mixdown_mono", "resample"),
        backend_distribution="scikit-learn",
        backend_version="1.7.2",
        backend_revision="22c1b342",
        completed_at="2026-11-04T09:02:00.000Z",
        decisions=decisions,
    )


def test_review_eligibility_is_cnn_all_and_rf_accepted_only_in_source_order():
    """Case: UT-REVW-001."""
    inventory = _inventory(_inventory_row("recordings/dawn.wav", "7" * 64))
    parent = _parent(inventory)
    first, second, third = parent.recordings[0].candidates
    child = _derived(
        parent,
        {
            first.candidate_id: RefinementDecision.scored(0.9, threshold=0.6),
            second.candidate_id: RefinementDecision.scored(0.2, threshold=0.6),
            third.candidate_id: RefinementDecision.unscored("feature_extraction_failed"),
        },
    )

    cnn = build_review_projection(
        parent,
        inventory,
        publication_digest="1" * 64,
    )
    rf = build_review_projection(
        child,
        inventory,
        publication_digest="2" * 64,
        parent=parent,
    )

    assert cnn.manifest.result_kind is ReviewResultKind.CNN
    assert tuple(row.candidate_id for row in cnn.candidates) == (
        first.candidate_id,
        second.candidate_id,
        third.candidate_id,
    )
    assert rf.manifest.result_kind is ReviewResultKind.RF
    assert tuple(row.candidate_id for row in rf.candidates) == (first.candidate_id,)
    assert rf.candidates[0].rf_target_score == pytest.approx(0.9)
    assert second.candidate_id not in {row.candidate_id for row in rf.candidates}
    assert third.candidate_id not in {row.candidate_id for row in rf.candidates}

    wrong_parent = DetectionResult.from_dict(parent.to_dict())
    object.__setattr__(wrong_parent, "result_id", "pub_" + "1" * 32)
    with pytest.raises(ValueError, match="parent|digest"):
        build_review_projection(
            child,
            inventory,
            publication_digest="2" * 64,
            parent=wrong_parent,
        )

    original_candidates = parent.recordings[0].candidates
    object.__setattr__(
        parent.recordings[0],
        "candidates",
        (*original_candidates, original_candidates[0]),
    )
    with pytest.raises(ValueError, match="candidate|digest|provenance"):
        build_review_projection(parent, inventory, publication_digest="1" * 64)


def test_review_projection_is_versioned_digest_bound_and_distinguishes_zero_from_failure():
    """Case: UT-REVW-002."""
    first = _inventory_row("recordings/quiet.wav", "7" * 64, channels=1)
    second = _inventory_row("recordings/broken.wav", "8" * 64, channels=2)
    inventory = _inventory(first, second)
    zero = _parent(inventory, candidate_frames=(), failed_second=True)

    projection = build_review_projection(
        zero,
        inventory,
        publication_digest="1" * 64,
    )

    assert projection.manifest.schema_version == REVIEW_INTAKE_SCHEMA_VERSION
    assert projection.manifest.eligible_candidate_count == 0
    assert projection.manifest.failed_recording_count == 1
    assert projection.candidates == ()
    by_key = {row.recording_key: row for row in projection.recordings}
    assert by_key["recordings/quiet.wav"].sample_rate_hz == 8_000
    assert by_key["recordings/quiet.wav"].channels == 1
    assert by_key["recordings/quiet.wav"].failed
    assert projection.manifest.result_digest == zero.result_digest
    assert projection.manifest.inventory_digest == inventory.digest
    assert projection.manifest.projection_digest != zero.result_digest

    stale_inventory = replace(inventory, digest="9" * 64)
    with pytest.raises(ValueError, match="Inventory|inventory|digest"):
        build_review_projection(zero, stale_inventory, publication_digest="1" * 64)

    unsafe_inventory = _inventory(first, second)
    object.__setattr__(unsafe_inventory.recordings[0], "recording_key", "../escape.wav")
    with pytest.raises(ValueError, match="traversal|reference|Inventory|inventory"):
        build_review_projection(zero, unsafe_inventory, publication_digest="1" * 64)

    unsupported = zero.to_dict()
    unsupported["schema_version"] = 999
    with pytest.raises(ValueError, match="schema"):
        build_review_projection(
            DetectionResult.from_dict(unsupported),
            inventory,
            publication_digest="1" * 64,
        )
