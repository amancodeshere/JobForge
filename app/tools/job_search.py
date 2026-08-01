from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urlparse

from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.schemas.job import JobResult, JobStatus
from app.tools.experience_levels import has_experience_overlap


SKILL_TERMS = [
    "Python",
    "C++",
    "SQL",
    "Java",
    "Go",
    "Golang",
    "Rust",
    "TypeScript",
    "PyTorch",
    "TensorFlow",
    "Transformers",
    "YOLO",
    "OpenCV",
    "ROS2",
    "FastAPI",
    "Next.js",
    "PostgreSQL",
    "AWS",
    "Docker",
    "Linux",
    "Kubernetes",
    "Spark",
    "Machine Learning",
    "Computer Vision",
]


def load_jobs_from_json(path: str) -> List[JobResult]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [JobResult.model_validate(item) for item in payload]


def search_sample_jobs(path: str, queries: Iterable[str]) -> List[JobResult]:
    jobs = load_jobs_from_json(path)
    query_terms = {term.lower() for query in queries for term in re.findall(r"[A-Za-z0-9+#.]+", query)}
    scored: list[tuple[int, JobResult]] = []
    for job in jobs:
        haystack = " ".join([job.title, job.company, job.location, job.description]).lower()
        score = sum(1 for term in query_terms if term in haystack)
        if score:
            scored.append((score, job))
    return [job for _, job in sorted(scored, key=lambda pair: pair[0], reverse=True)]


def broad_queries(preferences: CandidatePreferences) -> List[str]:
    locations = preferences.locations or ["Australia"]
    roles = preferences.target_roles or preferences.career_interests or ["graduate software engineer"]
    levels = preferences.selected_experience_levels()
    queries = []
    for role in roles[:5]:
        for location in locations[:2]:
            for level in levels[:4]:
                queries.append(f"{level} {role} {location}")
    queries.extend(
        [
            "entry-level data scientist Australia",
            "AI engineering internship remote Australia",
            "software engineer computer vision graduate",
        ]
    )
    return queries


def targeted_queries(profile: CandidateProfile) -> List[str]:
    skills = [skill.name for skill in profile.skills[:8]]
    locations = profile.locations or ["Australia"]
    themes = profile.career_themes or profile.target_roles or ["software engineer"]
    levels = profile.experience_levels or [profile.experience_level]
    queries = []
    for theme in themes[:4]:
        selected = " ".join(skills[:4])
        for level in levels[:3]:
            queries.append(f"{level} {theme} {selected} {locations[0]}")
    if {"python", "c++", "opencv"} & profile.supported_skill_names():
        queries.append("graduate computer vision engineer Python C++ Sydney")
    if "ros2" in profile.supported_skill_names():
        queries.append("graduate robotics software engineer ROS2 C++ Australia")
    return queries


def enrich_job_skills(job: JobResult) -> JobResult:
    text = f"{job.title}\n{job.description}"
    found = []
    for skill in SKILL_TERMS:
        if re.search(rf"(?<![A-Za-z0-9+#.]){re.escape(skill)}(?![A-Za-z0-9+#.])", text, re.IGNORECASE):
            found.append(skill)
    if not job.required_skills and not job.preferred_skills:
        # A provider description rarely distinguishes required from preferred skills
        # reliably. Treat inferred terms as preferred rather than inventing hard requirements.
        job.preferred_skills = found[:8]
    elif not job.preferred_skills:
        job.preferred_skills = [skill for skill in found if skill not in job.required_skills][:8]
    if not job.eligibility_requirements:
        lowered = text.lower()
        if re.search(r"\b(?:australian citizenship|australian citizen)\b", lowered):
            job.eligibility_requirements.append("Australian citizenship required")
        elif re.search(r"\b(?:permanent resident|permanent residency)\b", lowered):
            job.eligibility_requirements.append("Australian permanent residency or citizenship required")
    return job


def validate_job(job: JobResult, preferences: CandidatePreferences, today: date | None = None) -> JobResult:
    today = today or date.today()
    job = enrich_job_skills(job)
    reasons: list[str] = []
    text = f"{job.title} {job.description} {job.experience_required}".lower()
    level_text = f"{job.title} {job.experience_required}".lower()

    if not has_experience_overlap(level_text, preferences.selected_experience_levels()):
        reasons.append("Role experience level does not match preferences.")

    years = [int(value) for value in re.findall(r"(\d+)\+?\s*(?:years|yrs)", text)]
    if years and min(years) > preferences.max_years_experience:
        reasons.append(f"Requires more than {preferences.max_years_experience} years of experience.")

    if preferences.employment_types and job.employment_type.lower() not in {item.lower() for item in preferences.employment_types}:
        reasons.append("Employment type does not match preferences.")

    if preferences.locations and not _location_matches(job.location, preferences.locations):
        reasons.append("Location does not match preferences.")

    excluded_companies = {value.strip().lower() for value in preferences.excluded_companies if value.strip()}
    if job.company.strip().lower() in excluded_companies:
        reasons.append("Company is excluded by candidate preferences.")

    excluded_keywords = {value.strip().lower() for value in preferences.excluded_keywords if value.strip()}
    matched_keywords = sorted(keyword for keyword in excluded_keywords if keyword in text)
    if matched_keywords:
        reasons.append(f"Contains excluded keyword: {', '.join(matched_keywords)}.")

    posted = _parse_date(job.date_posted or job.date_found)
    if posted and (today - posted).days > preferences.posted_within_days:
        reasons.append(f"Posted more than {preferences.posted_within_days} days ago.")

    if not job.description.strip():
        reasons.append("Missing job description.")

    parsed_url = urlparse(job.application_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        reasons.append("Application URL is not a valid HTTP(S) link.")

    eligibility_text = " ".join(job.eligibility_requirements).lower()
    work_rights = (preferences.work_rights or "").lower()
    if "citizen" in eligibility_text and "citizen" not in work_rights:
        reasons.append("Requires Australian citizenship.")
    elif "permanent resident" in eligibility_text and not any(term in work_rights for term in ["permanent resident", "citizen"]):
        reasons.append("Requires Australian permanent residency or citizenship.")

    if reasons:
        job.status = JobStatus.REJECTED
        job.rejection_reasons = reasons
    else:
        job.status = JobStatus.VALIDATED
        job.rejection_reasons = []
    return job


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _location_matches(job_location: str, preferred_locations: Iterable[str]) -> bool:
    job = _normalize_location(job_location)
    if not job or job in {"unspecified", "unknown"}:
        return True
    worldwide = {"worldwide", "anywhere", "global", "remote"}
    if job in worldwide or any(term in job for term in ["worldwide", "anywhere"]):
        return True
    for preferred in preferred_locations:
        target = _normalize_location(preferred)
        if not target:
            continue
        if job in target or target in job:
            return True
        if "australia" in target and any(term in job for term in ["australia", "australian", "apac"]):
            return True
    return False


def _normalize_location(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
