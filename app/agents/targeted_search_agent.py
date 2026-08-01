from __future__ import annotations

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobResult
from app.tools.job_search import search_sample_jobs, targeted_queries


class TargetedSearchAgent:
    name = "targeted_job_researcher"

    def __init__(self, sample_jobs_path: str) -> None:
        self.sample_jobs_path = sample_jobs_path
        self.tool_calls = 0

    def run(self, profile: CandidateProfile) -> list[JobResult]:
        queries = targeted_queries(profile)
        self.tool_calls += 1
        return search_sample_jobs(self.sample_jobs_path, queries)

