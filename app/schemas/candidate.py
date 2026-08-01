from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class EvidenceType(str, Enum):
    EXPLICIT = "explicit"
    INFERRED_FROM_PROJECT = "inferred_from_project"
    LEARNING = "learning"
    UNSUPPORTED = "unsupported"


class EvidenceItem(BaseModel):
    evidence_id: str
    cv_section: str
    original_text: str
    evidence_type: EvidenceType = EvidenceType.EXPLICIT


class SkillEvidence(BaseModel):
    name: str
    category: str
    evidence_type: EvidenceType
    evidence_ids: List[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    description: str
    technologies: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class CandidatePreferences(BaseModel):
    target_roles: List[str] = Field(default_factory=list)
    career_interests: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    experience_level: str = "graduate"
    employment_types: List[str] = Field(default_factory=lambda: ["Full-time"])
    max_years_experience: int = 2
    posted_within_days: int = 30
    work_rights: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    candidate_id: str = "candidate-001"
    target_roles: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    experience_level: str = "graduate"
    skills: List[SkillEvidence] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    eligibility: dict = Field(default_factory=dict)
    verified_evidence: List[EvidenceItem] = Field(default_factory=list)
    career_themes: List[str] = Field(default_factory=list)
    profile_gaps: List[str] = Field(default_factory=list)
    source_cv: Optional[str] = None

    def supported_skill_names(self) -> set[str]:
        return {
            skill.name.lower()
            for skill in self.skills
            if skill.evidence_type != EvidenceType.UNSUPPORTED
        }

    def evidence_by_id(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.verified_evidence}


class UserInput(BaseModel):
    cv_path: str
    preferences: CandidatePreferences
    output_path: str = "sample_data/expected_outputs/latest_run.json"

