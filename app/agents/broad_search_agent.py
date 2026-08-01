from __future__ import annotations

from app.schemas.candidate import CandidatePreferences
from app.schemas.job import JobResult
from app.tools.job_search import broad_queries, search_sample_jobs


class BroadSearchAgent:
    name = "broad_opportunity_scout"

    def __init__(self, sample_jobs_path: str) -> None:
        self.sample_jobs_path = sample_jobs_path
        self.tool_calls = 0

    def run(self, preferences: CandidatePreferences) -> list[JobResult]:
        queries = broad_queries(preferences)
        self.tool_calls += 1
        return search_sample_jobs(self.sample_jobs_path, queries)

