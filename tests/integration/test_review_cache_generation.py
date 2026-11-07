from __future__ import annotations

import errno
import hashlib
import math
import os
import threading
import time
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from biocall_studio.review.application.generation import (
    GenerationCancelled,
    GenerationJob,
    GenerationToken,
    SpectrogramGenerationSupervisor,
)
from biocall_studio.review.application.storage import (
    CacheSizeCalibration,
    assess_review_cache_storage,
    plan_review_cache_generation,
)
from biocall_studio.review.domain.cache import CachePriority
from biocall_studio.review.domain.intake import EligibleCandidate
from biocall_studio.review.domain.spectrograms import (
    SPECTROGRAM_RENDER_VERSION,
    Palette,
    SpectrogramImageTier,
    SpectrogramSettings,
)
from biocall_studio.review.persistence.cache import SpectrogramCache
from biocall_studio.review.workflows.audio import (
    AudioSourceError,
    SourceIdentityCache,
    read_candidate_audio,
)
from biocall_studio.review.workflows.spectrograms import (
    SpectrogramRenderRequest,
    render_spectrogram,
    spectrogram_content_key,
)
from biocall_studio.shared.storage import (
    CapacityObservation,
    StoragePreflightError,
)

pytestmark = pytest.mark.integration


def _write_wav(path: Path, *, rate: int = 8_000, frames: int = 24_000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for frame in range(frames):
        value = round(12_000 * math.sin(2 * math.pi * 700 * frame / rate))
        payload.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(payload)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(source_root: Path, source: Path, *, token: str = "1") -> EligibleCandidate:
    return EligibleCandidate(
        ordinal=0,
        recording_ordinal=0,
        candidate_id="cand_" + token * 32,
        recording_ref="rec_" + "2" * 32,
        recording_key=source.relative_to(source_root).as_posix(),
        source_sha256=_sha256(source),
        sample_rate_hz=8_000,
        frame_count=24_000,
        channels=1,
        start_frame=8_000,
        end_frame=8_800,
        start_time_ns=1_000_000_000,
        end_time_ns=1_100_000_000,
        cnn_target_score=0.9,
        rf_target_score=None,
        contributing_windows=1,
    )


def _request(source_root: Path, candidate: EligibleCandidate) -> tuple[object, object]:
    audio = read_candidate_audio(source_root, candidate, context_seconds=1)
    request = SpectrogramRenderRequest(
        candidate_id=candidate.candidate_id,
        source_sha256=candidate.source_sha256,
        context=audio.context,
        settings=SpectrogramSettings(frequency_max_hz=3_000, exact_window_ms=20),
        tier=SpectrogramImageTier.THUMBNAIL,
    )
    return audio, request


def _ready_assessment(tmp_path: Path, *, settings_digest: str):
    calibration = CacheSizeCalibration(
        calibration_version="generated-integration-v1",
        render_version=SPECTROGRAM_RENDER_VERSION,
        tier=SpectrogramImageTier.THUMBNAIL,
        sample_count=100,
        encoded_low_bytes=1,
        encoded_high_bytes=2_000_000,
        metadata_high_bytes=64_000,
        staging_high_bytes=2_000_000,
        milliseconds_low=None,
        milliseconds_high=None,
    )
    plan = plan_review_cache_generation(
        missing_count=1,
        existing_file_sizes=(),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest=settings_digest,
        calibration=calibration,
    )
    return assess_review_cache_storage(
        plan,
        capacity=CapacityObservation(
            target_label="Spectrogram cache",
            volume_id="test-cache-volume",
            free_bytes=2_000_000_000,
            observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        ),
    )


def test_async_generation_reuse_stale_epoch_cancel_retry_and_50k_bound(tmp_path) -> None:
    """Case: IT-REVW-006."""
    source_root = tmp_path / "source"
    source = _write_wav(source_root / "recordings" / "call.wav")
    source_before = _sha256(source)
    labels = tmp_path / "sessions.sqlite3"
    labels.write_bytes(b"committed labels")
    labels_before = _sha256(labels)
    result_file = tmp_path / "detect-result.json"
    result_file.write_bytes(b"immutable Detect Result")
    result_before = _sha256(result_file)

    candidate = _candidate(source_root, source)
    audio, request = _request(source_root, candidate)
    settings_digest = "4" * 64
    epochs = {"session-a": 1, "session-b": 1}
    cache = SpectrogramCache(
        tmp_path / "app" / "review" / "v1" / "spectrograms",
        limit_bytes=20_000_000,
    )
    supervisor = SpectrogramGenerationSupervisor(
        cache,
        token_is_current=lambda token: epochs.get(token.session_id) == token.settings_epoch,
        max_workers=1,
        max_pending=8,
    )
    renders = 0

    def generate(_prepared, cancelled):
        nonlocal renders
        if cancelled():
            raise GenerationCancelled("cancelled")
        renders += 1
        return render_spectrogram(audio.samples, request)

    key = spectrogram_content_key(request)
    token_a = GenerationToken("session-a", 1, settings_digest, candidate.source_sha256)
    job = GenerationJob(
        content_key=key,
        tier=SpectrogramImageTier.THUMBNAIL,
        priority=CachePriority.VISIBLE_THUMBNAIL,
        token=token_a,
        render=generate,
    )
    ready = _ready_assessment(tmp_path, settings_digest=settings_digest)
    first_batch = supervisor.submit_bulk(iter((job,)), storage_estimate=ready)
    first = supervisor.wait(first_batch, timeout=10)
    assert first.completed == 1 and first.failed == first.cancelled == 0
    assert supervisor._batches[first_batch].states == {}
    assert supervisor._batches[first_batch].iterator is None
    entry = cache.lookup(key)
    assert entry is not None and entry.source_sha256 == candidate.source_sha256
    assert entry.size_bytes <= ready.expected_final.high_bytes
    assert renders == 1

    # A different preset snapshot digest with identical effective render inputs
    # reuses the global content-addressed object.
    token_b = GenerationToken("session-b", 1, "6" * 64, candidate.source_sha256)
    reused = supervisor.submit(
        GenerationJob(
            content_key=key,
            tier=SpectrogramImageTier.THUMBNAIL,
            priority=CachePriority.CURRENT_DETAIL,
            token=token_b,
            render=generate,
        ),
        storage_estimate=ready,
    )
    reused_progress = supervisor.wait(reused, timeout=5)
    assert reused_progress.cache_hits == 1
    assert supervisor._batches[reused].states == {}
    assert renders == 1

    cleared = cache.clear((key,))
    assert cleared.deleted_keys == (key,)
    regenerated = supervisor.submit(
        GenerationJob(
            content_key=key,
            tier=SpectrogramImageTier.THUMBNAIL,
            priority=CachePriority.VISIBLE_THUMBNAIL,
            token=token_b,
            render=generate,
        ),
        storage_estimate=ready,
    )
    assert supervisor.wait(regenerated, timeout=10).completed == 1
    assert renders == 2 and cache.lookup(key) is not None

    release = threading.Event()
    stale_request = SpectrogramRenderRequest(
        candidate_id=request.candidate_id,
        source_sha256=request.source_sha256,
        context=request.context,
        settings=SpectrogramSettings(
            frequency_max_hz=3_000,
            exact_window_ms=20,
            contrast_db=40,
        ),
        tier=SpectrogramImageTier.THUMBNAIL,
    )

    def stale_render(_prepared, cancelled):
        release.wait(5)
        return render_spectrogram(audio.samples, stale_request)

    stale_job = GenerationJob(
        content_key=spectrogram_content_key(stale_request),
        tier=SpectrogramImageTier.THUMBNAIL,
        priority=CachePriority.VISIBLE_THUMBNAIL,
        token=token_a,
        render=stale_render,
    )
    stale_batch = supervisor.submit(stale_job, storage_estimate=ready)
    epochs["session-a"] = 2
    release.set()
    stale_progress = supervisor.wait(stale_batch, timeout=10)
    assert stale_progress.failed == 1
    assert supervisor._batches[stale_batch].states == {}
    assert cache.lookup(stale_job.content_key) is None

    started = threading.Event()

    def cancellable(_prepared, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.005)
        raise GenerationCancelled("cancelled")

    cancel_request = SpectrogramRenderRequest(
        candidate_id=request.candidate_id,
        source_sha256=request.source_sha256,
        context=request.context,
        settings=SpectrogramSettings(
            frequency_max_hz=3_000,
            exact_window_ms=20,
            contrast_db=65,
        ),
        tier=SpectrogramImageTier.THUMBNAIL,
    )
    cancel_job = GenerationJob(
        content_key=spectrogram_content_key(cancel_request),
        tier=SpectrogramImageTier.THUMBNAIL,
        priority=CachePriority.NEARBY_PREFETCH,
        token=GenerationToken("session-a", 2, settings_digest, candidate.source_sha256),
        render=cancellable,
    )
    cancel_batch = supervisor.submit(cancel_job, storage_estimate=ready)
    assert started.wait(5)
    supervisor.cancel(cancel_batch)
    cancelled_progress = supervisor.wait(cancel_batch, timeout=5)
    assert cancelled_progress.cancelled == 1
    assert supervisor._batches[cancel_batch].states == {}
    assert cache.lookup(cancel_job.content_key) is None

    clear_started = threading.Event()
    clear_release = threading.Event()
    clear_request = SpectrogramRenderRequest(
        candidate_id=request.candidate_id,
        source_sha256=request.source_sha256,
        context=request.context,
        settings=SpectrogramSettings(
            frequency_max_hz=3_000,
            exact_window_ms=20,
            palette=Palette.VIRIDIS,
        ),
        tier=SpectrogramImageTier.THUMBNAIL,
    )

    def late_after_clear(_prepared, cancelled):
        clear_started.set()
        clear_release.wait(5)
        return render_spectrogram(audio.samples, clear_request)

    clear_job = GenerationJob(
        content_key=spectrogram_content_key(clear_request),
        tier=SpectrogramImageTier.THUMBNAIL,
        priority=CachePriority.VISIBLE_THUMBNAIL,
        token=token_b,
        render=late_after_clear,
    )
    clear_batch = supervisor.submit(clear_job, storage_estimate=ready)
    assert clear_started.wait(5)
    supervisor.clear_cache((clear_job.content_key,))
    clear_release.set()
    clear_progress = supervisor.wait(clear_batch, timeout=10)
    assert clear_progress.failed == 1
    assert supervisor._batches[clear_batch].states == {}
    assert cache.lookup(clear_job.content_key) is None

    produced = 0
    bulk_release = threading.Event()

    def many_jobs():
        nonlocal produced
        for index in range(50_000):
            produced += 1
            generated_key = "spec_" + hashlib.sha256(f"bulk-{index}".encode()).hexdigest()
            yield GenerationJob(
                content_key=generated_key,
                tier=SpectrogramImageTier.THUMBNAIL,
                priority=CachePriority.GENERATE_ALL,
                token=token_b,
                render=lambda _prepared, cancelled: (
                    bulk_release.wait(5),
                    (_ for _ in ()).throw(GenerationCancelled("cancelled")),
                )[1],
            )

    large_batch = supervisor.submit_bulk(many_jobs(), storage_estimate=ready)
    deadline = time.monotonic() + 5
    while supervisor.active_count == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert produced <= supervisor.max_pending + supervisor.max_workers
    assert supervisor.pending_count <= supervisor.max_pending
    supervisor.cancel(large_batch)
    bulk_release.set()
    large_progress = supervisor.wait(large_batch, timeout=5)
    assert large_progress.done
    assert supervisor._batches[large_batch].states == {}
    assert supervisor._batches[large_batch].iterator is None
    supervisor.shutdown(wait=True)

    assert _sha256(source) == source_before
    assert _sha256(labels) == labels_before
    assert _sha256(result_file) == result_before


def test_preflight_disk_failure_corruption_and_interrupted_staging_recover(
    tmp_path, monkeypatch
) -> None:
    """Case: IT-REVW-006."""
    cache = SpectrogramCache(tmp_path / "cache", limit_bytes=20_000_000)
    source_root = tmp_path / "source"
    source = _write_wav(source_root / "recordings" / "call.wav")
    candidate = _candidate(source_root, source)
    original_source = source.read_bytes()
    identities = SourceIdentityCache(max_entries=2)
    read_candidate_audio(source_root, candidate, context_seconds=1, identity_cache=identities)
    read_candidate_audio(source_root, candidate, context_seconds=1, identity_cache=identities)
    assert identities.entry_count == 1
    source.write_bytes(original_source[:-2] + b"\0\0")
    with pytest.raises(AudioSourceError, match="frozen Detect source"):
        read_candidate_audio(source_root, candidate, context_seconds=1, identity_cache=identities)
    source.write_bytes(original_source)
    audio, request = _request(source_root, candidate)
    raster = render_spectrogram(audio.samples, request)
    settings_digest = "5" * 64

    plan = plan_review_cache_generation(
        missing_count=1,
        existing_file_sizes=(),
        tier=SpectrogramImageTier.THUMBNAIL,
        settings_digest=settings_digest,
        calibration=CacheSizeCalibration(
            calibration_version="generated-integration-v1",
            render_version=SPECTROGRAM_RENDER_VERSION,
            tier=SpectrogramImageTier.THUMBNAIL,
            sample_count=100,
            encoded_low_bytes=1,
            encoded_high_bytes=2_000_000,
            metadata_high_bytes=64_000,
            staging_high_bytes=2_000_000,
            milliseconds_low=None,
            milliseconds_high=None,
        ),
    )
    insufficient = assess_review_cache_storage(
        plan,
        capacity=CapacityObservation(
            target_label="Spectrogram cache",
            volume_id="test-cache-volume",
            free_bytes=1,
            observed_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        ),
    )
    consumed = False

    def jobs():
        nonlocal consumed
        consumed = True
        yield None

    supervisor = SpectrogramGenerationSupervisor(cache, token_is_current=lambda token: True)
    with pytest.raises(StoragePreflightError, match="Not enough free space"):
        supervisor.submit_bulk(jobs(), storage_estimate=insufficient)
    assert not consumed and supervisor.active_count == 0

    real_replace = os.replace

    def disk_full(source_path, target_path):
        raise OSError(errno.ENOSPC, "injected disk full")

    monkeypatch.setattr(os, "replace", disk_full)
    with pytest.raises(OSError) as full:
        cache.publish(raster, settings_digest=settings_digest)
    assert full.value.errno == errno.ENOSPC
    assert cache.lookup(raster.content_key) is None
    assert tuple(cache.staging_root.iterdir()) == ()
    monkeypatch.setattr(os, "replace", real_replace)

    entry = cache.publish(raster, settings_digest=settings_digest)
    real_unlink = Path.unlink

    def permission_denied(path, *args, **kwargs):
        if path == entry.path:
            raise PermissionError(errno.EACCES, "injected permission failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", permission_denied)
    denied = cache.clear((raster.content_key,))
    assert denied.failed_keys == (raster.content_key,)
    assert cache.lookup(raster.content_key) is not None
    monkeypatch.setattr(Path, "unlink", real_unlink)

    entry.path.write_bytes(b"corrupt image")
    assert cache.lookup(raster.content_key) is None

    interrupted = cache.staging_root / f"{raster.content_key}.interrupted.part"
    interrupted.write_bytes(b"private incomplete bytes")
    repaired = SpectrogramCache(cache.root, limit_bytes=20_000_000)
    reconciliation = repaired.reconcile(max_entries=100)
    assert interrupted.name in reconciliation.removed_staging_names
    assert not interrupted.exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    attacked = repaired.objects_root / raster.content_key[5:7]
    if attacked.exists():
        attacked.rmdir()
    attacked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link|unsafe"):
        repaired.publish(raster, settings_digest=settings_digest)
    assert tuple(outside.iterdir()) == ()
    supervisor.shutdown(wait=True)
