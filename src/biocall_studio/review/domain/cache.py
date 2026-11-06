"""Pure bounded scheduling rules for regenerable Review spectrograms."""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass
from enum import IntEnum

from biocall_studio.review.domain.spectrograms import validate_spectrogram_content_key


class CachePriority(IntEnum):
    """Lower values run first; prefetch and bulk are expendable under pressure."""

    CURRENT_DETAIL = 0
    VISIBLE_THUMBNAIL = 1
    NEARBY_PREFETCH = 2
    GENERATE_ALL = 3


@dataclass(frozen=True, slots=True)
class CacheQueueRequest:
    content_key: str
    priority: CachePriority

    def __post_init__(self) -> None:
        validate_spectrogram_content_key(self.content_key)
        if not isinstance(self.priority, CachePriority):
            raise ValueError("Spectrogram generation priority is invalid.")


@dataclass(frozen=True, slots=True)
class QueueOffer:
    accepted: bool
    deduplicated: bool
    dropped_keys: tuple[str, ...] = ()


class GenerationQueue:
    """A small priority queue with content-key deduplication and backpressure."""

    def __init__(self, *, max_pending: int):
        if type(max_pending) is not int or not 1 <= max_pending <= 4_096:
            raise ValueError("Spectrogram queue limit must be from 1 to 4096.")
        self.max_pending = max_pending
        self._requests: dict[str, tuple[CacheQueueRequest, int, int]] = {}
        self._heap: list[tuple[int, int, int, str]] = []
        self._sequence = 0
        self._generation = 0
        self._lock = threading.RLock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._requests)

    def _insert(self, request: CacheQueueRequest) -> None:
        self._sequence += 1
        self._generation += 1
        marker = (request, self._sequence, self._generation)
        self._requests[request.content_key] = marker
        heapq.heappush(
            self._heap,
            (int(request.priority), self._sequence, self._generation, request.content_key),
        )

    def offer(self, request: CacheQueueRequest) -> QueueOffer:
        if not isinstance(request, CacheQueueRequest):
            raise TypeError("Spectrogram queue request is invalid.")
        with self._lock:
            current = self._requests.get(request.content_key)
            if current is not None:
                if request.priority < current[0].priority:
                    self._insert(request)
                return QueueOffer(True, True)

            dropped: tuple[str, ...] = ()
            if len(self._requests) >= self.max_pending:
                worst_key, worst = max(
                    self._requests.items(),
                    key=lambda item: (int(item[1][0].priority), item[1][1]),
                )
                if request.priority >= worst[0].priority:
                    return QueueOffer(False, False)
                del self._requests[worst_key]
                dropped = (worst_key,)
            self._insert(request)
            return QueueOffer(True, False, dropped)

    def pop(self) -> CacheQueueRequest | None:
        with self._lock:
            while self._heap:
                _, _, generation, content_key = heapq.heappop(self._heap)
                current = self._requests.get(content_key)
                if current is None or current[2] != generation:
                    continue
                del self._requests[content_key]
                return current[0]
            return None

    def remove(self, content_key: str) -> bool:
        validate_spectrogram_content_key(content_key)
        with self._lock:
            return self._requests.pop(content_key, None) is not None

    def drop_prefetch_except(self, retained_keys: set[str] | frozenset[str]) -> tuple[str, ...]:
        retained = set(retained_keys)
        for content_key in retained:
            validate_spectrogram_content_key(content_key)
        with self._lock:
            dropped = tuple(
                content_key
                for content_key, marker in self._requests.items()
                if marker[0].priority is CachePriority.NEARBY_PREFETCH
                and content_key not in retained
            )
            for content_key in dropped:
                del self._requests[content_key]
            return dropped

    def snapshot_keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._requests)


__all__ = [
    "CachePriority",
    "CacheQueueRequest",
    "GenerationQueue",
    "QueueOffer",
]
