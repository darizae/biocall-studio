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
from biocall_studio.review.persistence.cache import (
    CacheEntry,
    CacheMutation,
    SpectrogramCache,
)
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
    request_epoch: int = 0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session_id, str)
            or not self.session_id
            or len(self.session_id) > 120
            or type(self.settings_epoch) is not int
            or self.settings_epoch < 1
        ):
            raise ValueError("Spectrogram generation session token is invalid.")
        if type(self.request_epoch) is not int or self.request_epoch < 0:
            raise ValueError("Spectrogram generation request epoch is invalid.")
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
class GenerationCompletion:
    content_key: str
    outcome: str
    token: GenerationToken
    entry: CacheEntry | None
    prepared: object | None
    display_payload: object | None
    elapsed_milliseconds: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationJob:
    content_key: str
    tier: SpectrogramImageTier
    priority: CachePriority
    token: GenerationToken
    render: Callable[[object | None, Callable[[], bool]], SpectrogramRaster]
    prepare: Callable[[Callable[[], bool]], object] | None = None
    prepare_on_cache_hit: bool = False
    admit_write: Callable[[], None] | None = None
    load_display: bool = False
    completed: Callable[[GenerationCompletion], None] | None = None

    def __post_init__(self) -> None:
        validate_spectrogram_content_key(self.content_key)
        if not isinstance(self.tier, SpectrogramImageTier):
            raise ValueError("Spectrogram generation tier is invalid.")
        if not isinstance(self.priority, CachePriority):
            raise ValueError("Spectrogram generation priority is invalid.")
        if not isinstance(self.token, GenerationToken) or not callable(self.render):
            raise ValueError("Spectrogram generation job is invalid.")
        for callback in (self.prepare, self.admit_write, self.completed):
            if callback is not None and not callable(callback):
                raise ValueError("Spectrogram generation callback is invalid.")
        if not isinstance(self.prepare_on_cache_hit, bool) or not isinstance(
            self.load_display, bool
        ):
            raise ValueError("Spectrogram generation cache-hit policy is invalid.")


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
    done: bool = False
    requested: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    cache_hits: int = 0
    states: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _WorkItem:
    job: GenerationJob
    subscribers: dict[str, GenerationJob]
    all_tokens: list[GenerationToken]
    cache_epoch: int
    cancel_event: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True, slots=True)
class _WorkResult:
    outcome: str
    current_tokens: tuple[GenerationToken, ...]
    entry: CacheEntry | None = None
    prepared: object | None = None
    display_payload: object | None = None
    elapsed_milliseconds: int = 0
    error: str | None = None


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
                self._compact_if_terminal_locked(batch)

    def _enqueue_locked(self, batch: _Batch, job: GenerationJob) -> bool:
        if job.content_key in batch.states:
            return True
        batch.requested += 1
        existing = self._items.get(job.content_key)
        if existing is not None:
            if existing.job.tier is not job.tier:
                batch.states[job.content_key] = "failed"
                batch.failed += 1
                self._compact_if_terminal_locked(batch)
                return True
            if len(existing.subscribers) >= _MAX_DEDUP_SUBSCRIBERS:
                batch.states[job.content_key] = "failed"
                batch.failed += 1
                self._compact_if_terminal_locked(batch)
                return True
            existing.subscribers[batch.batch_id] = job
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
                    self._compact_if_terminal_locked(batch)
            return True
        offer = self._queue.offer(CacheQueueRequest(job.content_key, job.priority))
        for dropped_key in offer.dropped_keys:
            self._drop_item_locked(dropped_key)
        if not offer.accepted:
            batch.states[job.content_key] = "cancelled"
            batch.cancelled += 1
            self._compact_if_terminal_locked(batch)
            return False
        self._items[job.content_key] = _WorkItem(
            job=job,
            subscribers={batch.batch_id: job},
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
        self._compact_if_terminal_locked(batch)

    def submit(
        self,
        job: GenerationJob,
        *,
        storage_estimate: StorageEstimate | None = None,
        confirmed: bool = False,
    ) -> str:
        if not isinstance(job, GenerationJob):
            raise TypeError("Spectrogram generation job is invalid.")
        if storage_estimate is None and job.admit_write is None:
            raise ValueError("A fresh cache storage check is required before generation.")
        if storage_estimate is not None:
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
                while not self._shutdown and (
                    len(self._active) >= self.max_workers or self._queue.pending_count == 0
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
        started = time.monotonic_ns()
        try:
            current = tuple(token for token in item.all_tokens if self.token_is_current(token))
            if not current:
                return _WorkResult("stale", ())
            loaded = self.cache.load_rgb(item.job.content_key) if item.job.load_display else None
            entry = loaded[0] if loaded is not None else self.cache.lookup(item.job.content_key)
            if (
                entry is not None
                and entry.source_sha256 == item.job.token.source_sha256
                and entry.tier is item.job.tier
            ):
                prepared = (
                    item.job.prepare(item.cancel_event.is_set)
                    if item.job.prepare is not None and item.job.prepare_on_cache_hit
                    else None
                )
                display = loaded[1] if loaded is not None else None
                return _WorkResult(
                    "cache_hit",
                    current,
                    entry,
                    prepared,
                    display,
                    max(1, (time.monotonic_ns() - started) // 1_000_000),
                )
            if item.job.admit_write is not None:
                item.job.admit_write()
            prepared = (
                item.job.prepare(item.cancel_event.is_set) if item.job.prepare is not None else None
            )
            raster = item.job.render(prepared, item.cancel_event.is_set)
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
            entry = self.cache.publish(
                raster,
                settings_digest=current[0].settings_digest,
                protected_keys=protected,
                expected_clear_epoch=item.cache_epoch,
            )
            display = raster.rgb_bytes if item.job.load_display else None
            return _WorkResult(
                "completed",
                current,
                entry,
                prepared,
                display,
                max(1, (time.monotonic_ns() - started) // 1_000_000),
            )
        except GenerationCancelled as exc:
            return _WorkResult("cancelled", (), error=str(exc))
        except Exception as exc:
            return _WorkResult("failed", (), error=f"{type(exc).__name__}: {exc}")

    def _complete_item(self, content_key: str, future: Future[_WorkResult]) -> None:
        try:
            result = future.result()
        except Exception:
            result = _WorkResult("failed", ())
        callbacks: list[tuple[GenerationJob, GenerationCompletion]] = []
        with self._condition:
            active = self._active.pop(content_key, None)
            item = self._items.pop(content_key, None)
            if item is None and active is not None:
                item = active[1]
            if item is not None:
                current_tokens = set(result.current_tokens)
                touched_batches: list[_Batch] = []
                for batch_id, subscriber in tuple(item.subscribers.items()):
                    token = subscriber.token
                    token_is_current = token in current_tokens or (
                        result.outcome in {"cache_hit", "completed"}
                        and self.token_is_current(token)
                    )
                    batch = self._batches.get(batch_id)
                    if batch is None or batch.states.get(content_key) != "active":
                        continue
                    touched_batches.append(batch)
                    if batch.cancelled_by_user or result.outcome == "cancelled":
                        batch.states[content_key] = "cancelled"
                        batch.cancelled += 1
                    elif result.outcome == "cache_hit" and token_is_current:
                        batch.states[content_key] = "cache_hit"
                        batch.cache_hits += 1
                    elif result.outcome == "completed" and token_is_current:
                        batch.states[content_key] = "completed"
                        batch.completed += 1
                    else:
                        batch.states[content_key] = "failed"
                        batch.failed += 1
                    if subscriber.completed is not None:
                        outcome = (
                            result.outcome
                            if token_is_current and not batch.cancelled_by_user
                            else "stale"
                        )
                        callbacks.append(
                            (
                                subscriber,
                                GenerationCompletion(
                                    content_key=content_key,
                                    outcome=outcome,
                                    token=token,
                                    entry=result.entry,
                                    prepared=result.prepared,
                                    display_payload=result.display_payload,
                                    elapsed_milliseconds=result.elapsed_milliseconds,
                                    error=result.error,
                                ),
                            )
                        )
                for batch in touched_batches:
                    self._compact_if_terminal_locked(batch)
            for batch in self._batches.values():
                self._feed_bulk_locked(batch)
            self._condition.notify_all()
        for subscriber, completion in callbacks:
            try:
                if (
                    subscriber.load_display
                    and completion.display_payload is None
                    and completion.entry is not None
                    and completion.outcome in {"completed", "cache_hit"}
                ):
                    loaded = self.cache.load_rgb(content_key)
                    if loaded is not None:
                        completion = GenerationCompletion(
                            content_key=completion.content_key,
                            outcome=completion.outcome,
                            token=completion.token,
                            entry=loaded[0],
                            prepared=completion.prepared,
                            display_payload=loaded[1],
                            elapsed_milliseconds=completion.elapsed_milliseconds,
                            error=completion.error,
                        )
                subscriber.completed(completion)
            except Exception:
                # Presentation notification failure cannot corrupt cache state.
                continue

    @staticmethod
    def _has_reached_terminal_state(batch: _Batch) -> bool:
        outstanding = any(state in {"pending", "active"} for state in batch.states.values())
        source_done = batch.exhausted or batch.cancelled_by_user
        return source_done and not outstanding

    def _compact_if_terminal_locked(self, batch: _Batch) -> bool:
        if batch.done:
            return True
        if not self._has_reached_terminal_state(batch):
            return False
        batch.done = True
        batch.iterator = None
        batch.states.clear()
        return True

    @staticmethod
    def _is_done(batch: _Batch) -> bool:
        return batch.done

    def progress(self, batch_id: str) -> GenerationProgress:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError("Spectrogram generation batch does not exist.")
            self._compact_if_terminal_locked(batch)
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
                done=batch.done,
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
            self._compact_if_terminal_locked(batch)
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
            touched_batches: dict[str, _Batch] = {}
            for content_key, item in tuple(self._items.items()):
                affected = tuple(
                    batch_id
                    for batch_id, job in item.subscribers.items()
                    if job.token.session_id == session_id
                    and job.token.settings_epoch == settings_epoch
                )
                if not affected:
                    continue
                is_active = content_key in self._active
                if is_active:
                    unaffected = any(
                        job.token.session_id != session_id
                        or job.token.settings_epoch != settings_epoch
                        for job in item.subscribers.values()
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
                        touched_batches[batch_id] = batch
                if not item.subscribers:
                    self._queue.remove(content_key)
                    self._items.pop(content_key, None)
            for batch in touched_batches.values():
                self._compact_if_terminal_locked(batch)
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
    "GenerationCompletion",
    "GenerationJob",
    "GenerationProgress",
    "GenerationToken",
    "SpectrogramGenerationSupervisor",
]
