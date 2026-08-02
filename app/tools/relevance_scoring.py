from __future__ import annotations

from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Iterable

from app.schemas.application import Recommendation, ScoreBreakdown
from app.schemas.candidate import CandidateProfile, CandidatePreferences
from app.schemas.job import JobResult
from app.tools.experience_levels import infer_job_experience_levels
from app.tools.job_normalization import canonical_company, canonical_location, normalize_job
from app.tools.query_planner import normalize_role, role_family, role_match_score


WEIGHTS = {
    "role_compatibility": 0.18,
    "required_skills": 0.20,
    "preferred_skills": 0.10,
    "experience_level": 0.12,
    "career_interest": 0.10,
    "project_similarity": 0.08,
    "eligibility": 0.08,
    "location": 0.05,
    "work_arrangement": 0.03,
    "compensation": 0.02,
    "company_industry": 0.01,
    "source_quality": 0.02,
    "freshness": 0.01,
}

TRANSFERABLE_SKILLS = {
    "javascript": {"typescript": 0.8},
    "typescript": {"javascript": 0.8},
    "pytorch": {"tensorflow": 0.65},
    "tensorflow": {"pytorch": 0.65},
    "sql": {"postgresql": 0.8},
    "postgresql": {"sql": 0.8},
    "docker": {"kubernetes": 0.6},
    "kubernetes": {"docker": 0.6},
    "go": {"golang": 1.0},
    "golang": {"go": 1.0},
    "opencv": {"computer vision": 0.7},
    "computer vision": {"opencv": 0.7},
}

DOMAIN_TERMS = {
    "ai", "api", "backend", "cloud", "computer", "containers", "data", "database", "embedded",
    "frontend", "graphics", "java", "javascript", "linux", "learning", "machine", "model", "opencv",
    "postgresql", "python", "robotics", "ros2", "rust", "sql", "typescript", "vision", "web", "yolo",
    "go", "golang", "pytorch", "fastapi", "docker", "kubernetes", "react", "spark",
}


def calculate_relevance_score(
    profile: CandidateProfile,
    preferences: CandidatePreferences,
    job: JobResult,
    today: date | None = None,
) -> ScoreBreakdown:
    today = today or date.today()
    job = normalize_job(job)
    supported = profile.supported_skill_names()
    components = {
        "role_compatibility": _role_score(job, profile, preferences),
        "required_skills": _skill_match(job.required_skills, supported),
        "preferred_skills": _skill_match(_declared_preferred_skills(job), supported),
        "experience_level": _experience_score(job, preferences),
        "career_interest": _interest_score(job, profile, preferences),
        "project_similarity": _project_similarity(job, profile),
        "eligibility": _eligibility_score(job, preferences),
        "location": _location_score(job, preferences),
        "work_arrangement": _work_arrangement_score(job, preferences),
        "compensation": _compensation_score(job, preferences),
        "company_industry": _company_industry_score(job, preferences),
        "source_quality": _source_quality_score(job),
        "freshness": _freshness_score(job, preferences, today),
    }
    overall = round(sum(components[key] * WEIGHTS[key] for key in WEIGHTS))
    return ScoreBreakdown(overall_score=overall, base_score=overall, components=components, weights=WEIGHTS)


def calculate_candidate_score(
    profile: CandidateProfile,
    preferences: CandidatePreferences,
    job: JobResult,
) -> int:
    """Cheap first-stage score used to bound the richer reranking pass."""

    supported = profile.supported_skill_names()
    skills = [*job.required_skills, *job.preferred_skills, *job.inferred_skills]
    skill_score = _skill_match(skills, supported)
    return round(
        _role_score(job, profile, preferences) * 0.45
        + skill_score * 0.25
        + _experience_score(job, preferences) * 0.20
        + _location_score(job, preferences) * 0.10
    )


def rank_jobs(
    profile: CandidateProfile,
    preferences: CandidatePreferences,
    jobs: Iterable[JobResult],
    *,
    today: date | None = None,
    candidate_limit: int = 50,
    result_limit: int | None = None,
    confidence_floor: int = 42,
    result_floor: int = 62,
) -> list[tuple[JobResult, ScoreBreakdown]]:
    today = today or date.today()
    normalized = [normalize_job(job) for job in jobs]
    candidates = sorted(
        ((job, calculate_candidate_score(profile, preferences, job)) for job in normalized),
        key=lambda item: (item[1], item[0].date_posted or "", item[0].job_id),
        reverse=True,
    )
    bounded = [item for item in candidates[: max(1, candidate_limit)] if item[1] >= confidence_floor]
    fully_scored = [
        (job, calculate_relevance_score(profile, preferences, job, today=today))
        for job, _candidate_score in bounded
    ]
    fully_scored = [item for item in fully_scored if item[1].overall_score >= result_floor]
    ranked = _diversity_rerank(fully_scored, limit=result_limit)
    return ranked


def rank_jobs_v1(
    profile: CandidateProfile,
    preferences: CandidatePreferences,
    jobs: Iterable[JobResult],
    *,
    today: date | None = None,
    result_limit: int | None = None,
    result_floor: int = 62,
) -> list[tuple[JobResult, ScoreBreakdown]]:
    """Stable control ranker retained for canary rollback and shadow evaluation."""

    today = today or date.today()
    scored = [
        (job, calculate_relevance_score(profile, preferences, job, today=today))
        for job in (normalize_job(item) for item in jobs)
    ]
    scored = [item for item in scored if item[1].overall_score >= result_floor]
    scored.sort(
        key=lambda item: (item[1].overall_score, item[0].date_posted or "", item[0].job_id),
        reverse=True,
    )
    return scored[:result_limit] if result_limit is not None else scored


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


def _role_score(job: JobResult, profile: CandidateProfile, preferences: CandidatePreferences) -> int:
    roles = [*preferences.target_roles, *profile.target_roles]
    if not roles:
        return 70
    score = max((role_match_score(role, job.title) for role in roles), default=0.0)
    return max(15, round(score * 100))


def _skill_match(required: Iterable[str], supported: set[str]) -> int:
    skills = [skill.lower() for skill in required]
    if not skills:
        return 50
    credit = 0.0
    for skill in skills:
        if skill in supported:
            credit += 1.0
            continue
        transfer = max(
            (TRANSFERABLE_SKILLS.get(skill, {}).get(candidate, 0.0) for candidate in supported),
            default=0.0,
        )
        if not transfer:
            transfer = max((_similar(skill, candidate) * 0.5 for candidate in supported if _similar(skill, candidate) > 0.82), default=0.0)
        credit += transfer
    return min(100, round((credit / len(skills)) * 100))


def _declared_preferred_skills(job: JobResult) -> list[str]:
    inferred = {skill.lower() for skill in job.inferred_skills}
    return [skill for skill in job.preferred_skills if skill.lower() not in inferred]


def _experience_score(job: JobResult, preferences: CandidatePreferences) -> int:
    if job.required_years_min is not None and job.required_years_min > preferences.max_years_experience:
        return 0
    text = f"{job.title} {job.description} {job.experience_required}".lower()
    selected = set(preferences.selected_experience_levels())
    inferred = set(job.seniority_levels or infer_job_experience_levels(text))
    if inferred and inferred & selected:
        return 100
    if inferred:
        return 25
    return 70


def _interest_score(job: JobResult, profile: CandidateProfile, preferences: CandidatePreferences) -> int:
    interests = [*profile.career_themes, *preferences.career_interests]
    if not interests:
        return 70
    text = f"{job.title} {job.description}".lower()
    direct = sum(1 for interest in interests if interest.lower() in text)
    if direct:
        return min(100, 65 + direct * 15)
    role_scores = [role_match_score(interest, job.title) for interest in interests]
    return max(30, round(max(role_scores, default=0.0) * 100))


def _project_similarity(job: JobResult, profile: CandidateProfile) -> int:
    if not profile.projects:
        return 45
    job_text = f"{job.title} {job.description}".lower()
    project_text = " ".join(
        project.name + " " + project.description + " " + " ".join(project.technologies)
        for project in profile.projects
    ).lower()
    job_terms = _domain_tokens(job_text)
    project_terms = _domain_tokens(project_text)
    if not job_terms:
        return 45
    return round(20 + (len(job_terms & project_terms) / len(job_terms)) * 80)


def _eligibility_score(job: JobResult, preferences: CandidatePreferences) -> int:
    reqs = " ".join([*job.eligibility_requirements, *job.visa_requirements]).lower()
    if not reqs:
        return 100
    rights = (preferences.work_rights or "").lower()
    if "citizen" in reqs and "citizen" not in rights:
        return 0
    if "permanent resident" in reqs and not any(term in rights for term in ["permanent resident", "citizen"]):
        return 25
    if "sponsorship unavailable" in reqs and "sponsorship" in rights:
        return 20
    return 90


def _location_score(job: JobResult, preferences: CandidatePreferences) -> int:
    if not preferences.locations:
        return 80
    job_location = job.canonical_location or canonical_location(job.location)
    targets = [canonical_location(value) for value in preferences.locations]
    if not job_location or job_location in {"unknown", "unspecified"}:
        return 60
    if any(job_location in target or target in job_location for target in targets):
        return 100
    if "remote" in job_location and any("australia" in target or "remote" in target for target in targets):
        return 95
    return 20


def _work_arrangement_score(job: JobResult, preferences: CandidatePreferences) -> int:
    selected = {value.strip().lower() for value in preferences.work_arrangements if value.strip()}
    if not selected:
        return 75
    if job.work_arrangement == "unspecified":
        return 55
    return 100 if job.work_arrangement.lower() in selected else 20


def _compensation_score(job: JobResult, preferences: CandidatePreferences) -> int:
    if preferences.salary_min is None:
        return 70
    if job.compensation_max is None:
        return 50
    if job.compensation_max >= preferences.salary_min:
        return 100
    return max(0, round((job.compensation_max / max(1, preferences.salary_min)) * 100))


def _company_industry_score(job: JobResult, preferences: CandidatePreferences) -> int:
    companies = {canonical_company(value) for value in preferences.preferred_companies}
    industries = {value.strip().lower() for value in preferences.preferred_industries}
    if not companies and not industries:
        return 70
    if companies and job.canonical_company in companies:
        return 100
    if industries and (job.industry or "").lower() in industries:
        return 100
    return 45


def _source_quality_score(job: JobResult) -> int:
    provider = job.source.lower().split(":", 1)[0]
    provider_score = {
        "greenhouse": 100, "lever": 100, "ashby": 100, "workday": 95, "seek": 95,
        "linkedin": 90, "indeed": 90, "adzuna": 82, "remotive": 82, "serpapi": 78,
    }.get(provider, 70)
    completeness = min(100, 35 + len(job.description) // 20)
    return round(provider_score * 0.7 + completeness * 0.3)


def _freshness_score(job: JobResult, preferences: CandidatePreferences, today: date) -> int:
    posted = _parse_date(job.date_posted or job.date_found)
    if not posted:
        return 55
    age = max(0, (today - posted).days)
    if age <= 7:
        return 100
    if age <= preferences.posted_within_days:
        return max(50, 100 - round((age / preferences.posted_within_days) * 50))
    return 0


def _diversity_rerank(
    scored_jobs: list[tuple[JobResult, ScoreBreakdown]],
    *,
    limit: int | None,
) -> list[tuple[JobResult, ScoreBreakdown]]:
    remaining = list(scored_jobs)
    selected: list[tuple[JobResult, ScoreBreakdown]] = []
    company_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    target_count = min(len(remaining), limit if limit is not None else len(remaining))

    while remaining and len(selected) < target_count:
        alternatives = [
            item for item in remaining
            if company_counts.get(item[0].canonical_company, 0) < 2
            and family_counts.get(_job_family(item[0]), 0) < 3
        ]
        pool = alternatives or remaining

        def adjusted(item: tuple[JobResult, ScoreBreakdown]) -> tuple[int, str, str]:
            job, score = item
            company_penalty = company_counts.get(job.canonical_company, 0) * 8
            family_penalty = family_counts.get(_job_family(job), 0) * 3
            return (score.overall_score - company_penalty - family_penalty, job.date_posted or "", job.job_id)

        chosen = max(pool, key=adjusted)
        remaining.remove(chosen)
        job, base = chosen
        company_penalty = company_counts.get(job.canonical_company, 0) * 8
        family_penalty = family_counts.get(_job_family(job), 0) * 3
        score = base.model_copy(deep=True)
        score.base_score = base.overall_score
        score.rerank_adjustments = {
            "company_diversity": -company_penalty,
            "role_diversity": -family_penalty,
        }
        score.overall_score = max(0, base.overall_score - company_penalty - family_penalty)
        selected.append((job, score))
        company_counts[job.canonical_company] = company_counts.get(job.canonical_company, 0) + 1
        family = _job_family(job)
        family_counts[family] = family_counts.get(family, 0) + 1
    return selected


def _job_family(job: JobResult) -> str:
    family = role_family(job.title)
    return family.canonical if family else normalize_role(job.title)


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

    return {token for token in re.findall(r"[a-z0-9+#.]{2,}", value.lower()) if token in DOMAIN_TERMS}
