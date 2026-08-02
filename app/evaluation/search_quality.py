from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.schemas.candidate import (
    CandidatePreferences,
    CandidateProfile,
    EvidenceType,
    Project,
    SkillEvidence,
)
from app.schemas.job import JobResult, JobStatus
from app.tools.duplicate_detection import deduplicate_jobs
from app.tools.job_search import validate_job
from app.tools.relevance_scoring import rank_jobs
from app.tools.live_job_search import SearchOutcome


RELEVANT_GRADE = 2


class BenchmarkProfile(BaseModel):
    skills: list[str] = Field(default_factory=list)
    career_themes: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)


class SearchBenchmarkCase(BaseModel):
    case_id: str
    description: str
    profile: BenchmarkProfile
    preferences: CandidatePreferences
    labels: dict[str, int]


class SearchQualityMetrics(BaseModel):
    case_count: int
    precision_at_5: float
    precision_at_10: float
    ndcg_at_10: float
    relevant_recall: float
    duplicate_rate: float
    invalid_link_rate: float
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    confidence_floor: int = 42
    result_floor: int = 62


class CaseMetrics(BaseModel):
    case_id: str
    ranked_job_ids: list[str]
    precision_at_5: float
    precision_at_10: float
    ndcg_at_10: float
    relevant_recall: float
    rejected_count: int


class BenchmarkReport(BaseModel):
    generated_for: date
    metrics: SearchQualityMetrics
    cases: list[CaseMetrics]


class ProviderMetrics(BaseModel):
    source: str
    searches: int
    request_count: int
    records_returned: int
    average_duration_ms: int
    error_rate: float
    estimated_cost: float


def load_benchmark(path: str | Path) -> list[SearchBenchmarkCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SearchBenchmarkCase.model_validate(item) for item in payload]


def evaluate_benchmark(
    cases: Iterable[SearchBenchmarkCase],
    jobs: Iterable[JobResult],
    *,
    today: date,
    confidence_floor: int = 42,
    result_floor: int = 62,
) -> BenchmarkReport:
    case_list = list(cases)
    job_list = list(jobs)
    case_metrics: list[CaseMetrics] = []
    rejection_reasons: Counter[str] = Counter()

    for case in case_list:
        profile = _candidate_profile(case)
        validated: list[JobResult] = []
        rejected_count = 0
        for source_job in job_list:
            job = validate_job(source_job.model_copy(deep=True), case.preferences, today=today)
            if job.status == JobStatus.VALIDATED:
                validated.append(job)
            else:
                rejected_count += 1
                rejection_reasons.update(job.rejection_reasons)
        ranked = [
            job
            for job, _score in rank_jobs(
                profile,
                case.preferences,
                validated,
                today=today,
                confidence_floor=confidence_floor,
                result_floor=result_floor,
            )
        ]
        ranked_ids = [job.job_id for job in ranked]
        case_metrics.append(
            CaseMetrics(
                case_id=case.case_id,
                ranked_job_ids=ranked_ids,
                precision_at_5=precision_at_k(ranked_ids, case.labels, 5),
                precision_at_10=precision_at_k(ranked_ids, case.labels, 10),
                ndcg_at_10=ndcg_at_k(ranked_ids, case.labels, 10),
                relevant_recall=relevant_recall(ranked_ids, case.labels),
                rejected_count=rejected_count,
            )
        )

    metrics = SearchQualityMetrics(
        case_count=len(case_list),
        precision_at_5=_mean(item.precision_at_5 for item in case_metrics),
        precision_at_10=_mean(item.precision_at_10 for item in case_metrics),
        ndcg_at_10=_mean(item.ndcg_at_10 for item in case_metrics),
        relevant_recall=_mean(item.relevant_recall for item in case_metrics),
        duplicate_rate=duplicate_rate(job_list),
        invalid_link_rate=invalid_link_rate(job_list),
        rejection_reasons=dict(rejection_reasons.most_common()),
        confidence_floor=confidence_floor,
        result_floor=result_floor,
    )
    return BenchmarkReport(generated_for=today, metrics=metrics, cases=case_metrics)


def precision_at_k(ranked_job_ids: Iterable[str], labels: dict[str, int], k: int) -> float:
    selected = list(ranked_job_ids)[: max(0, k)]
    if not selected:
        return 0.0
    relevant = sum(1 for job_id in selected if labels.get(job_id, 0) >= RELEVANT_GRADE)
    return round(relevant / len(selected), 4)


def relevant_recall(ranked_job_ids: Iterable[str], labels: dict[str, int]) -> float:
    expected = {job_id for job_id, grade in labels.items() if grade >= RELEVANT_GRADE}
    if not expected:
        return 1.0
    returned = set(ranked_job_ids)
    return round(len(expected & returned) / len(expected), 4)


def ndcg_at_k(ranked_job_ids: Iterable[str], labels: dict[str, int], k: int) -> float:
    gains = [labels.get(job_id, 0) for job_id in list(ranked_job_ids)[: max(0, k)]]
    ideal = sorted(labels.values(), reverse=True)[: max(0, k)]
    ideal_score = _discounted_gain(ideal)
    if not ideal_score:
        return 1.0
    return round(_discounted_gain(gains) / ideal_score, 4)


def duplicate_rate(jobs: Iterable[JobResult]) -> float:
    job_list = list(jobs)
    if not job_list:
        return 0.0
    return round((len(job_list) - len(deduplicate_jobs(job_list))) / len(job_list), 4)


def invalid_link_rate(jobs: Iterable[JobResult]) -> float:
    job_list = list(jobs)
    if not job_list:
        return 0.0
    invalid = 0
    for job in job_list:
        parsed = urlparse(job.application_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            invalid += 1
    return round(invalid / len(job_list), 4)


def aggregate_provider_metrics(
    outcomes: Iterable[SearchOutcome],
    *,
    request_costs: dict[str, float] | None = None,
) -> dict[str, ProviderMetrics]:
    """Aggregate provider telemetry without coupling evaluation to a metrics vendor."""

    request_costs = request_costs or {}
    samples: dict[str, list] = {}
    for outcome in outcomes:
        for source, telemetry in outcome.source_telemetry.items():
            samples.setdefault(source, []).append(telemetry)

    metrics: dict[str, ProviderMetrics] = {}
    for source, values in samples.items():
        request_count = sum(item.request_count for item in values)
        error_count = sum(item.error_count for item in values)
        metrics[source] = ProviderMetrics(
            source=source,
            searches=len(values),
            request_count=request_count,
            records_returned=sum(item.records_returned for item in values),
            average_duration_ms=round(sum(item.duration_ms for item in values) / len(values)),
            error_rate=round(error_count / len(values), 4),
            estimated_cost=round(request_count * request_costs.get(source, 0.0), 6),
        )
    return metrics


def _candidate_profile(case: SearchBenchmarkCase) -> CandidateProfile:
    return CandidateProfile(
        candidate_id=case.case_id,
        target_roles=case.preferences.target_roles,
        locations=case.preferences.locations,
        experience_level=case.preferences.experience_level,
        experience_levels=case.preferences.selected_experience_levels(),
        skills=[
            SkillEvidence(name=name, category="benchmark", evidence_type=EvidenceType.EXPLICIT)
            for name in case.profile.skills
        ],
        projects=case.profile.projects,
        career_themes=case.profile.career_themes,
    )


def _discounted_gain(grades: Iterable[int]) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return round(sum(items) / len(items), 4) if items else 0.0
