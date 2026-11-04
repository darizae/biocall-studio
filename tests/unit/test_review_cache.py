from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest

from biocall_studio.review.application.cache import change_session_settings_with_preflight
from biocall_studio.review.application.controller import ReviewSessionController
from biocall_studio.review.application.generation import SpectrogramGenerationSupervisor
from biocall_studio.review.application.storage import (
    CacheSizeCalibration,
    assess_review_cache_storage,
    measured_cache_limit,
    plan_review_cache_generation,
)
from biocall_studio.review.domain.cache import (
    CachePriority,
    CacheQueueRequest,
    GenerationQueue,
)
from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.sessions import DEFAULT_PRESET_ID, SpectrogramSettingsSnapshot
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_ALGORITHM_VERSION,
    SPECTROGRAM_RENDER_VERSION,
    SpectrogramImageTier,
    SpectrogramSettings,
    plan_candidate_context,
)
from biocall_studio.review.persistence.cache import SpectrogramCache
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    render_spectrogram,
)
from biocall_studio.shared.storage import (
    MAX_ESTIMATE_BYTES,
    CapacityObservation,
    EstimateKind,
    StorageDecision,
    StoragePreflightError,
    require_storage_admission,
)


def _key(index: int) -> str:
    return "spec_" + hashlib.sha256(str(index).encode()).hexdigest()


def _raster(*, tier: SpectrogramImageTier = SpectrogramImageTier.THUMBNAIL):
    candidate = EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + "1" * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key="recordings/source.wav",
        source_sha256="3" * 64,
        sample_rate_hz=1_000,
        frame_count=2_000,
        channels=1,
        start_frame=900,
        end_frame=1_100,
        start_time_ns=900_000_000,
        end_time_ns=1_100_000_000,
        cnn_target_score=0.9,
        rf_target_score=None,
        contributing_windows=1,
    )
    context = plan_candidate_context(candidate, context_seconds=1)
    request = SpectrogramRenderRequest(
        candidate_id=candidate.candidate_id,
        source_sha256=candidate.source_sha256,
        context=context,
        settings=SpectrogramSettings(
            frequency_max_hz=3_000,
            exact_window_ms=20,
        ),
        tier=tier,
    )
    samples = np.sin(np.arange(context.frame_count) * 2 * np.pi * 80 / 1_000)[None, :]
    return render_spectrogram(samples, request)


def test_generation_queue_is_bounded_prioritized_and_deduplicated() -> None:
    """Case: UT-REVW-007."""
    queue = GenerationQueue(max_pending=3)
    first = queue.offer(CacheQueueRequest(_key(1), CachePriority.NEARBY_PREFETCH))
    queue.offer(CacheQueueRequest(_key(2), CachePriority.GENERATE_ALL))
    queue.offer(CacheQueueRequest(_key(3), CachePriority.NEARBY_PREFETCH))
    assert first.accepted and queue.pending_count == 3

    duplicate = queue.offer(CacheQueueRequest(_key(1), CachePriority.VISIBLE_THUMBNAIL))
    assert duplicate.deduplicated
    assert queue.pending_count == 3
    assert queue.pop().content_key == _key(1)

    queue.offer(CacheQueueRequest(_key(4), CachePriority.VISIBLE_THUMBNAIL))
    offered = queue.offer(CacheQueueRequest(_key(5), CachePriority.CURRENT_DETAIL))
    assert offered.accepted
    assert offered.dropped_keys == (_key(2),)
    assert queue.pending_count == 3
    assert queue.pop().content_key == _key(4)
    assert queue.pop().content_key == _key(5)

    queue.offer(CacheQueueRequest(_key(6), CachePriority.NEARBY_PREFETCH))
    queue.offer(CacheQueueRequest(_key(7), CachePriority.GENERATE_ALL))
    dropped = queue.drop_prefetch_except({_key(6)})
    assert _key(3) in dropped
    assert _key(6) not in dropped
    assert queue.pending_count <= 3


def test_cache_publish_lookup_lru_clear_and_containment(tmp_path) -> None:
    """Case: UT-REVW-007."""
    cache = SpectrogramCache(
        tmp_path / "review" / "v1" / "spectrograms", limit_bytes=20_000_000
    )
    raster = _raster()
    entry = cache.publish(raster, settings_digest="4" * 64)
    assert entry.content_key == raster.content_key
    assert entry.size_bytes > 0
    assert cache.lookup(raster.content_key) == entry
    assert cache.actual_bytes == entry.size_bytes

    source = tmp_path / "source.wav"
    labels = tmp_path / "sessions.sqlite3"
    source.write_bytes(b"source")
    labels.write_bytes(b"labels")
    protected = cache.clear((raster.content_key,), protected_keys={raster.content_key})
    assert protected.deleted_keys == ()
    assert protected.protected_keys == (raster.content_key,)
    assert source.read_bytes() == b"source"
    assert labels.read_bytes() == b"labels"

    cleared = cache.clear((raster.content_key,))
    assert cleared.deleted_keys == (raster.content_key,)
    assert cache.lookup(raster.content_key) is None
    assert source.read_bytes() == b"source"
    assert labels.read_bytes() == b"labels"

    first = cache.publish(_raster(), settings_digest="4" * 64)
    detail = cache.publish(_raster(tier=SpectrogramImageTier.DETAIL), settings_digest="4" * 64)
    cache.set_automatic_pins({detail.content_key})
    evicted = cache.evict_to_limit(first.size_bytes)
    assert first.content_key in evicted.deleted_keys
    assert cache.lookup(detail.content_key) is not None
    assert cache.clear((detail.content_key,)).deleted_keys == (detail.content_key,)

    outside = tmp_path / "outside"
    outside.mkdir()
    shard = cache.objects_root / "ff"
    shard.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link|unsafe"):
        cache.object_path("spec_ff" + "0" * 62, create_parent=True)
    assert tuple(outside.iterdir()) == ()


def test_review_storage_adapter_uses_measured_incremental_bytes_and_rev05() -> None:
    """Case: UT-REVW-008."""
    calibration = CacheSizeCalibration(
        calibration_version="generated-fixture-v1",
        render_version=SPECTROGRAM_RENDER_VERSION,
        tier=SpectrogramImageTier.THUMBNAIL,
        sample_count=100,
        encoded_low_bytes=10_000,
        encoded_high_bytes=20_000,
        metadata_high_bytes=1_000,
        staging_high_bytes=20_000,
        milliseconds_low=None,
        milliseconds_high=None,
    )
    plan = plan_review_cache_generation(
        missing_count=10,
        existing_file_sizes=(7_000, 8_000),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest="5" * 64,
        calibration=calibration,
    )
    assert plan.existing_cache_bytes == 15_000
    assert plan.size_plan.expected_final.kind is EstimateKind.RANGE
    assert plan.size_plan.expected_final.low_bytes == 110_000
    assert plan.size_plan.expected_final.high_bytes == 210_000
    assert plan.size_plan.peak_bytes == 230_000
    assert plan.time_estimate.kind is EstimateKind.UNAVAILABLE
    assert measured_cache_limit(calibration, item_capacity=100) == 2_120_000

    capacity = CapacityObservation(
        target_label="Spectrogram cache",
        volume_id="cache-volume",
        free_bytes=2_000_000_000,
        observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
    )
    estimate = assess_review_cache_storage(plan, capacity=capacity)
    assert estimate.decision is StorageDecision.READY
    assert estimate.expected_final == plan.size_plan.expected_final
    assert estimate.input_digest == plan.input_digest

    tight = assess_review_cache_storage(
        plan,
        capacity=CapacityObservation(
            target_label="Spectrogram cache",
            volume_id="cache-volume",
            free_bytes=700_000_000,
            observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        ),
    )
    assert tight.decision is StorageDecision.TIGHT
    with pytest.raises(StoragePreflightError, match="confirmation"):
        require_storage_admission(tight)

    insufficient = assess_review_cache_storage(
        plan,
        capacity=CapacityObservation(
            target_label="Spectrogram cache",
            volume_id="cache-volume",
            free_bytes=100,
            observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        ),
    )
    assert insufficient.decision is StorageDecision.INSUFFICIENT

    unavailable_capacity = assess_review_cache_storage(
        plan,
        capacity=CapacityObservation(
            target_label="Spectrogram cache",
            volume_id="unknown-volume",
            free_bytes=None,
            observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
            error="PermissionError",
        ),
    )
    assert unavailable_capacity.decision is StorageDecision.UNKNOWN

    all_hits = plan_review_cache_generation(
        missing_count=0,
        existing_file_sizes=(7_000, 8_000),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest="5" * 64,
        calibration=None,
    )
    assert all_hits.size_plan.expected_final.low_bytes == 0
    assert all_hits.size_plan.peak_bytes == 0

    unknown = plan_review_cache_generation(
        missing_count=10,
        existing_file_sizes=(),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest="5" * 64,
        calibration=None,
    )
    assert unknown.size_plan.expected_final.kind is EstimateKind.UNAVAILABLE
    assert (
        assess_review_cache_storage(unknown, capacity=capacity).decision
        is StorageDecision.UNKNOWN
    )

    stale = assess_review_cache_storage(
        plan,
        capacity=capacity,
        expected_input_digest="0" * 64,
    )
    assert stale.decision is StorageDecision.STALE

    with pytest.raises(OverflowError, match="supported byte range"):
        plan_review_cache_generation(
            missing_count=MAX_ESTIMATE_BYTES,
            existing_file_sizes=(),
            tier=SpectrogramImageTier.THUMBNAIL,
            settings_digest="5" * 64,
            calibration=calibration,
        )


def test_settings_change_rechecks_preflight_before_advancing_epoch(tmp_path, monkeypatch) -> None:
    """Case: UT-REVW-008."""
    settings = SpectrogramSettingsSnapshot.create(
        preset_id=DEFAULT_PRESET_ID,
        preset_name="Default",
        preset_revision=1,
        algorithm_version=SPECTROGRAM_ALGORITHM_VERSION,
        render_version=SPECTROGRAM_RENDER_VERSION,
        effective_settings=SpectrogramSettings().to_mapping(),
    )
    calibration = CacheSizeCalibration(
        calibration_version="generated-fixture-v1",
        render_version=SPECTROGRAM_RENDER_VERSION,
        tier=SpectrogramImageTier.THUMBNAIL,
        sample_count=100,
        encoded_low_bytes=1_000,
        encoded_high_bytes=2_000,
        metadata_high_bytes=500,
        staging_high_bytes=2_000,
        milliseconds_low=None,
        milliseconds_high=None,
    )
    plan = plan_review_cache_generation(
        missing_count=1,
        existing_file_sizes=(),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest=settings.settings_digest,
        calibration=calibration,
    )
    controller = ReviewSessionController(tmp_path / "suite")
    cache = SpectrogramCache(
        tmp_path / "suite" / "review" / "v1" / "spectrograms",
        limit_bytes=20_000_000,
    )
    supervisor = SpectrogramGenerationSupervisor(
        cache,
        token_is_current=lambda token: True,
        max_workers=1,
        max_pending=2,
    )
    calls: list[object] = []
    sentinel = object()

    def change_settings(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    invalidated: list[tuple[str, int]] = []
    monkeypatch.setattr(controller, "change_settings", change_settings)
    monkeypatch.setattr(
        supervisor,
        "invalidate_session_epoch",
        lambda session_id, epoch: invalidated.append((session_id, epoch)),
    )
    insufficient = CapacityObservation(
        target_label="Spectrogram cache",
        volume_id="cache-volume",
        free_bytes=1,
        observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
    )
    try:
        with pytest.raises(StoragePreflightError, match="Not enough free space"):
            change_session_settings_with_preflight(
                controller,
                supervisor,
                "rsn_" + "1" * 32,
                settings,
                plan,
                expected_revision=3,
                expected_settings_epoch=1,
                changed_at="2026-11-04T12:00:00Z",
                confirmed_change=True,
                capacity=insufficient,
            )
        assert calls == [] and invalidated == []

        result = change_session_settings_with_preflight(
            controller,
            supervisor,
            "rsn_" + "1" * 32,
            settings,
            plan,
            expected_revision=3,
            expected_settings_epoch=1,
            changed_at="2026-11-04T12:00:00Z",
            confirmed_change=True,
            capacity=CapacityObservation(
                target_label="Spectrogram cache",
                volume_id="cache-volume",
                free_bytes=2_000_000_000,
                observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
            ),
        )
        assert result.session is sentinel
        assert len(calls) == 1
        assert invalidated == [("rsn_" + "1" * 32, 1)]
    finally:
        supervisor.shutdown(wait=True)
        controller.shutdown()
