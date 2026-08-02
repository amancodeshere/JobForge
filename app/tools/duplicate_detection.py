from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from typing import Iterable, List

from app.schemas.job import JobResult
from app.tools.job_normalization import description_tokens, normalize_job


SOURCE_PRIORITY = {
    "greenhouse": 6,
    "lever": 6,
    "ashby": 6,
    "workday": 5,
    "seek": 5,
    "linkedin": 4,
    "indeed": 4,
    "glassdoor": 3,
    "adzuna": 3,
    "remotive": 3,
}


def normalize_key(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def deduplicate_jobs(jobs: Iterable[JobResult]) -> List[JobResult]:
    unique: List[JobResult] = []
    for source_job in jobs:
        job = normalize_job(source_job.model_copy(deep=True))
        duplicate_index = next(
            (index for index, incumbent in enumerate(unique) if jobs_are_duplicates(incumbent, job)),
            None,
        )
        if duplicate_index is None:
            unique.append(job)
        else:
            unique[duplicate_index] = merge_duplicate_jobs(unique[duplicate_index], job)
    return unique


def jobs_are_duplicates(left: JobResult, right: JobResult) -> bool:
    left = normalize_job(left)
    right = normalize_job(right)
    if left.canonical_url and left.canonical_url == right.canonical_url:
        return True

    same_provider = _provider_identity(left.source) == _provider_identity(right.source)
    if same_provider and left.job_id != right.job_id:
        return False
    if not left.canonical_company or left.canonical_company != right.canonical_company:
        return False
    if not _locations_compatible(left.canonical_location, right.canonical_location):
        return False
    if _seniority_conflicts(left.seniority_levels, right.seniority_levels):
        return False

    title_similarity = SequenceMatcher(None, _title_key(left.title), _title_key(right.title)).ratio()
    if title_similarity >= 0.86:
        return True
    if left.description_fingerprint and left.description_fingerprint == right.description_fingerprint:
        return True
    return title_similarity >= 0.72 and _description_similarity(left.description, right.description) >= 0.82


def merge_duplicate_jobs(left: JobResult, right: JobResult) -> JobResult:
    left = normalize_job(left)
    right = normalize_job(right)
    winner, other = max(
        ((left, right), (right, left)),
        key=lambda pair: (_source_priority(pair[0]), len(pair[0].description), _date_key(pair[0].date_posted)),
    )
    merged = winner.model_copy(deep=True)
    merged.description = max((left.description, right.description), key=len)
    merged.date_posted = max(
        (value for value in (left.date_posted, right.date_posted) if value),
        default=None,
    )
    merged.date_found = min(value for value in (left.date_found, right.date_found) if value)
    merged.required_skills = _unique([*left.required_skills, *right.required_skills])
    merged.preferred_skills = _unique([*left.preferred_skills, *right.preferred_skills])
    merged.inferred_skills = _unique([*left.inferred_skills, *right.inferred_skills])
    merged.eligibility_requirements = _unique(
        [*left.eligibility_requirements, *right.eligibility_requirements]
    )
    merged.visa_requirements = _unique([*left.visa_requirements, *right.visa_requirements])
    merged.source_provenance = _unique(
        [*left.source_provenance, left.source, *right.source_provenance, right.source]
    )
    merged.source_job_ids = _unique([*left.source_job_ids, left.job_id, *right.source_job_ids, right.job_id])
    merged.duplicate_count = max(2, left.duplicate_count + right.duplicate_count)
    if not merged.compensation_text and other.compensation_text:
        merged.compensation_text = other.compensation_text
        merged.compensation_min = other.compensation_min
        merged.compensation_max = other.compensation_max
        merged.compensation_currency = other.compensation_currency
    if merged.work_arrangement == "unspecified":
        merged.work_arrangement = other.work_arrangement
    if not merged.contract_duration:
        merged.contract_duration = other.contract_duration
    if not merged.application_deadline:
        merged.application_deadline = other.application_deadline
    return normalize_job(merged, force=True)


def _provider_identity(source: str) -> str:
    normalized = source.lower()
    if normalized.startswith("serpapi:"):
        return normalized.split(":", 1)[1]
    return normalized.split(":", 1)[0]


def _source_priority(job: JobResult) -> int:
    return SOURCE_PRIORITY.get(_provider_identity(job.source), 1)


def _locations_compatible(left: str, right: str) -> bool:
    unknown = {"", "unknown", "unspecified"}
    if left in unknown or right in unknown:
        return True
    if left == right or left in right or right in left:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if "remote" in left_tokens and "remote" in right_tokens:
        return True
    australian_regions = {"sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra", "hobart", "darwin"}
    return bool(left_tokens & right_tokens & australian_regions)


def _seniority_conflicts(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False
    early = {"internship", "graduate", "entry-level", "junior", "associate"}
    advanced = {"senior", "staff", "principal", "manager", "director"}
    return bool(set(left) & early and set(right) & advanced) or bool(set(right) & early and set(left) & advanced)


def _title_key(value: str) -> str:
    return normalize_key(value).replace("developer", "engineer").replace("engineering", "engineer")


def _description_similarity(left: str, right: str) -> float:
    left_tokens = description_tokens(left)
    right_tokens = description_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _date_key(value: str | None) -> date:
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return date.min


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
