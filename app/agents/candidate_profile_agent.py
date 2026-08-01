from __future__ import annotations

import re
from typing import Iterable, List

from app.schemas.candidate import (
    CandidatePreferences,
    CandidateProfile,
    EvidenceItem,
    EvidenceType,
    Project,
    SkillEvidence,
)
from app.tools.document_parser import extract_text


SKILL_CATALOG = {
    "languages": ["Python", "C++", "SQL", "Java", "TypeScript", "JavaScript"],
    "machine_learning": ["PyTorch", "TensorFlow", "Transformers", "YOLO", "Machine Learning"],
    "software": ["Next.js", "FastAPI", "PostgreSQL", "React", "Docker", "AWS"],
    "robotics": ["ROS2", "OpenCV", "Computer Vision"],
    "data": ["Pandas", "NumPy", "T-SQL", "Power BI"],
}

PROJECT_MARKERS = ["project", "projects", "experience", "engineering", "robotics", "portfolio"]


class CandidateProfileAgent:
    name = "candidate_profile_agent"

    def run(self, cv_path: str, preferences: CandidatePreferences) -> CandidateProfile:
        text = extract_text(cv_path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        evidence = _build_evidence(lines)
        skills = _extract_skills(lines, evidence)
        projects = _extract_projects(lines, skills, evidence)
        career_themes = _career_themes(preferences, skills, projects)
        gaps = _profile_gaps(skills)

        return CandidateProfile(
            candidate_name=_candidate_name(lines),
            target_roles=preferences.target_roles,
            locations=preferences.locations,
            experience_level=preferences.experience_level,
            experience_levels=preferences.selected_experience_levels(),
            skills=skills,
            projects=projects,
            eligibility={"work_rights": preferences.work_rights},
            verified_evidence=evidence,
            career_themes=career_themes,
            profile_gaps=gaps,
            source_cv=cv_path,
        )


def _build_evidence(lines: List[str]) -> List[EvidenceItem]:
    items = []
    for index, line in enumerate(lines, start=1):
        if len(line) < 3:
            continue
        section = _guess_section(line)
        items.append(
            EvidenceItem(
                evidence_id=f"cv-{index:03d}",
                cv_section=section,
                original_text=line,
                evidence_type=EvidenceType.EXPLICIT,
            )
        )
    return items


def _extract_skills(lines: List[str], evidence: List[EvidenceItem]) -> List[SkillEvidence]:
    found: dict[str, SkillEvidence] = {}
    joined_by_id = {item.evidence_id: item.original_text for item in evidence}
    for category, skills in SKILL_CATALOG.items():
        for skill in skills:
            evidence_ids = [
                item.evidence_id
                for item in evidence
                if re.search(rf"(?<![A-Za-z0-9+#.]){re.escape(skill)}(?![A-Za-z0-9+#.])", item.original_text, re.IGNORECASE)
            ]
            if evidence_ids:
                found[skill.lower()] = SkillEvidence(
                    name=skill,
                    category=category,
                    evidence_type=_evidence_type_for_skill(skill, evidence_ids, joined_by_id),
                    evidence_ids=evidence_ids,
                )
    return sorted(found.values(), key=lambda skill: (skill.category, skill.name.lower()))


def _extract_projects(
    lines: List[str],
    skills: List[SkillEvidence],
    evidence: List[EvidenceItem],
) -> List[Project]:
    projects: List[Project] = []
    skill_by_id: dict[str, list[str]] = {}
    for skill in skills:
        for evidence_id in skill.evidence_ids:
            skill_by_id.setdefault(evidence_id, []).append(skill.name)

    for item in evidence:
        line = item.original_text
        lower = line.lower()
        looks_project = bool(
            re.search(r"\b(?:project|portfolio)\b", lower)
            or re.search(r"\b(?:built|developed|implemented|integrated|created|designed)\b", lower)
        )
        if not looks_project or len(line) < 20:
            continue
        name = _project_name(line)
        projects.append(
            Project(
                name=name,
                description=line,
                technologies=sorted(set(skill_by_id.get(item.evidence_id, []))),
                evidence_ids=[item.evidence_id],
            )
        )

    unique: dict[str, Project] = {}
    for project in projects:
        unique.setdefault(project.name.lower(), project)
    return list(unique.values())[:8]


def _career_themes(
    preferences: CandidatePreferences,
    skills: Iterable[SkillEvidence],
    projects: Iterable[Project],
) -> List[str]:
    themes = {theme.lower() for theme in preferences.career_interests + preferences.target_roles}
    skill_names = {skill.name.lower() for skill in skills}
    project_text = " ".join(project.description.lower() for project in projects)
    if {"pytorch", "tensorflow", "machine learning", "yolo"} & skill_names:
        themes.add("machine learning")
    if {"opencv", "computer vision", "yolo"} & skill_names or "computer vision" in project_text:
        themes.add("computer vision")
    if {"sql", "pandas", "numpy", "power bi"} & skill_names:
        themes.add("data science")
    if {"next.js", "fastapi", "typescript", "java"} & skill_names:
        themes.add("software engineering")
    return sorted(themes)


def _profile_gaps(skills: List[SkillEvidence]) -> List[str]:
    skill_names = {skill.name.lower() for skill in skills}
    gaps = []
    for term in ["AWS", "Kubernetes", "Spark", "Commercial ML experience"]:
        if term.lower() not in skill_names:
            gaps.append(term)
    return gaps


def _guess_section(line: str) -> str:
    lower = line.lower()
    if any(term in lower for term in ["university", "bachelor", "master", "unsw"]):
        return "Education"
    if any(term in lower for term in ["project", "robotics", "engineer", "developer"]):
        return "Projects/Experience"
    if any(term in lower for term in ["python", "sql", "skills", "technologies"]):
        return "Skills"
    return "CV"


def _evidence_type_for_skill(skill: str, evidence_ids: List[str], joined_by_id: dict[str, str]) -> EvidenceType:
    text = " ".join(joined_by_id[evidence_id].lower() for evidence_id in evidence_ids)
    if re.search(r"\b(?:currently learning|currently studying|familiar with|learning about)\b", text):
        return EvidenceType.LEARNING
    if any(term in text for term in ["project", "built", "developed", "implemented"]):
        return EvidenceType.INFERRED_FROM_PROJECT
    return EvidenceType.EXPLICIT


def _project_name(line: str) -> str:
    cleaned = re.sub(r"^[*\-•]\s*", "", line).strip()
    if ":" in cleaned:
        return cleaned.split(":", 1)[0][:80]
    words = cleaned.split()
    return " ".join(words[:8])


def _candidate_name(lines: List[str]) -> str:
    if not lines:
        return "Candidate"
    first = lines[0].strip()
    if (
        1 < len(first.split()) <= 5
        and len(first) <= 80
        and not re.search(r"[@|:/\\]|\d", first)
        and not any(term in first.lower() for term in ["curriculum vitae", "resume", "profile", "summary"])
    ):
        return first
    return "Candidate"
