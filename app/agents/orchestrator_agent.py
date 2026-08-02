from __future__ import annotations

import os
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, List, TypeVar

from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.agents.broad_search_agent import BroadSearchAgent
from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.agents.dashboard_agent import DashboardAgent
from app.agents.targeted_search_agent import TargetedSearchAgent
from app.evaluation.validation import (
    validate_applications,
    validate_candidate_profile,
    validate_dashboard_payload,
    validate_job_pool,
    validate_rankings,
)
from app.schemas.application import (
    AgentHealth,
    ApplicationResult,
    JobSearchResult,
    ProviderHealth,
    RankedJob,
    ScoreBreakdown,
    WorkflowResult,
)
from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.schemas.job import JobResult, JobStatus
from app.tools.duplicate_detection import deduplicate_jobs
from app.tools.cache import TTLCache
from app.tools.job_search import validate_job
from app.tools.live_job_search import LiveJobSearch, ProgressCallback, SearchOutcome
from app.tools.relevance_scoring import rank_jobs, rank_jobs_v1
from app.tools.rollout import RolloutConfig, compare_rankings, rollout_decision


_PROFILE_CACHE: TTLCache[CandidateProfile] = TTLCache(max_entries=64)


class OrchestratorAgent:
    name = "orchestrator_quality_controller"

    def __init__(
        self,
        sample_jobs_path: str = "sample_data/jobs/jobs.json",
        live_search: LiveJobSearch | None = None,
        progress_callback: ProgressCallback | None = None,
        enable_cache: bool = False,
        rollout_config: RolloutConfig | None = None,
    ) -> None:
        self.sample_jobs_path = sample_jobs_path
        self.enable_cache = enable_cache
        self.profile_cache_status = "disabled"
        self.rollout_config = rollout_config or RolloutConfig.from_env()
        broad_live_search = live_search or LiveJobSearch(progress_callback=progress_callback)
        targeted_live_search = live_search or LiveJobSearch(progress_callback=progress_callback)
        self.live_search = broad_live_search
        self.profile_agent = CandidateProfileAgent()
        self.broad_agent = BroadSearchAgent(sample_jobs_path, broad_live_search)
        self.targeted_agent = TargetedSearchAgent(sample_jobs_path, targeted_live_search)
        self.tailor_agent = ApplicationTailorAgent()
        self.dashboard_agent = DashboardAgent()

    def run(
        self,
        cv_path: str,
        preferences: CandidatePreferences,
        output_path: str,
        top_n: int = 5,
        use_live_search: bool = False,
        sample_fallback: bool = True,
    ) -> WorkflowResult:
        search_result = self.search(
            cv_path=cv_path,
            preferences=preferences,
            use_live_search=use_live_search,
            sample_fallback=sample_fallback,
        )
        health = list(search_result.agent_health)
        checks = list(search_result.validation_checks)
        ranked_jobs = [
            (ranked.job, ranked.score_breakdown)
            for ranked in search_result.ranked_jobs[:top_n]
        ]

        tailoring_started = perf_counter()
        applications = self._tailor_ranked_jobs(
            search_result.candidate_profile,
            preferences,
            ranked_jobs,
            search_result.validation_date,
        )
        tailoring_duration = _elapsed_ms(tailoring_started)
        applications = sorted(applications, key=lambda item: item.relevance_score, reverse=True)
        ranking_check = validate_rankings(applications)
        application_check = validate_applications(applications)
        checks.extend([ranking_check, application_check])
        health.append(
            AgentHealth(
                agent=self.tailor_agent.name,
                status="completed" if application_check.passed else "completed_with_issues",
                valid_results=len(applications),
                invalid_results=sum(1 for application in applications if application.quality_checks.unsupported_claims),
                tool_calls=self.tailor_agent.llm_attempts,
                execution_errors=self.tailor_agent.llm_errors,
                duration_ms=tailoring_duration,
                notes=self.tailor_agent.notes[:8],
            )
        )

        result = WorkflowResult(
            candidate_profile=search_result.candidate_profile,
            search_mode=search_result.search_mode,
            search_sources=search_result.search_sources,
            search_warnings=search_result.search_warnings,
            discovered_count=search_result.discovered_count,
            validated_count=search_result.validated_count,
            recommended_count=len(applications),
            applications=applications,
            agent_health=health,
            validation_checks=checks,
        )

        dashboard_started = perf_counter()
        dashboard_check = validate_dashboard_payload(result)
        dashboard_duration = _elapsed_ms(dashboard_started)
        result.validation_checks.append(dashboard_check)
        result.agent_health.append(
            AgentHealth(
                agent=self.dashboard_agent.name,
                status="completed" if dashboard_check.passed else "completed_with_issues",
                valid_results=1 if dashboard_check.passed else 0,
                invalid_results=len(dashboard_check.issues),
                duration_ms=dashboard_duration,
            )
        )
        self.dashboard_agent.write_payload(result, output_path)
        return result

    def search(
        self,
        cv_path: str,
        preferences: CandidatePreferences,
        use_live_search: bool = False,
        sample_fallback: bool = True,
        limit: int | None = None,
    ) -> JobSearchResult:
        health: List[AgentHealth] = []
        checks = []

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="workflow") as executor:
            profile_future = executor.submit(_timed, lambda: self._profile(cv_path, preferences))
            broad_future = executor.submit(
                _timed,
                lambda: self.broad_agent.run(preferences, use_live=use_live_search),
            )
            profile, profile_duration = profile_future.result()
            targeted_future = executor.submit(
                _timed,
                lambda: self.targeted_agent.run(profile, use_live=use_live_search),
            )
            broad_jobs, broad_duration = broad_future.result()
            targeted_jobs, targeted_duration = targeted_future.result()

        profile_check = validate_candidate_profile(profile)
        checks.append(profile_check)
        health.append(
            AgentHealth(
                agent=self.profile_agent.name,
                status="completed" if profile_check.passed else "completed_with_issues",
                valid_results=len(profile.skills),
                invalid_results=len(profile_check.issues),
                duration_ms=profile_duration,
                notes=[f"profile cache: {self.profile_cache_status}"],
            )
        )

        health.append(
            AgentHealth(
                agent=self.broad_agent.name,
                status="completed_with_issues" if self.broad_agent.last_outcome.source_errors else "completed",
                tool_calls=self.broad_agent.tool_calls,
                valid_results=len(broad_jobs),
                execution_errors=len(self.broad_agent.last_outcome.source_errors),
                duration_ms=broad_duration,
                notes=_source_notes(self.broad_agent.last_outcome)[:8],
            )
        )

        health.append(
            AgentHealth(
                agent=self.targeted_agent.name,
                status="completed_with_issues" if self.targeted_agent.last_outcome.source_errors else "completed",
                tool_calls=self.targeted_agent.tool_calls,
                valid_results=len(targeted_jobs),
                execution_errors=len(self.targeted_agent.last_outcome.source_errors),
                duration_ms=targeted_duration,
                notes=_source_notes(self.targeted_agent.last_outcome)[:8],
            )
        )

        discovered = deduplicate_jobs([*broad_jobs, *targeted_jobs])
        search_mode = "live" if use_live_search else "sample"
        search_sources = _unique_strings(
            [*self.broad_agent.last_outcome.sources_attempted, *self.targeted_agent.last_outcome.sources_attempted]
        )
        search_warnings = [
            *self.broad_agent.last_outcome.source_errors,
            *self.targeted_agent.last_outcome.source_errors,
        ]
        if use_live_search and not discovered and sample_fallback:
            search_warnings.append("No live jobs were returned; using the bundled sample dataset.")
            broad_jobs = self.broad_agent.run(preferences, use_live=False)
            targeted_jobs = self.targeted_agent.run(profile, use_live=False)
            discovered = deduplicate_jobs([*broad_jobs, *targeted_jobs])
            search_mode = "sample_fallback"
            search_sources.append("sample")
        validation_date = date.today() if search_mode == "live" else _validation_date(discovered, self.sample_jobs_path)
        validation_started = perf_counter()
        validated_jobs, rejected_jobs = _validate_jobs(discovered, preferences, validation_date)
        validation_duration = _elapsed_ms(validation_started)
        job_pool_check = validate_job_pool([*validated_jobs, *rejected_jobs])
        checks.append(job_pool_check)
        health.append(
            AgentHealth(
                agent="job_validation",
                status="completed" if job_pool_check.passed else "completed_with_issues",
                valid_results=len(validated_jobs),
                invalid_results=len(rejected_jobs),
                duration_ms=validation_duration,
                notes=_rejection_notes(rejected_jobs),
            )
        )

        rollout = rollout_decision(_rollout_key(profile, preferences), self.rollout_config)
        v2_ranked_jobs: list[tuple[JobResult, ScoreBreakdown]] = []
        if rollout.ranker == "v2" or rollout.shadow_enabled:
            v2_ranked_jobs = rank_jobs(
                profile,
                preferences,
                validated_jobs,
                today=validation_date,
                candidate_limit=50,
                result_limit=max(0, limit) if limit is not None else None,
            )
        v1_ranked_jobs: list[tuple[JobResult, ScoreBreakdown]] = []
        if rollout.ranker == "v1" or rollout.shadow_enabled:
            v1_ranked_jobs = rank_jobs_v1(
                profile,
                preferences,
                validated_jobs,
                today=validation_date,
                result_limit=max(0, limit) if limit is not None else None,
            )
        ranked_jobs = v2_ranked_jobs if rollout.ranker == "v2" else v1_ranked_jobs
        shadow = {}
        if rollout.shadow_enabled:
            shadow = compare_rankings(
                [job.job_id for job, _score in v1_ranked_jobs],
                [job.job_id for job, _score in v2_ranked_jobs],
            ).model_dump()
        outcomes = [self.broad_agent.last_outcome, self.targeted_agent.last_outcome]
        provider_health = _provider_health(
            outcomes,
            rejected_jobs=rejected_jobs,
            ranked_jobs=[job for job, _score in ranked_jobs[:10]],
            duplicates_removed=max(0, len(broad_jobs) + len(targeted_jobs) - len(discovered)),
        )
        return JobSearchResult(
            candidate_profile=profile,
            search_mode=search_mode,
            search_sources=search_sources,
            search_warnings=search_warnings,
            discovered_count=len(discovered),
            validated_count=len(validated_jobs),
            validation_date=validation_date,
            ranked_jobs=[RankedJob(job=job, score_breakdown=score) for job, score in ranked_jobs],
            agent_health=health,
            validation_checks=checks,
            provider_health=provider_health,
            search_alerts=_provider_alerts(provider_health, outcomes),
            correlation_ids=[outcome.correlation_id for outcome in outcomes if outcome.correlation_id],
            ranker_version=rollout.ranker,
            rollout_bucket=rollout.bucket,
            shadow_comparison=shadow,
        )

    def _profile(self, cv_path: str, preferences: CandidatePreferences) -> CandidateProfile:
        if not self.enable_cache:
            self.profile_cache_status = "disabled"
            return self.profile_agent.run(cv_path, preferences)
        content = Path(cv_path).read_bytes()
        payload = content + b"\0" + preferences.model_dump_json().encode("utf-8")
        key = hashlib.sha256(payload).hexdigest()
        cached = _PROFILE_CACHE.get_or_load(
            key,
            lambda: self.profile_agent.run(cv_path, preferences),
            ttl_seconds=86400,
            stale_seconds=86400,
        )
        self.profile_cache_status = cached.status
        profile = cached.value
        profile.source_cv = cv_path
        return profile

    def _tailor_ranked_jobs(
        self,
        profile,
        preferences: CandidatePreferences,
        ranked_jobs: list[tuple[JobResult, ScoreBreakdown]],
        validation_date: date,
    ) -> list[ApplicationResult]:
        self.tailor_agent = ApplicationTailorAgent()
        if not ranked_jobs:
            return []

        def tailor(job: JobResult, score: ScoreBreakdown):
            agent = ApplicationTailorAgent()
            application = agent.run(
                profile,
                preferences,
                job,
                today=validation_date,
                precomputed_score=score,
            )
            return application, agent

        workers = _bounded_env_int("JOBFORGE_TAILOR_WORKERS", 3, 1, 6)
        ordered: list[tuple[ApplicationResult, ApplicationTailorAgent] | None] = [None] * len(ranked_jobs)
        with ThreadPoolExecutor(max_workers=min(workers, len(ranked_jobs)), thread_name_prefix="tailor") as executor:
            futures = {
                executor.submit(tailor, job, score): index
                for index, (job, score) in enumerate(ranked_jobs)
            }
            for future in as_completed(futures):
                ordered[futures[future]] = future.result()

        applications: list[ApplicationResult] = []
        for item in ordered:
            if item is None:
                continue
            application, agent = item
            applications.append(application)
            self.tailor_agent.llm_attempts += agent.llm_attempts
            self.tailor_agent.llm_successes += agent.llm_successes
            self.tailor_agent.llm_errors += agent.llm_errors
            self.tailor_agent.notes.extend(agent.notes)
        return applications


def _validate_jobs(
    jobs: list[JobResult],
    preferences: CandidatePreferences,
    today: date,
) -> tuple[list[JobResult], list[JobResult]]:
    validated: list[JobResult] = []
    rejected: list[JobResult] = []
    for job in jobs:
        checked = validate_job(job, preferences, today=today)
        if checked.status == JobStatus.VALIDATED:
            validated.append(checked)
        else:
            rejected.append(checked)
    return validated, rejected


def _validation_date(jobs: list[JobResult], sample_jobs_path: str) -> date:
    configured = os.getenv("JOBFORGE_DEMO_DATE")
    if configured:
        try:
            return datetime.strptime(configured, "%Y-%m-%d").date()
        except ValueError:
            pass
    if "sample_data/jobs" in sample_jobs_path:
        parsed = [
            _parse_date(job.date_posted or job.date_found)
            for job in jobs
        ]
        valid_dates = [item for item in parsed if item]
        if valid_dates:
            return max(valid_dates)
    return date.today()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _rejection_notes(jobs: list[JobResult]) -> list[str]:
    return [
        f"{job.job_id}: {', '.join(job.rejection_reasons)}"
        for job in jobs[:8]
    ]


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _source_notes(outcome: SearchOutcome) -> list[str]:
    counts = [f"{source}: {outcome.source_counts.get(source, 0)} jobs" for source in outcome.sources_attempted]
    return [*counts, *outcome.source_errors]


def _provider_health(
    outcomes: list[SearchOutcome],
    *,
    rejected_jobs: list[JobResult],
    ranked_jobs: list[JobResult],
    duplicates_removed: int,
) -> list[ProviderHealth]:
    rejected = _source_occurrences(rejected_jobs)
    top_ten = _source_occurrences(ranked_jobs)
    values: list[ProviderHealth] = []
    for outcome in outcomes:
        for source, telemetry in outcome.source_telemetry.items():
            status = "degraded" if telemetry.error_count or telemetry.circuit_state == "open" else "healthy"
            values.append(ProviderHealth(
                source=source,
                status=status,
                duration_ms=telemetry.duration_ms,
                requests=telemetry.request_count,
                retries=telemetry.retry_count,
                records_received=telemetry.records_returned,
                records_rejected=rejected.get(source, 0),
                duplicates_removed=duplicates_removed if source == next(iter(outcome.source_telemetry), "") else 0,
                top_ten_contribution=top_ten.get(source, 0),
                cache_status=telemetry.cache_status,
                circuit_state=telemetry.circuit_state,
                estimated_cost_units=telemetry.estimated_cost_units,
                error_category=telemetry.error_category,
            ))
    return values


def _source_occurrences(jobs: list[JobResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        sources = job.source_provenance or [job.source]
        for source in set(sources):
            counts[source] = counts.get(source, 0) + 1
    return counts


def _provider_alerts(health: list[ProviderHealth], outcomes: list[SearchOutcome]) -> list[str]:
    alerts: list[str] = []
    for item in health:
        if item.circuit_state == "open":
            alerts.append(f"{item.source}: circuit open")
        elif item.error_category:
            alerts.append(f"{item.source}: {item.error_category} failure")
        if item.duration_ms >= 10_000:
            alerts.append(f"{item.source}: latency exceeded 10 seconds")
    if any(outcome.deadline_exceeded for outcome in outcomes):
        alerts.append("Search deadline exceeded; partial results were returned.")
    return _unique_strings(alerts)


def _rollout_key(profile: CandidateProfile, preferences: CandidatePreferences) -> str:
    payload = f"{profile.candidate_id}|{preferences.model_dump_json()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


T = TypeVar("T")


def _timed(operation: Callable[[], T]) -> tuple[T, int]:
    started = perf_counter()
    result = operation()
    return result, _elapsed_ms(started)


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))
