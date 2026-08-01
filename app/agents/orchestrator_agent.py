from __future__ import annotations

import os
from datetime import date, datetime
from typing import List

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
from app.schemas.application import AgentHealth, WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.schemas.job import JobResult, JobStatus
from app.tools.duplicate_detection import deduplicate_jobs
from app.tools.job_search import validate_job
from app.tools.live_job_search import LiveJobSearch
from app.tools.relevance_scoring import calculate_relevance_score


class OrchestratorAgent:
    name = "orchestrator_quality_controller"

    def __init__(
        self,
        sample_jobs_path: str = "sample_data/jobs/jobs.json",
        live_search: LiveJobSearch | None = None,
    ) -> None:
        self.sample_jobs_path = sample_jobs_path
        self.live_search = live_search or LiveJobSearch()
        self.profile_agent = CandidateProfileAgent()
        self.broad_agent = BroadSearchAgent(sample_jobs_path, self.live_search)
        self.targeted_agent = TargetedSearchAgent(sample_jobs_path, self.live_search)
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
        health: List[AgentHealth] = []
        checks = []

        profile = self.profile_agent.run(cv_path, preferences)
        profile_check = validate_candidate_profile(profile)
        checks.append(profile_check)
        health.append(
            AgentHealth(
                agent=self.profile_agent.name,
                status="completed" if profile_check.passed else "completed_with_issues",
                valid_results=len(profile.skills),
                invalid_results=len(profile_check.issues),
            )
        )

        broad_jobs = self.broad_agent.run(preferences, use_live=use_live_search)
        health.append(
            AgentHealth(
                agent=self.broad_agent.name,
                status="completed",
                tool_calls=self.broad_agent.tool_calls,
                valid_results=len(broad_jobs),
                execution_errors=len(self.broad_agent.last_outcome.source_errors),
                notes=self.broad_agent.last_outcome.source_errors[:8],
            )
        )

        targeted_jobs = self.targeted_agent.run(profile, use_live=use_live_search)
        health.append(
            AgentHealth(
                agent=self.targeted_agent.name,
                status="completed",
                tool_calls=self.targeted_agent.tool_calls,
                valid_results=len(targeted_jobs),
                execution_errors=len(self.targeted_agent.last_outcome.source_errors),
                notes=self.targeted_agent.last_outcome.source_errors[:8],
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
        validated_jobs, rejected_jobs = _validate_jobs(discovered, preferences, validation_date)
        job_pool_check = validate_job_pool([*validated_jobs, *rejected_jobs])
        checks.append(job_pool_check)
        health.append(
            AgentHealth(
                agent="job_validation",
                status="completed" if job_pool_check.passed else "completed_with_issues",
                valid_results=len(validated_jobs),
                invalid_results=len(rejected_jobs),
                notes=_rejection_notes(rejected_jobs),
            )
        )

        ranked_jobs = sorted(
            validated_jobs,
            key=lambda job: calculate_relevance_score(profile, preferences, job, today=validation_date).overall_score,
            reverse=True,
        )[:top_n]
        self.tailor_agent = ApplicationTailorAgent()
        applications = [
            self.tailor_agent.run(profile, preferences, job, today=validation_date)
            for job in ranked_jobs
        ]
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
                notes=self.tailor_agent.notes[:8],
            )
        )

        result = WorkflowResult(
            candidate_profile=profile,
            search_mode=search_mode,
            search_sources=search_sources,
            search_warnings=search_warnings,
            discovered_count=len(discovered),
            validated_count=len(validated_jobs),
            recommended_count=len(applications),
            applications=applications,
            agent_health=health,
            validation_checks=checks,
        )

        dashboard_check = validate_dashboard_payload(result)
        result.validation_checks.append(dashboard_check)
        result.agent_health.append(
            AgentHealth(
                agent=self.dashboard_agent.name,
                status="completed" if dashboard_check.passed else "completed_with_issues",
                valid_results=1 if dashboard_check.passed else 0,
                invalid_results=len(dashboard_check.issues),
            )
        )
        self.dashboard_agent.write_payload(result, output_path)
        return result


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
