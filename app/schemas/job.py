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


class JobPool(BaseModel):
    discovered: List[JobResult] = Field(default_factory=list)
    validated: List[JobResult] = Field(default_factory=list)
    rejected: List[JobResult] = Field(default_factory=list)

