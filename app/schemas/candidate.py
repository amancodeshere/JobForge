from __future__ import annotations

from enum import Enum
import re
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.tools.experience_levels import normalize_experience_levels


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
    experience_levels: List[str] = Field(default_factory=list)
    employment_types: List[str] = Field(default_factory=lambda: ["Full-time"])
    max_years_experience: int = 2
    posted_within_days: int = 30
    work_rights: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    excluded_companies: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    work_arrangements: List[str] = Field(default_factory=list)
    salary_min: Optional[int] = None
    preferred_companies: List[str] = Field(default_factory=list)
    preferred_industries: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_levels(self) -> "CandidatePreferences":
        selected = self.experience_levels or [self.experience_level]
        self.experience_levels = normalize_experience_levels(selected)
        self.experience_level = self.experience_levels[0] if self.experience_levels else "graduate"
        self.excluded_companies = _unique_values(
            [*self.excluded_companies, *_constraint_values(self.constraints, "company")]
        )
        self.excluded_keywords = _unique_values(
            [*self.excluded_keywords, *_constraint_values(self.constraints, "keyword")]
        )
        return self

    def selected_experience_levels(self) -> List[str]:
        return self.experience_levels or [self.experience_level]


class CandidateProfile(BaseModel):
    candidate_id: str = "candidate-001"
    candidate_name: str = "Candidate"
    target_roles: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    experience_level: str = "graduate"
    experience_levels: List[str] = Field(default_factory=lambda: ["graduate"])
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
            if skill.evidence_type not in {EvidenceType.LEARNING, EvidenceType.UNSUPPORTED}
        }

    def evidence_by_id(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.verified_evidence}


class UserInput(BaseModel):
    cv_path: str
    preferences: CandidatePreferences
    output_path: str = "sample_data/expected_outputs/latest_run.json"


def _constraint_values(constraints: List[str], kind: str) -> List[str]:
    values = []
    for constraint in constraints:
        match = re.match(rf"\s*(?:exclude|avoid)\s+{kind}\s*:\s*(.+?)\s*$", constraint, re.IGNORECASE)
        if match:
            values.append(match.group(1))
    return values


def _unique_values(values: List[str]) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique.append(cleaned)
    return unique
