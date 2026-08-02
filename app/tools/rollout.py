from __future__ import annotations

import hashlib
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class RolloutConfig:
    ranker_v2_enabled: bool = True
    shadow_enabled: bool = False
    rollout_percent: int = 100

    @classmethod
    def from_env(cls) -> "RolloutConfig":
        return cls(
            ranker_v2_enabled=_flag("JOBFORGE_RANKER_V2", True),
            shadow_enabled=_flag("JOBFORGE_RANKER_SHADOW", False),
            rollout_percent=_bounded_int("JOBFORGE_RANKER_ROLLOUT_PERCENT", 100, 0, 100),
        )


@dataclass(frozen=True)
class RolloutDecision:
    ranker: str
    bucket: int
    shadow_enabled: bool


class ShadowComparison(BaseModel):
    control_ranker: str = "v1"
    candidate_ranker: str = "v2"
    top_ten_overlap: float = 1.0
    average_displacement: float = 0.0
    control_count: int = 0
    candidate_count: int = 0


class SearchFeedback(BaseModel):
    correlation_id: str
    job_id: str
    signal: str
    ranker: str
    rank: int = Field(ge=1)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedbackStore:
    def __init__(self, max_entries: int = 2_000) -> None:
        self._items: deque[SearchFeedback] = deque(maxlen=max_entries)
        self._lock = Lock()

    def add(self, feedback: SearchFeedback) -> None:
        with self._lock:
            self._items.append(feedback)

    def snapshot(self) -> list[SearchFeedback]:
        with self._lock:
            return list(self._items)


@dataclass(frozen=True)
class PromotionMetrics:
    precision_at_ten: float
    duplicate_rate: float
    invalid_rate: float
    p95_latency_seconds: float
    provider_error_rate: float


@dataclass(frozen=True)
class PromotionDecision:
    approved: bool
    failed_gates: tuple[str, ...] = ()


FEEDBACK_STORE = FeedbackStore()


def rollout_decision(key: str, config: RolloutConfig) -> RolloutDecision:
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100
    use_v2 = config.ranker_v2_enabled and bucket < config.rollout_percent
    return RolloutDecision(
        ranker="v2" if use_v2 else "v1",
        bucket=bucket,
        shadow_enabled=config.shadow_enabled,
    )


def compare_rankings(control_ids: Iterable[str], candidate_ids: Iterable[str], limit: int = 10) -> ShadowComparison:
    control = list(control_ids)[:limit]
    candidate = list(candidate_ids)[:limit]
    shared = set(control) & set(candidate)
    denominator = max(1, len(set(control) | set(candidate)))
    displacement = [abs(control.index(job_id) - candidate.index(job_id)) for job_id in shared]
    return ShadowComparison(
        top_ten_overlap=round(len(shared) / denominator, 4),
        average_displacement=round(sum(displacement) / len(displacement), 2) if displacement else 0.0,
        control_count=len(control),
        candidate_count=len(candidate),
    )


def evaluate_promotion(metrics: PromotionMetrics) -> PromotionDecision:
    failed: list[str] = []
    if metrics.precision_at_ten < 0.80:
        failed.append("precision_at_ten")
    if metrics.duplicate_rate >= 0.02:
        failed.append("duplicate_rate")
    if metrics.invalid_rate >= 0.05:
        failed.append("invalid_rate")
    if metrics.p95_latency_seconds >= 12.0:
        failed.append("p95_latency")
    if metrics.provider_error_rate >= 0.10:
        failed.append("provider_error_rate")
    return PromotionDecision(approved=not failed, failed_gates=tuple(failed))


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))
