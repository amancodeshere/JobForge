from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    REJECTED = "rejected"


class JobResult(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    employment_type: str
    description: str
    source: str
    application_url: str
    date_found: str
    date_posted: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    experience_required: str = "unspecified"
    eligibility_requirements: List[str] = Field(default_factory=list)
    status: JobStatus = JobStatus.DISCOVERED
    rejection_reasons: List[str] = Field(default_factory=list)
    canonical_url: str = ""
    canonical_company: str = ""
    canonical_location: str = ""
    work_arrangement: str = "unspecified"
    compensation_text: Optional[str] = None
    compensation_min: Optional[int] = None
    compensation_max: Optional[int] = None
    compensation_currency: Optional[str] = None
    required_years_min: Optional[int] = None
    required_years_max: Optional[int] = None
    seniority_levels: List[str] = Field(default_factory=list)
    visa_requirements: List[str] = Field(default_factory=list)
    contract_duration: Optional[str] = None
    application_deadline: Optional[str] = None
    description_fingerprint: str = ""
    source_provenance: List[str] = Field(default_factory=list)
    source_job_ids: List[str] = Field(default_factory=list)
    duplicate_count: int = 1
    industry: Optional[str] = None
    inferred_skills: List[str] = Field(default_factory=list)
    normalization_version: int = 0


class JobPool(BaseModel):
    discovered: List[JobResult] = Field(default_factory=list)
    validated: List[JobResult] = Field(default_factory=list)
    rejected: List[JobResult] = Field(default_factory=list)
