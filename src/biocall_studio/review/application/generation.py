"""Bounded asynchronous supervision for Review spectrogram cache generation."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from biocall_studio.review.domain.cache import (
    CachePriority,
    CacheQueueRequest,
    GenerationQueue,
)
from biocall_studio.review.domain.spectrograms import (
    SpectrogramImageTier,
    SpectrogramRaster,
    validate_spectrogram_content_key,
)
from biocall_studio.review.persistence.cache import CacheMutation, SpectrogramCache
from biocall_studio.shared.storage import StorageEstimate, require_storage_admission

_MAX_BATCH_HISTORY = 256
_MAX_DEDUP_SUBSCRIBERS = 4_096


class GenerationCancelled(InterruptedError):
    """A supervised cache job observed cancellation before valid completion."""


@dataclass(frozen=True, slots=True)
class GenerationToken:
    session_id: str
    settings_epoch: int
    settings_digest: str
    source_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session_id, str)
            or not self.session_id
            or len(self.session_id) > 120
            or type(self.settings_epoch) is not int
            or self.settings_epoch < 1
        ):
            raise ValueError("Spectrogram generation session token is invalid.")
        for value, label in (
            (self.settings_digest, "settings"),
            (self.source_sha256, "source"),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"Spectrogram generation {label} digest is invalid.")


@dataclass(frozen=True, slots=True)
class GenerationJob:
    content_key: str
    tier: SpectrogramImageTier
    priority: CachePriority
    token: GenerationToken
    render: Callable[[Callable[[], bool]], SpectrogramRaster]

    def __post_init__(self) -> None:
        validate_spectrogram_content_key(self.content_key)
        if not isinstance(self.tier, SpectrogramImageTier):
            raise ValueError("Spectrogram generation tier is invalid.")
        if not isinstance(self.priority, CachePriority):
            raise ValueError("Spectrogram generation priority is invalid.")
        if not isinstance(self.token, GenerationToken) or not callable(self.render):
            raise ValueError("Spectrogram generation job is invalid.")


@dataclass(frozen=True, slots=True)
class GenerationProgress:
    batch_id: str
    requested: int
    completed: int
    failed: int
    cancelled: int
    cache_hits: int
    pending: int
    active: int
    done: bool


@dataclass(slots=True)
class _Batch:
    batch_id: str
    iterator: Iterator[GenerationJob] | None
    exhausted: bool
    thumbnail_only: bool
    cancelled_by_user: bool = False
    requested: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    cache_hits: int = 0
    states: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _WorkItem:
    job: GenerationJob
    subscribers: dict[str, GenerationToken]
    all_tokens: list[GenerationToken]
    cache_epoch: int
    cancel_event: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True, slots=True)
class _WorkResult:
    outcome: str
    current_tokens: tuple[GenerationToken, ...]


class SpectrogramGenerationSupervisor:
    """Keep CPU work off the UI thread while bounding queue, buffers, and handles."""

    def __init__(
        self,
        cache: SpectrogramCache,
        *,
        token_is_current: Callable[[GenerationToken], bool],
        max_workers: int = 2,
        max_pending: int = 64,
    ):
        if not isinstance(cache, SpectrogramCache) or not callable(token_is_current):
            raise ValueError("Spectrogram generation supervisor dependencies are invalid.")
        if type(max_workers) is not int or not 1 <= max_workers <= 4:
            raise ValueError("Spectrogram worker count must be from one to four.")
        self.cache = cache
        self.token_is_current = token_is_current
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._queue = GenerationQueue(max_pending=max_pending)
        self._condition = threading.Condition(threading.RLock())
        self._items: dict[str, _WorkItem] = {}
        self._active: dict[str, tuple[Future[_WorkResult], _WorkItem]] = {}
        self._batches: dict[str, _Batch] = {}
        self._shutdown = False
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="biocall-review-spectrogram",
        )
        self._dispatcher = threading.Thread(
            target=self._dispatch,
            name="biocall-review-cache-supervisor",
            daemon=True,
        )
        self._dispatcher.start()

    @property
    def pending_count(self) -> int:
        return self._queue.pending_count

    @property
    def active_count(self) -> int:
        with self._condition:
            return len(self._active)

    def _new_batch(
        self,
        iterator: Iterator[GenerationJob] | None,
        *,
        thumbnail_only: bool,
    ) -> _Batch:
        if len(self._batches) >= _MAX_BATCH_HISTORY:
            for old_batch_id, old_batch in tuple(self._batches.items()):
                if self._is_done(old_batch):
                    del self._batches[old_batch_id]
                if len(self._batches) < _MAX_BATCH_HISTORY:
                    break
        if len(self._batches) >= _MAX_BATCH_HISTORY:
            raise RuntimeError("Too many spectrogram generation batches are still active.")
        batch_id = f"rgb_{uuid.uuid4().hex}"
        batch = _Batch(
            batch_id=batch_id,
            iterator=iterator,
            exhausted=iterator is None,
            thumbnail_only=thumbnail_only,
        )
        self._batches[batch_id] = batch
        return batch

    def _drop_item_locked(self, content_key: str) -> None:
        item = self._items.pop(content_key, None)
        if item is None:
            return
        for batch_id in tuple(item.subscribers):
            batch = self._batches.get(batch_id)
            if batch is not None and batch.states.get(content_key) == "pending":
                batch.states[content_key] = "cancelled"
                batch.cancelled += 1

    def _enqueue_locked(self, batch: _Batch, job: GenerationJob) -> bool:
        if job.content_key in batch.states:
            return True
        batch.requested += 1
        existing = self._items.get(job.content_key)
        if existing is not None:
            if existing.job.tier is not job.tier:
                batch.states[job.content_key] = "failed"
                batch.failed += 1
                return True
            if len(existing.subscribers) >= _MAX_DEDUP_SUBSCRIBERS:
                batch.states[job.content_key] = "failed"
                batch.failed += 1
                return True
            existing.subscribers[batch.batch_id] = job.token
            if job.token not in existing.all_tokens:
                existing.all_tokens.append(job.token)
            if job.content_key in self._active:
                batch.states[job.content_key] = "active"
            else:
                batch.states[job.content_key] = "pending"
                offer = self._queue.offer(CacheQueueRequest(job.content_key, job.priority))
                if not offer.accepted:
                    batch.states[job.content_key] = "cancelled"
                    batch.cancelled += 1
                    existing.subscribers.pop(batch.batch_id, None)
            return True
        offer = self._queue.offer(CacheQueueRequest(job.content_key, job.priority))
        for dropped_key in offer.dropped_keys:
            self._drop_item_locked(dropped_key)
        if not offer.accepted:
            batch.states[job.content_key] = "cancelled"
            batch.cancelled += 1
            return False
        self._items[job.content_key] = _WorkItem(
            job=job,
            subscribers={batch.batch_id: job.token},
            all_tokens=[job.token],
            cache_epoch=self.cache.publication_epoch,
        )
        batch.states[job.content_key] = "pending"
        return True

    def _feed_bulk_locked(self, batch: _Batch) -> None:
        if batch.iterator is None or batch.exhausted or batch.cancelled_by_user:
            return
        pull_budget = self.max_pending
        while self._queue.pending_count < self.max_pending and pull_budget:
            pull_budget -= 1
            try:
                job = next(batch.iterator)
            except StopIteration:
                batch.exhausted = True
                batch.iterator = None
                break
            if not isinstance(job, GenerationJob):
                batch.requested += 1
                batch.failed += 1
                batch.exhausted = True
                batch.iterator = None
                break
            if batch.thumbnail_only and job.tier is not SpectrogramImageTier.THUMBNAIL:
                batch.requested += 1
                batch.failed += 1
                batch.exhausted = True
                batch.iterator = None
                break
            accepted = self._enqueue_locked(batch, job)
            if not accepted:
                # Equal/lower-priority bulk work waits for actual capacity instead
                # of consuming the rest of a very large iterator.
                break

    def submit(
        self,
        job: GenerationJob,
        *,
        storage_estimate: StorageEstimate | None = None,
        confirmed: bool = False,
    ) -> str:
        if not isinstance(job, GenerationJob):
            raise TypeError("Spectrogram generation job is invalid.")
        if storage_estimate is None:
            raise ValueError("A fresh cache storage check is required before generation.")
        require_storage_admission(storage_estimate, confirmed=confirmed)
        with self._condition:
            if self._shutdown:
                raise RuntimeError("Spectrogram generation supervisor is closed.")
            batch = self._new_batch(None, thumbnail_only=False)
            self._enqueue_locked(batch, job)
            self._condition.notify_all()
            return batch.batch_id

    def submit_bulk(
        self,
        jobs: Iterable[GenerationJob],
        *,
        storage_estimate: StorageEstimate,
        confirmed: bool = False,
    ) -> str:
        """Recheck/require the shared REV-05 decision before consuming bulk work."""
        require_storage_admission(storage_estimate, confirmed=confirmed)
        iterator = iter(jobs)
        with self._condition:
            if self._shutdown:
                raise RuntimeError("Spectrogram generation supervisor is closed.")
            batch = self._new_batch(iterator, thumbnail_only=True)
            self._feed_bulk_locked(batch)
            self._condition.notify_all()
            return batch.batch_id

    def _dispatch(self) -> None:
        while True:
            with self._condition:
                while (
                    not self._shutdown
                    and (
                        len(self._active) >= self.max_workers
                        or self._queue.pending_count == 0
                    )
                ):
                    self._condition.wait()
                if self._shutdown:
                    return
                request = self._queue.pop()
                if request is None:
                    continue
                item = self._items.get(request.content_key)
                if item is None or not item.subscribers:
                    self._items.pop(request.content_key, None)
                    continue
                for batch_id in item.subscribers:
                    batch = self._batches.get(batch_id)
                    if batch is not None and batch.states.get(request.content_key) == "pending":
                        batch.states[request.content_key] = "active"
                future = self._executor.submit(self._run_item, item)
                self._active[request.content_key] = (future, item)
                future.add_done_callback(
                    lambda completed, key=request.content_key: self._complete_item(key, completed)
                )
                for batch in self._batches.values():
                    self._feed_bulk_locked(batch)

    def _run_item(self, item: _WorkItem) -> _WorkResult:
        try:
            current = tuple(token for token in item.all_tokens if self.token_is_current(token))
            if not current:
                return _WorkResult("stale", ())
            entry = self.cache.lookup(item.job.content_key)
            if (
                entry is not None
                and entry.source_sha256 == item.job.token.source_sha256
                and entry.tier is item.job.tier
            ):
                return _WorkResult("cache_hit", current)
            raster = item.job.render(item.cancel_event.is_set)
            if not isinstance(raster, SpectrogramRaster):
                raise ValueError("Spectrogram renderer returned an invalid result.")
            if (
                raster.content_key != item.job.content_key
                or raster.metadata.source_sha256 != item.job.token.source_sha256
                or raster.metadata.tier is not item.job.tier
            ):
                raise ValueError("Spectrogram renderer returned mismatched content.")
            current = tuple(token for token in item.all_tokens if self.token_is_current(token))
            if not current:
                return _WorkResult("stale", ())
            with self._condition:
                protected = set(self._items).union(self._active)
            self.cache.publish(
                raster,
                settings_digest=current[0].settings_digest,
                protected_keys=protected,
                expected_clear_epoch=item.cache_epoch,
            )
            return _WorkResult("completed", current)
        except GenerationCancelled:
            return _WorkResult("cancelled", ())
        except Exception:
            return _WorkResult("failed", ())

    def _complete_item(self, content_key: str, future: Future[_WorkResult]) -> None:
        try:
            result = future.result()
        except Exception:
            result = _WorkResult("failed", ())
        with self._condition:
            active = self._active.pop(content_key, None)
            item = self._items.pop(content_key, None)
            if item is None and active is not None:
                item = active[1]
            if item is not None:
                current_tokens = set(result.current_tokens)
                for batch_id, token in tuple(item.subscribers.items()):
                    batch = self._batches.get(batch_id)
                    if batch is None or batch.states.get(content_key) != "active":
                        continue
                    if batch.cancelled_by_user:
                        batch.states[content_key] = "cancelled"
                        batch.cancelled += 1
                    elif result.outcome == "cache_hit" and token in current_tokens:
                        batch.states[content_key] = "cache_hit"
                        batch.cache_hits += 1
                    elif result.outcome == "completed" and token in current_tokens:
                        batch.states[content_key] = "completed"
                        batch.completed += 1
                    else:
                        batch.states[content_key] = "failed"
                        batch.failed += 1
            for batch in self._batches.values():
                self._feed_bulk_locked(batch)
            self._condition.notify_all()

    @staticmethod
    def _is_done(batch: _Batch) -> bool:
        outstanding = any(state in {"pending", "active"} for state in batch.states.values())
        source_done = batch.exhausted or batch.cancelled_by_user
        return source_done and not outstanding

    def progress(self, batch_id: str) -> GenerationProgress:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError("Spectrogram generation batch does not exist.")
            pending = sum(state == "pending" for state in batch.states.values())
            active = sum(state == "active" for state in batch.states.values())
            return GenerationProgress(
                batch_id=batch.batch_id,
                requested=batch.requested,
                completed=batch.completed,
                failed=batch.failed,
                cancelled=batch.cancelled,
                cache_hits=batch.cache_hits,
                pending=pending,
                active=active,
                done=self._is_done(batch),
            )

    def wait(self, batch_id: str, *, timeout: float) -> GenerationProgress:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Spectrogram wait timeout is invalid.")
        deadline = time.monotonic() + float(timeout)
        with self._condition:
            while True:
                progress = self.progress(batch_id)
                if progress.done:
                    return progress
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Spectrogram generation did not finish in time.")
                self._condition.wait(remaining)

    def cancel(self, batch_id: str) -> GenerationProgress:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError("Spectrogram generation batch does not exist.")
            batch.cancelled_by_user = True
            batch.iterator = None
            batch.exhausted = True
            for content_key, state in tuple(batch.states.items()):
                item = self._items.get(content_key)
                if state == "pending":
                    if item is not None:
                        item.subscribers.pop(batch_id, None)
                        if not item.subscribers:
                            self._queue.remove(content_key)
                            self._items.pop(content_key, None)
                    batch.states[content_key] = "cancelled"
                    batch.cancelled += 1
                elif state == "active" and item is not None:
                    other_live = any(
                        subscriber_id != batch_id
                        and not self._batches[subscriber_id].cancelled_by_user
                        for subscriber_id in item.subscribers
                        if subscriber_id in self._batches
                    )
                    if not other_live:
                        item.cancel_event.set()
            self._condition.notify_all()
            return self.progress(batch_id)

    def drop_prefetch_except(self, retained_keys: set[str]) -> tuple[str, ...]:
        with self._condition:
            dropped = self._queue.drop_prefetch_except(retained_keys)
            for content_key in dropped:
                self._drop_item_locked(content_key)
            self._condition.notify_all()
            return dropped

    def invalidate_session_epoch(self, session_id: str, settings_epoch: int) -> None:
        """Cancel or mark stale work from the superseded settings transaction."""
        with self._condition:
            for content_key, item in tuple(self._items.items()):
                affected = tuple(
                    batch_id
                    for batch_id, token in item.subscribers.items()
                    if token.session_id == session_id and token.settings_epoch == settings_epoch
                )
                if not affected:
                    continue
                is_active = content_key in self._active
                if is_active:
                    unaffected = any(
                        token.session_id != session_id or token.settings_epoch != settings_epoch
                        for token in item.subscribers.values()
                    )
                    if not unaffected:
                        item.cancel_event.set()
                    continue
                for batch_id in affected:
                    item.subscribers.pop(batch_id, None)
                    batch = self._batches.get(batch_id)
                    if batch is not None and batch.states.get(content_key) == "pending":
                        batch.states[content_key] = "failed"
                        batch.failed += 1
                if not item.subscribers:
                    self._queue.remove(content_key)
                    self._items.pop(content_key, None)
            self._condition.notify_all()

    def clear_cache(self, content_keys: tuple[str, ...] | list[str]) -> CacheMutation:
        """Suppress matching queued work and clear only regenerable cache objects."""
        keys = tuple(dict.fromkeys(content_keys))
        with self._condition:
            for content_key in keys:
                item = self._items.get(content_key)
                if item is None:
                    continue
                item.cancel_event.set()
                if content_key in self._active:
                    continue
                self._queue.remove(content_key)
                self._drop_item_locked(content_key)
            mutation = self.cache.clear(keys)
            self._condition.notify_all()
            return mutation

    def shutdown(self, *, wait: bool) -> None:
        with self._condition:
            if self._shutdown:
                return
            for batch_id in tuple(self._batches):
                self.cancel(batch_id)
            self._shutdown = True
            for _, item in self._active.values():
                item.cancel_event.set()
            self._condition.notify_all()
        self._dispatcher.join(timeout=5 if wait else 0)
        self._executor.shutdown(wait=wait, cancel_futures=True)


__all__ = [
    "GenerationCancelled",
    "GenerationJob",
    "GenerationProgress",
    "GenerationToken",
    "SpectrogramGenerationSupervisor",
]
