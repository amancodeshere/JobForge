from __future__ import annotations

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobResult
from app.tools.live_job_search import LiveJobSearch, SearchOutcome
from app.tools.job_search import search_sample_jobs, targeted_queries


class TargetedSearchAgent:
    name = "targeted_job_researcher"

    def __init__(self, sample_jobs_path: str, live_search: LiveJobSearch | None = None) -> None:
        self.sample_jobs_path = sample_jobs_path
        self.live_search = live_search or LiveJobSearch()
        self.tool_calls = 0
        self.last_outcome = SearchOutcome()

    def run(self, profile: CandidateProfile, use_live: bool = False) -> list[JobResult]:
        if use_live:
            self.last_outcome = self.live_search.targeted_search(profile)
            self.tool_calls += len(self.last_outcome.sources_attempted)
            return self.last_outcome.jobs
        queries = targeted_queries(profile)
        self.tool_calls += 1
        self.last_outcome = SearchOutcome(jobs=search_sample_jobs(self.sample_jobs_path, queries), sources_attempted=["sample"])
        return self.last_outcome.jobs
