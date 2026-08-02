from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.evaluation.validation import validate_candidate_profile
from app.schemas.application import ApplicationResult, JobSearchResult
from app.schemas.candidate import CandidatePreferences
from app.schemas.job import JobResult, JobStatus
from app.tools.job_search import validate_job


MAX_CV_CHARACTERS = 200_000


class JobForgeService:
    """Reusable application boundary for UI, CLI, and MCP transports."""

    def __init__(
        self,
        sample_jobs_path: str = "sample_data/jobs/jobs.json",
        orchestrator_factory: Callable[[], OrchestratorAgent] | None = None,
    ) -> None:
        self.sample_jobs_path = sample_jobs_path
        self._orchestrator_factory = orchestrator_factory or (
            lambda: OrchestratorAgent(sample_jobs_path=self.sample_jobs_path, enable_cache=True)
        )

    def search_jobs(
        self,
        cv_text: str,
        preferences: CandidatePreferences,
        *,
        limit: int = 10,
        use_live_search: bool = True,
        sample_fallback: bool = False,
    ) -> JobSearchResult:
        text = _validated_cv_text(cv_text)
        bounded_limit = max(1, min(limit, 25))
        with TemporaryDirectory(prefix="jobforge-service-") as directory:
            cv_path = Path(directory) / "cv.txt"
            cv_path.write_text(text, encoding="utf-8")
            return self._orchestrator_factory().search(
                cv_path=str(cv_path),
                preferences=preferences,
                use_live_search=use_live_search,
                sample_fallback=sample_fallback,
                limit=bounded_limit,
            )

    def prepare_application(
        self,
        cv_text: str,
        preferences: CandidatePreferences,
        job: JobResult,
        *,
        today: date | None = None,
    ) -> ApplicationResult:
        text = _validated_cv_text(cv_text)
        validation_date = today or date.today()
        checked_job = validate_job(job.model_copy(deep=True), preferences, today=validation_date)
        if checked_job.status != JobStatus.VALIDATED:
            reasons = "; ".join(checked_job.rejection_reasons) or "Job validation failed."
            raise ValueError(f"The selected job cannot be prepared: {reasons}")

        with TemporaryDirectory(prefix="jobforge-service-") as directory:
            cv_path = Path(directory) / "cv.txt"
            cv_path.write_text(text, encoding="utf-8")
            profile = CandidateProfileAgent().run(str(cv_path), preferences)

        profile_check = validate_candidate_profile(profile)
        if not profile_check.passed:
            raise ValueError("The CV could not be validated: " + "; ".join(profile_check.issues))
        return ApplicationTailorAgent().run(
            profile,
            preferences,
            checked_job,
            today=validation_date,
        )


def _validated_cv_text(cv_text: str) -> str:
    text = cv_text.strip()
    if not text:
        raise ValueError("CV text is required.")
    if len(text) > MAX_CV_CHARACTERS:
        raise ValueError(f"CV text must not exceed {MAX_CV_CHARACTERS:,} characters.")
    return text
