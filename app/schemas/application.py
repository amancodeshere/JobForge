from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from app.schemas.job import JobResult
from app.schemas.candidate import CandidateProfile


class Recommendation(str, Enum):
    STRONGLY_APPLY = "strongly_apply"
    APPLY = "apply"
    APPLY_WITH_TAILORING = "apply_with_tailoring"
    POSSIBLE = "possible"
    LOWER_PRIORITY = "lower_priority"


class ScoreBreakdown(BaseModel):
    overall_score: int
    components: dict[str, int]
    weights: dict[str, float]


class MatchingEvidence(BaseModel):
    requirement: str
    candidate_evidence: str
    evidence_ids: List[str] = Field(default_factory=list)


class TailoredStatement(BaseModel):
    tailored_bullet: str
    evidence_ids: List[str] = Field(default_factory=list)


class LLMApplicationCopy(BaseModel):
    tailored_cv: str
    cover_letter: str
    tailored_statements: List[TailoredStatement] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)


class QualityChecks(BaseModel):
    unsupported_claims: int = 0
    company_name_correct: bool = True
    evidence_grounded: bool = True
    job_eligible: bool = True
    score_explained: bool = True
    issues: List[str] = Field(default_factory=list)


class ApplicationResult(BaseModel):
    job_id: str
    job: JobResult
    relevance_score: int
    score_breakdown: ScoreBreakdown
    recommendation: Recommendation
    job_summary: str
    matching_evidence: List[MatchingEvidence] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    tailored_cv: str
    tailored_cv_latex: str = ""
    tailored_statements: List[TailoredStatement] = Field(default_factory=list)
    cover_letter: str
    interview_preparation_topics: List[str] = Field(default_factory=list)
    generation_source: str = "deterministic"
    quality_checks: QualityChecks


class AgentHealth(BaseModel):
    agent: str
    status: str
    tool_calls: int = 0
    valid_results: int = 0
    invalid_results: int = 0
    execution_errors: int = 0
    duration_ms: int = 0
    notes: List[str] = Field(default_factory=list)


class ValidationCheck(BaseModel):
    part: str
    passed: bool
    issues: List[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    candidate_profile: CandidateProfile
    search_mode: str = "sample"
    search_sources: List[str] = Field(default_factory=list)
    search_warnings: List[str] = Field(default_factory=list)
    discovered_count: int
    validated_count: int
    recommended_count: int
    applications: List[ApplicationResult] = Field(default_factory=list)
    agent_health: List[AgentHealth] = Field(default_factory=list)
    validation_checks: List[ValidationCheck] = Field(default_factory=list)
