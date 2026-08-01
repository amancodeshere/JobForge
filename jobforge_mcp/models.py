from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.application import ApplicationResult, ScoreBreakdown
from app.schemas.candidate import CandidatePreferences
from app.schemas.job import JobResult
from app.services.jobforge import MAX_CV_CHARACTERS


class SearchJobsRequest(BaseModel):
    cv_text: str = Field(min_length=1, max_length=MAX_CV_CHARACTERS)
    preferences: CandidatePreferences
    limit: int = Field(default=10, ge=1, le=25)


class SearchJobMatch(BaseModel):
    job: JobResult
    score_breakdown: ScoreBreakdown


class SearchJobsResponse(BaseModel):
    search_mode: str
    search_sources: list[str] = Field(default_factory=list)
    search_warnings: list[str] = Field(default_factory=list)
    discovered_count: int
    validated_count: int
    validation_date: date
    matches: list[SearchJobMatch] = Field(default_factory=list)


class PrepareApplicationRequest(BaseModel):
    cv_text: str = Field(min_length=1, max_length=MAX_CV_CHARACTERS)
    preferences: CandidatePreferences
    job: JobResult


class PrepareApplicationResponse(BaseModel):
    application: ApplicationResult
