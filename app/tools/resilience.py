from __future__ import annotations

import random
from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Callable


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.01
    max_delay_seconds: float = 0.1

    def delay(self, attempt: int, random_value: float | None = None) -> float:
        jitter = random.random() if random_value is None else random_value
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempt - 1))) * (0.5 + jitter)


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreakerRegistry:
    """Small process-local circuit breaker that isolates unhealthy providers."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0, clock: Callable[[], float] = monotonic) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.clock = clock
        self._states: dict[str, _CircuitState] = {}
        self._lock = Lock()

    def allow(self, source: str) -> bool:
        with self._lock:
            state = self._states.setdefault(source, _CircuitState())
            if state.opened_at is None:
                return True
            if self.clock() - state.opened_at >= self.cooldown_seconds:
                state.opened_at = None
                state.failures = max(0, self.failure_threshold - 1)
                return True
            return False

    def record_success(self, source: str) -> None:
        with self._lock:
            self._states[source] = _CircuitState()

    def record_failure(self, source: str) -> None:
        with self._lock:
            state = self._states.setdefault(source, _CircuitState())
            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.opened_at = self.clock()

    def state(self, source: str) -> str:
        return "closed" if self.allow(source) else "open"


def retry_call(operation: Callable[[], object], policy: RetryPolicy, retryable: Callable[[Exception], bool], sleeper: Callable[[float], None] = sleep) -> tuple[object, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            return operation(), attempts - 1
        except Exception as exc:
            if attempts >= policy.max_attempts or not retryable(exc):
                setattr(exc, "retry_count", attempts - 1)
                raise
            sleeper(policy.delay(attempts))
