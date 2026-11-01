from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from biocall_studio.detect.domain.detection import DetectionSettings
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
    RefinementStatus,
    ordered_feature_vector,
    prepare_candidate_segment,
    target_probability_score,
)


def _parent() -> DetectionResult:
    inventory_id = "inv_" + "1" * 32
    recording_ref = recording_identity(
        inventory_id, "recordings/dawn.wav", "7" * 64
    )
    candidates = tuple(
        CandidateInterval.create(
            candidate_id=candidate_identity(
                recording_ref, start, end, f"cnn-science-{index}"
            ),
            recording_ref=recording_ref,
            start_frame=start,
            end_frame=end,
            sample_rate_hz=8_000,
            max_target_score=0.91 - index / 10,
            contributing_windows=index + 1,
        )
        for index, (start, end) in enumerate(((800, 2_400), (4_000, 4_400)))
    )
    settings = DetectionSettings(0.5, 50, 125, 8)
    return DetectionResult.create(
        result_id="pub_" + "a" * 32,
        run_id="drun_" + "b" * 32,
        request_id="dreq_" + "c" * 32,
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        inventory_id=inventory_id,
        inventory_digest="2" * 64,
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
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:00:00.000Z",
        recordings=(
            RecordingOutcome.succeeded(
                recording_ref=recording_ref,
                recording_key="recordings/dawn.wav",
                source_sha256="7" * 64,
                sample_rate_hz=8_000,
                frame_count=16_000,
                channels=2,
                candidates=candidates,
            ),
        ),
    )


def _derived(
    parent: DetectionResult,
    decisions: dict[str, RefinementDecision],
) -> DerivedResult:
    return DerivedResult.create(
        result_id="pub_" + "e" * 32,
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
        feature_names=("first", "second"),
        feature_config=(("sample_rate_hz", 8_000), ("min_duration_s", 0.5)),
        preprocessing_order=("decode", "mixdown_mono", "resample", "minimum_pad"),
        backend_distribution="scikit-learn",
        backend_version="1.7.2",
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:01:00.000Z",
        decisions=decisions,
    )


def test_ordered_rf_features_and_probability_class_column_are_strict():
    """Case: UT-DET-018."""
    vector = ordered_feature_vector(
        {"first": 1.25, "second": -2.5}, ("first", "second")
    )
    assert vector.dtype == np.float64
    assert vector.shape == (1, 2)
    assert vector.tolist() == [[1.25, -2.5]]

    with pytest.raises(ValueError, match="order"):
        ordered_feature_vector(
            {"second": -2.5, "first": 1.25}, ("first", "second")
        )
    with pytest.raises(ValueError, match="non-finite"):
        ordered_feature_vector(
            {"first": 1.25, "second": float("nan")}, ("first", "second")
        )

    assert target_probability_score(
        np.asarray([[0.2, 0.8]], dtype=np.float64),
        estimator_classes=np.asarray([0, 1]),
        probability_class_order=(0, 1),
        target_probability_column=1,
    ) == pytest.approx(0.8)
    assert target_probability_score(
        np.asarray([[0.8, 0.2]], dtype=np.float64),
        estimator_classes=np.asarray([1, 0]),
        probability_class_order=(1, 0),
        target_probability_column=0,
    ) == pytest.approx(0.8)
    with pytest.raises(ValueError, match="class order"):
        target_probability_score(
            np.asarray([[0.2, 0.8]]),
            estimator_classes=np.asarray([1, 0]),
            probability_class_order=(0, 1),
            target_probability_column=1,
        )
    with pytest.raises(ValueError, match="non-finite"):
        target_probability_score(
            np.asarray([[float("nan"), 0.8]]),
            estimator_classes=np.asarray([0, 1]),
            probability_class_order=(0, 1),
            target_probability_column=1,
        )


def test_candidate_decisions_and_short_segment_policy_are_truthful():
    """Case: UT-DET-019."""
    accepted = RefinementDecision.scored(0.6, threshold=0.6)
    rejected = RefinementDecision.scored(0.599, threshold=0.6)
    unscored = RefinementDecision.unscored("feature_extraction_failed")
    assert accepted.status is RefinementStatus.ACCEPTED
    assert rejected.status is RefinementStatus.REJECTED
    assert unscored.status is RefinementStatus.UNSCORED
    assert unscored.rf_target_score is None
    assert unscored.unscored_reason == "feature_extraction_failed"

    signal = np.asarray([1.0, -1.0], dtype=np.float32)
    padded = prepare_candidate_segment(
        signal,
        source_sample_rate_hz=4,
        start_frame=0,
        end_frame=2,
        target_sample_rate_hz=4,
        minimum_duration_seconds=1.0,
        short_segment_policy="center_zero_pad",
    )
    assert padded is not None
    assert padded.dtype == np.float32
    assert padded.tolist() == [0.0, 1.0, -1.0, 0.0]
    assert (
        prepare_candidate_segment(
            signal,
            source_sample_rate_hz=4,
            start_frame=0,
            end_frame=2,
            target_sample_rate_hz=4,
            minimum_duration_seconds=1.0,
            short_segment_policy="reject",
        )
        is None
    )
    with pytest.raises(ValueError, match="policy"):
        prepare_candidate_segment(
            signal,
            source_sample_rate_hz=4,
            start_frame=0,
            end_frame=2,
            target_sample_rate_hz=4,
            minimum_duration_seconds=1.0,
            short_segment_policy="silently_reject",
        )


def test_derived_result_preserves_parent_lineage_identity_time_and_checksums():
    """Case: UT-DET-020."""
    parent = _parent()
    first, second = parent.recordings[0].candidates
    child = _derived(
        parent,
        {
            first.candidate_id: RefinementDecision.scored(0.8, threshold=0.6),
            second.candidate_id: RefinementDecision.unscored("short_segment"),
        },
    )

    assert child.parent_result_id == parent.result_id
    assert child.parent_result_digest == parent.result_digest
    assert child.parent_run_id == parent.run_id
    assert child.collection_id == parent.collection_id
    assert child.inventory_id == parent.inventory_id
    assert child.candidate_count == parent.candidate_count == 2
    assert (child.accepted_count, child.rejected_count, child.unscored_count) == (1, 0, 1)
    assert child.recordings[0].source_sha256 == parent.recordings[0].source_sha256
    assert child.recordings[0].candidates[0].candidate_id == first.candidate_id
    assert child.recordings[0].candidates[0].start_frame == first.start_frame
    assert child.recordings[0].candidates[0].start_time_ns == first.start_time_ns
    assert child.recordings[0].candidates[0].max_target_score == first.max_target_score
    assert DerivedResult.from_dict(child.to_dict()) == child
    child.verify_parent(parent)
    with pytest.raises(FrozenInstanceError):
        child.parent_result_id = "pub_" + "1" * 32  # type: ignore[misc]

    changed_parent = _parent()
    object.__setattr__(changed_parent, "result_digest", "1" * 64)
    with pytest.raises(ValueError, match="parent"):
        child.verify_parent(changed_parent)
    with pytest.raises(ValueError, match="exactly one decision"):
        _derived(
            parent,
            {first.candidate_id: RefinementDecision.scored(0.8, threshold=0.6)},
        )
    with pytest.raises(ValueError, match="candidate"):
        _derived(
            parent,
            {
                first.candidate_id: RefinementDecision.scored(0.8, threshold=0.6),
                "cand_" + "1" * 32: RefinementDecision.scored(0.7, threshold=0.6),
            },
        )
