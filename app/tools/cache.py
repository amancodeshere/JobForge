from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, Generic, Literal, TypeVar


T = TypeVar("T")
CacheStatus = Literal["miss", "fresh", "stale"]


@dataclass(frozen=True)
class CacheResult(Generic[T]):
    value: T
    status: CacheStatus


@dataclass
class _Entry(Generic[T]):
    value: T
    fresh_until: float
    stale_until: float


class TTLCache(Generic[T]):
    """Bounded process-local cache with non-blocking stale-while-revalidate."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.max_entries = max(1, max_entries)
        self._clock = clock
        self._entries: OrderedDict[str, _Entry[T]] = OrderedDict()
        self._refreshing: set[str] = set()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache-refresh")

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], T],
        *,
        ttl_seconds: float,
        stale_seconds: float,
    ) -> CacheResult[T]:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry and now < entry.fresh_until:
                self._entries.move_to_end(key)
                return CacheResult(deepcopy(entry.value), "fresh")
            if entry and now < entry.stale_until:
                self._entries.move_to_end(key)
                if key not in self._refreshing:
                    self._refreshing.add(key)
                    self._executor.submit(
                        self._refresh,
                        key,
                        loader,
                        ttl_seconds,
                        stale_seconds,
                    )
                return CacheResult(deepcopy(entry.value), "stale")

        value = loader()
        self.set(key, value, ttl_seconds=ttl_seconds, stale_seconds=stale_seconds)
        return CacheResult(deepcopy(value), "miss")

    def set(self, key: str, value: T, *, ttl_seconds: float, stale_seconds: float) -> None:
        now = self._clock()
        with self._lock:
            self._entries[key] = _Entry(
                value=deepcopy(value),
                fresh_until=now + max(0.0, ttl_seconds),
                stale_until=now + max(0.0, ttl_seconds) + max(0.0, stale_seconds),
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._refreshing.clear()

    def _refresh(
        self,
        key: str,
        loader: Callable[[], T],
        ttl_seconds: float,
        stale_seconds: float,
    ) -> None:
        try:
            value = loader()
            self.set(key, value, ttl_seconds=ttl_seconds, stale_seconds=stale_seconds)
        finally:
            with self._lock:
                self._refreshing.discard(key)
