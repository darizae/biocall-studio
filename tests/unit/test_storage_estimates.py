"""REV-05 Qt-free output sizing and storage-admission contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from biocall_studio.detect.application.storage import (
    DetectionRecordingFacts,
    estimate_detection_metadata,
    estimate_refinement_metadata,
)
from biocall_studio.shared.storage import (
    MIB,
    ByteEstimate,
    CapacityObservation,
    EstimateConfidence,
    StorageDecision,
    StorageEstimate,
    StoragePreflightError,
    assess_storage,
    format_binary_size,
    pcm_wav_bytes,
    query_filesystem_capacity,
    require_storage_admission,
    storage_input_digest,
)
from biocall_studio.train.application.storage import estimate_model_artifacts


def _capacity(
    free_bytes: int | None,
    *,
    target: str = "Test volume",
    volume: str = "test-volume",
) -> CapacityObservation:
    return CapacityObservation(
        target_label=target,
        volume_id=volume,
        free_bytes=free_bytes,
        observed_at=datetime(2026, 11, 3, 8, 0, tzinfo=UTC),
        error="permission denied" if free_bytes is None else "",
    )


def test_pcm_wav_and_binary_display_arithmetic() -> None:
    """Case: UT-SIZE-001."""
    assert pcm_wav_bytes(8_000, channels=1, sample_width_bytes=2) == 16_044
    assert pcm_wav_bytes(8_000, channels=2, sample_width_bytes=3) == 48_044
    assert format_binary_size(0) == "0 KB"
    assert format_binary_size(1) == "1 KB"
    assert format_binary_size(1_024) == "1 KB"
    assert format_binary_size(1_025) == "1.1 KB"
    assert format_binary_size(10 * 1_024 + 1) == "11 KB"
    assert format_binary_size(1_024**2) == "1 MB"
    with pytest.raises(ValueError, match="frame count"):
        pcm_wav_bytes(-1, channels=1, sample_width_bytes=2)
    with pytest.raises(ValueError, match="channel"):
        pcm_wav_bytes(1, channels=0, sample_width_bytes=2)
    with pytest.raises(ValueError, match="sample width"):
        pcm_wav_bytes(1, channels=1, sample_width_bytes=8)
    with pytest.raises(OverflowError, match="supported byte range"):
        pcm_wav_bytes(2**63, channels=2, sample_width_bytes=4)


def test_workflow_model_ranges_are_bounded_without_fake_precision() -> None:
    """Case: UT-SIZE-002."""
    cnn = estimate_model_artifacts(
        family="cnn",
        effective_values={
            "encoder.resnet_size": 18,
            "training.max_epochs": 20,
        },
        snippet_count=40,
    )
    assert cnn.expected_final.kind == "range"
    assert cnn.expected_final.low_bytes < cnn.expected_final.high_bytes
    assert cnn.peak_bytes >= cnn.expected_final.high_bytes
    assert cnn.confidence is EstimateConfidence.ARITHMETIC
    assert "varies" in cnn.user_note.lower()

    rf = estimate_model_artifacts(
        family="rf",
        effective_values={"n_estimators": 100, "max_depth": 8},
        snippet_count=40,
    )
    assert rf.expected_final.kind == "range"
    assert rf.expected_final.high_bytes < cnn.expected_final.high_bytes

    unknown = estimate_model_artifacts(
        family="cnn",
        effective_values={},
        snippet_count=0,
    )
    assert unknown.expected_final.kind == "unavailable"
    assert unknown.peak_bytes is None
    assert unknown.confidence is EstimateConfidence.INSUFFICIENT_EVIDENCE

    detection, windows = estimate_detection_metadata(
        (DetectionRecordingFacts("rec_a", 8_000, 16_000),),
        model_sample_rate_hz=8_000,
        window_samples=4_000,
        hop_samples=2_000,
    )
    assert windows == 7
    assert detection.expected_final.kind == "range"
    assert detection.peak_bytes is not None
    assert "64 MB Result document limit" in detection.basis

    refinement = estimate_refinement_metadata(7)
    assert refinement.expected_final.kind == "range"
    assert refinement.expected_final.high_bytes < detection.expected_final.high_bytes


def test_per_volume_capacity_staleness_and_confirmation_rules() -> None:
    """Case: UT-SIZE-003."""
    digest = storage_input_digest({"operation": "dataset", "count": 2})
    expected = ByteEstimate.exact(100 * MIB)

    ready = assess_storage(
        operation="train.dataset_build",
        input_digest=digest,
        expected_final=expected,
        target_peaks={"Dataset folder": 100 * MIB},
        capacities={"Dataset folder": _capacity(2_000 * MIB, target="Dataset folder")},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="planned PCM frames and bounded metadata",
    )
    assert ready.decision is StorageDecision.READY
    assert ready.reserve_bytes == 512 * MIB
    assert StorageEstimate.from_dict(ready.to_dict()) == ready
    require_storage_admission(ready)

    tight = assess_storage(
        operation="train.dataset_build",
        input_digest=digest,
        expected_final=expected,
        target_peaks={"Dataset folder": 100 * MIB},
        capacities={"Dataset folder": _capacity(700 * MIB, target="Dataset folder")},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="planned PCM frames and bounded metadata",
    )
    assert tight.decision is StorageDecision.TIGHT
    with pytest.raises(StoragePreflightError, match="confirmation"):
        require_storage_admission(tight)
    require_storage_admission(tight, confirmed=True)

    insufficient = assess_storage(
        operation="train.dataset_build",
        input_digest=digest,
        expected_final=expected,
        target_peaks={"Dataset folder": 100 * MIB},
        capacities={"Dataset folder": _capacity(600 * MIB, target="Dataset folder")},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="planned PCM frames and bounded metadata",
    )
    assert insufficient.decision is StorageDecision.INSUFFICIENT
    with pytest.raises(StoragePreflightError, match="Not enough free space"):
        require_storage_admission(insufficient, confirmed=True)

    unknown = assess_storage(
        operation="detect.export",
        input_digest=digest,
        expected_final=expected,
        target_peaks={"Export folder": 100 * MIB},
        capacities={"Export folder": _capacity(None, target="Export folder")},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="frozen export frames",
    )
    assert unknown.decision is StorageDecision.UNKNOWN
    assert unknown.requires_confirmation

    stale = assess_storage(
        operation="detect.export",
        input_digest=digest,
        expected_input_digest="0" * 64,
        expected_final=expected,
        target_peaks={"Export folder": 100 * MIB},
        capacities={"Export folder": _capacity(2_000 * MIB, target="Export folder")},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="frozen export frames",
    )
    assert stale.decision is StorageDecision.STALE

    split_volumes = assess_storage(
        operation="multi.volume",
        input_digest=digest,
        expected_final=ByteEstimate.range(100 * MIB, 200 * MIB),
        target_peaks={"A": 20 * MIB, "B": 20 * MIB},
        capacities={
            "A": _capacity(2_000 * MIB, target="A", volume="volume-a"),
            "B": _capacity(20 * MIB, target="B", volume="volume-b"),
        },
        confidence=EstimateConfidence.ARITHMETIC,
        basis="separate destinations",
    )
    assert split_volumes.decision is StorageDecision.INSUFFICIENT

    same_volume = assess_storage(
        operation="same.volume",
        input_digest=digest,
        expected_final=ByteEstimate.range(200 * MIB, 400 * MIB),
        target_peaks={"A": 200 * MIB, "B": 200 * MIB},
        capacities={
            "A": _capacity(800 * MIB, target="A"),
            "B": _capacity(800 * MIB, target="B"),
        },
        confidence=EstimateConfidence.ARITHMETIC,
        basis="two destinations on one filesystem",
    )
    assert same_volume.decision is StorageDecision.INSUFFICIENT
    assert len(same_volume.volumes) == 1
    assert same_volume.peak_bytes == 400 * MIB


def test_capacity_adapter_uses_existing_ancestor_without_serializing_paths(tmp_path) -> None:
    """Case: UT-SIZE-003."""
    destination = tmp_path / "not-created" / "export"
    observation = query_filesystem_capacity(destination, "Export folder")
    assert observation.free_bytes is not None
    assert observation.volume_id.startswith("device-")

    digest = storage_input_digest({"operation": "export"})
    estimate = assess_storage(
        operation="detect.export",
        input_digest=digest,
        expected_final=ByteEstimate.exact(1),
        target_peaks={"Export folder": 1},
        capacities={"Export folder": observation},
        confidence=EstimateConfidence.ARITHMETIC,
        basis="one byte test output",
    )
    assert str(tmp_path) not in json.dumps(estimate.to_dict())

    unknown = query_filesystem_capacity(tmp_path.relative_to(tmp_path), "Relative folder")
    assert unknown.free_bytes is None
    assert unknown.error == "ValueError"
