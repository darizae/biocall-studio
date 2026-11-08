from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from biocall_studio.detect.domain.detection import (
    DetectionSettings,
    WindowScore,
    map_resampled_interval_to_source,
    merge_candidate_windows,
    target_score,
)
from biocall_studio.detect.domain.results import (
    CandidateInterval,
    DetectionResult,
    FileOutcomeStatus,
    RecordingOutcome,
    ResultCompleteness,
    candidate_identity,
    recording_identity,
)


def test_window_hop_resample_padding_arithmetic_and_invalid_configuration():
    """Case: UT-DET-013."""
    settings = DetectionSettings(
        minimum_score=0.5,
        window_overlap_percent=25,
        combine_gap_ms=0,
        batch_size=16,
    )
    assert settings.hop_samples(11) == 8  # nearest integer, half upward
    assert settings.hop_samples(4_000) == 3_000
    assert map_resampled_interval_to_source(
        3,
        8,
        model_sample_rate_hz=8_000,
        source_sample_rate_hz=44_100,
        source_frame_count=100_000,
    ) == (16, 45)
    # A padded final inference window still ends at the original recording boundary.
    assert map_resampled_interval_to_source(
        15_999,
        16_000,
        model_sample_rate_hz=16_000,
        source_sample_rate_hz=44_100,
        source_frame_count=44_099,
    ) == (44_097, 44_099)

    for values in (
        (-0.01, 50, 0, 16),
        (1.01, 50, 0, 16),
        (0.5, 100, 0, 16),
        (0.5, -1, 0, 16),
        (0.5, 50, -1, 16),
        (0.5, 50, 0, 0),
    ):
        with pytest.raises(ValueError):
            DetectionSettings(*values)
    with pytest.raises(ValueError, match="source interval"):
        map_resampled_interval_to_source(
            2,
            2,
            model_sample_rate_hz=8_000,
            source_sample_rate_hz=16_000,
            source_frame_count=100,
        )


def test_target_score_threshold_and_merge_semantics_reject_ambiguous_outputs():
    """Case: UT-DET-014."""
    assert (
        target_score(
            {"noise": 0.5, "target": 0.5},
            class_to_index=(("noise", 0), ("target", 1)),
        )
        == 0.5
    )
    for probabilities in (
        {"target": 0.8, "noise": 0.2},  # wrong output-column order
        {"noise": 0.2},
        {"noise": 0.2, "target": 0.8, "other": 0.0},
        {"noise": float("nan"), "target": 0.8},
        {"noise": 0.4, "target": 0.8},
    ):
        with pytest.raises(ValueError, match="output|finite|sum"):
            target_score(
                probabilities,
                class_to_index=(("noise", 0), ("target", 1)),
            )

    settings = DetectionSettings(0.5, 50, 125, 8)
    merged = merge_candidate_windows(
        (
            WindowScore(0, 0, 4_000, 0.49),
            WindowScore(1, 2_000, 6_000, 0.50),
            WindowScore(2, 4_000, 8_000, 0.90),
            WindowScore(3, 10_000, 12_000, 0.70),
        ),
        settings=settings,
        model_sample_rate_hz=8_000,
        source_sample_rate_hz=16_000,
        source_frame_count=24_000,
    )
    # Threshold is inclusive. Overlapping windows merge; a 250 ms gap stays separate.
    assert merged == (
        (4_000, 16_000, 0.90, 2),
        (20_000, 24_000, 0.70, 1),
    )
    with pytest.raises(ValueError, match="finite"):
        merge_candidate_windows(
            (WindowScore(0, 0, 4_000, float("inf")),),
            settings=settings,
            model_sample_rate_hz=8_000,
            source_sample_rate_hz=16_000,
            source_frame_count=24_000,
        )


def _candidate(recording_ref: str, seed: str = "seed") -> CandidateInterval:
    return CandidateInterval.create(
        candidate_id=candidate_identity(recording_ref, 160, 320, seed),
        recording_ref=recording_ref,
        start_frame=160,
        end_frame=320,
        sample_rate_hz=16_000,
        max_target_score=0.75,
        contributing_windows=2,
    )


def test_source_timestamps_deterministic_ids_immutable_result_and_file_statuses():
    """Case: UT-DET-015."""
    recording_ref = recording_identity(
        "inv_" + "1" * 32,
        "recordings/a.wav",
        "2" * 64,
    )
    assert recording_ref == recording_identity(
        "inv_" + "1" * 32,
        "recordings/a.wav",
        "2" * 64,
    )
    candidate = _candidate(recording_ref)
    assert (candidate.start_time_ns, candidate.end_time_ns) == (10_000_000, 20_000_000)
    assert candidate.candidate_id == _candidate(recording_ref).candidate_id

    succeeded = RecordingOutcome.succeeded(
        recording_ref=recording_ref,
        recording_key="recordings/a.wav",
        source_sha256="2" * 64,
        sample_rate_hz=16_000,
        frame_count=1_600,
        channels=1,
        candidates=(candidate,),
    )
    zero = RecordingOutcome.succeeded(
        recording_ref=recording_identity("inv_" + "1" * 32, "recordings/zero.wav", "3" * 64),
        recording_key="recordings/zero.wav",
        source_sha256="3" * 64,
        sample_rate_hz=16_000,
        frame_count=1_600,
        channels=2,
        candidates=(),
    )
    failed = RecordingOutcome.failed(
        recording_ref=recording_identity("inv_" + "1" * 32, "recordings/broken.wav", "4" * 64),
        recording_key="recordings/broken.wav",
        source_sha256="4" * 64,
        sample_rate_hz=16_000,
        frame_count=0,
        channels=1,
        error_code="audio_decode_failed",
    )
    result = DetectionResult.create(
        result_id="pub_" + "a" * 32,
        run_id="drun_" + "b" * 32,
        request_id="dreq_" + "c" * 32,
        collection_id="det_" + "d" * 32,
        binding_revision=1,
        inventory_id="inv_" + "1" * 32,
        inventory_digest="5" * 64,
        model_id="model-cnn",
        model_snapshot_id="mdl_" + "6" * 32,
        model_manifest_sha256="7" * 64,
        model_artifact_sha256="8" * 64,
        model_snapshot_digest="9" * 64,
        settings=DetectionSettings(0.5, 50, 125, 8),
        window_length_samples=4_000,
        hop_samples=2_000,
        model_sample_rate_hz=16_000,
        backend_distribution="bioacoustics-dl-toolbox",
        backend_version="0.2.0",
        backend_revision="e478ca5",
        completed_at="2026-10-29T12:00:00.000Z",
        recordings=(succeeded, zero, failed),
    )
    assert result.completeness is ResultCompleteness.PARTIAL
    assert result.successful_files == 2
    assert result.failed_files == 1
    assert result.candidate_count == 1
    by_key = {item.recording_key: item for item in result.recordings}
    assert by_key["recordings/zero.wav"].status is FileOutcomeStatus.SUCCEEDED
    assert by_key["recordings/zero.wav"].candidates == ()
    assert by_key["recordings/broken.wav"].status is FileOutcomeStatus.FAILED
    assert DetectionResult.from_dict(result.to_dict()) == result
    with pytest.raises(FrozenInstanceError):
        result.result_id = "pub_" + "0" * 32  # type: ignore[misc]

    changed = result.to_dict()
    changed["candidate_count"] = 999
    with pytest.raises(ValueError, match="count|digest"):
        DetectionResult.from_dict(changed)
    with pytest.raises(ValueError, match="failed recording"):
        replace(failed, candidates=(candidate,))
    with pytest.raises(ValueError, match="successful recording"):
        replace(zero, error_code="audio_decode_failed")
    with pytest.raises(ValueError, match="successful recording"):
        DetectionResult.create(
            result_id="pub_" + "e" * 32,
            run_id="drun_" + "f" * 32,
            request_id="dreq_" + "0" * 32,
            collection_id="det_" + "1" * 32,
            binding_revision=1,
            inventory_id="inv_" + "2" * 32,
            inventory_digest="3" * 64,
            model_id="model-cnn",
            model_snapshot_id="mdl_" + "4" * 32,
            model_manifest_sha256="5" * 64,
            model_artifact_sha256="6" * 64,
            model_snapshot_digest="7" * 64,
            settings=DetectionSettings(0.5, 0, 0, 8),
            window_length_samples=4_000,
            hop_samples=4_000,
            model_sample_rate_hz=16_000,
            backend_distribution="bioacoustics-dl-toolbox",
            backend_version="0.2.0",
            backend_revision="e478ca5",
            completed_at="2026-10-29T12:00:00.000Z",
            recordings=(failed,),
        )
