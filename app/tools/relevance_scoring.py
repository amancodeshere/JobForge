from __future__ import annotations

from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Iterable

from app.schemas.application import Recommendation, ScoreBreakdown
from app.schemas.candidate import CandidateProfile, CandidatePreferences
from app.schemas.job import JobResult
from app.tools.experience_levels import infer_job_experience_levels


WEIGHTS = {
    "required_skills": 0.30,
    "preferred_skills": 0.15,
    "experience_level": 0.15,
    "career_interest": 0.15,
    "project_similarity": 0.10,
    "eligibility": 0.10,
    "freshness": 0.05,
}

DOMAIN_TERMS = {
    "ai",
    "api",
    "backend",
    "cloud",
    "computer",
    "containers",
    "data",
    "database",
    "embedded",
    "frontend",
    "graphics",
    "java",
    "javascript",
    "linux",
    "learning",
    "machine",
    "model",
    "opencv",
    "postgresql",
    "python",
    "robotics",
    "ros2",
    "rust",
    "sql",
    "typescript",
    "vision",
    "web",
    "yolo",
    "go",
    "golang",
    "pytorch",
    "fastapi",
}


def calculate_relevance_score(
    profile: CandidateProfile,
    preferences: CandidatePreferences,
    job: JobResult,
    today: date | None = None,
) -> ScoreBreakdown:
    today = today or date.today()
    supported = profile.supported_skill_names()
    components = {
        "required_skills": _skill_match(job.required_skills, supported),
        "preferred_skills": _skill_match(job.preferred_skills, supported),
        "experience_level": _experience_score(job, preferences),
        "career_interest": _interest_score(job, profile, preferences),
        "project_similarity": _project_similarity(job, profile),
        "eligibility": _eligibility_score(job, preferences),
        "freshness": _freshness_score(job, preferences, today),
    }
    overall = round(sum(components[key] * WEIGHTS[key] for key in WEIGHTS))
    return ScoreBreakdown(overall_score=overall, components=components, weights=WEIGHTS)


def recommendation_for(score: int) -> Recommendation:
    if score >= 85:
        return Recommendation.STRONGLY_APPLY
    if score >= 78:
        return Recommendation.APPLY
    if score >= 70:
        return Recommendation.APPLY_WITH_TAILORING
    if score >= 60:
        return Recommendation.POSSIBLE
    return Recommendation.LOWER_PRIORITY


def _skill_match(required: Iterable[str], supported: set[str]) -> int:
    skills = [skill.lower() for skill in required]
    if not skills:
        return 70
    matches = sum(1 for skill in skills if skill in supported)
    partial = sum(1 for skill in skills if skill not in supported and any(_similar(skill, candidate) > 0.82 for candidate in supported))
    return min(100, round(((matches + partial * 0.5) / len(skills)) * 100))


def _experience_score(job: JobResult, preferences: CandidatePreferences) -> int:
    text = f"{job.title} {job.description} {job.experience_required}".lower()
    selected = set(preferences.selected_experience_levels())
    inferred = set(infer_job_experience_levels(text))
    if inferred and inferred & selected:
        return 100
    if inferred:
        return 35
    if "0-2" in text or "0 to 2" in text or "0–2" in text:
        early = {"internship", "graduate", "entry-level", "junior", "associate"}
        return 95 if selected & early else 45
    if "3 years" in text or "3+ years" in text:
        return 75 if selected & {"associate", "mid-level", "senior"} else 30
    return 70


def _interest_score(job: JobResult, profile: CandidateProfile, preferences: CandidatePreferences) -> int:
    interests = [*profile.career_themes, *preferences.career_interests, *preferences.target_roles]
    if not interests:
        return 70
    text = f"{job.title} {job.description}".lower()
    direct = sum(1 for interest in interests if interest.lower() in text)
    if direct:
        return min(100, 65 + direct * 15)
    return max(round(max((_similar(interest.lower(), text) for interest in interests), default=0) * 100), 35)


def _project_similarity(job: JobResult, profile: CandidateProfile) -> int:
    if not profile.projects:
        return 45
    job_text = f"{job.title} {job.description}".lower()
    project_text = " ".join([project.name + " " + project.description + " " + " ".join(project.technologies) for project in profile.projects]).lower()
    job_terms = _domain_tokens(job_text)
    project_terms = _domain_tokens(project_text)
    if not job_terms:
        return 45
    overlap = job_terms & project_terms
    coverage = len(overlap) / len(job_terms)
    return round(20 + coverage * 80)


def _eligibility_score(job: JobResult, preferences: CandidatePreferences) -> int:
    reqs = " ".join(job.eligibility_requirements).lower()
    if not reqs:
        return 100
    rights = (preferences.work_rights or "").lower()
    if "citizen" in reqs and "citizen" not in rights:
        return 20
    if "permanent resident" in reqs and not any(term in rights for term in ["permanent resident", "citizen"]):
        return 45
    return 90


def _freshness_score(job: JobResult, preferences: CandidatePreferences, today: date) -> int:
    posted = _parse_date(job.date_posted or job.date_found)
    if not posted:
        return 60
    age = max(0, (today - posted).days)
    if age <= 7:
        return 100
    if age <= preferences.posted_within_days:
        return max(50, 100 - round((age / preferences.posted_within_days) * 50))
    return 0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _domain_tokens(value: str) -> set[str]:
    import re

    return {
        token
        for token in re.findall(r"[a-z0-9+#.]{2,}", value.lower())
        if token in DOMAIN_TERMS
    }
