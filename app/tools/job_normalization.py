from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.schemas.job import JobResult
from app.tools.experience_levels import infer_job_experience_levels


SKILL_TERMS = (
    "Python",
    "C++",
    "SQL",
    "Java",
    "Go",
    "Golang",
    "Rust",
    "TypeScript",
    "JavaScript",
    "React",
    "PyTorch",
    "TensorFlow",
    "Transformers",
    "YOLO",
    "OpenCV",
    "ROS2",
    "FastAPI",
    "Next.js",
    "PostgreSQL",
    "Power BI",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Linux",
    "Kubernetes",
    "Spark",
    "Machine Learning",
    "Computer Vision",
)

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "source",
    "ref",
    "referrer",
    "tracking",
    "trackingid",
    "gh_src",
    "lever-source",
    "type",
    "origin",
}
IDENTITY_QUERY_KEYS = {"jk", "jl", "gh_jid", "jobid", "job_id", "requisitionid", "rid"}


def normalize_job(job: JobResult, *, force: bool = False) -> JobResult:
    """Populate stable identity and structured fields once per normalized record."""

    if job.normalization_version == 1 and not force:
        return job
    text = f"{job.title}\n{job.description}\n{job.experience_required}"
    job.canonical_url = canonicalize_url(job.application_url)
    job.canonical_company = canonical_company(job.company)
    job.canonical_location = canonical_location(job.location)
    job.work_arrangement = extract_work_arrangement(text, job.location)
    compensation = extract_compensation(text)
    if compensation:
        job.compensation_text, job.compensation_min, job.compensation_max, job.compensation_currency = compensation
    job.required_years_min, job.required_years_max = extract_required_years(text)
    job.seniority_levels = infer_job_experience_levels(f"{job.title} {job.experience_required} {job.description}")
    job.visa_requirements = extract_visa_requirements(text)
    job.contract_duration = extract_contract_duration(text)
    job.application_deadline = extract_application_deadline(text)
    job.description_fingerprint = description_fingerprint(job.description)
    job.source_provenance = _unique([*job.source_provenance, job.source])
    job.source_job_ids = _unique([*job.source_job_ids, job.job_id])
    job.duplicate_count = max(1, job.duplicate_count)

    found_skills = extract_skills(text)
    declared = {skill.lower() for skill in [*job.required_skills, *job.preferred_skills]}
    job.inferred_skills = _unique(
        [*job.inferred_skills, *(skill for skill in found_skills if skill.lower() not in declared)]
    )[:12]
    if not job.required_skills and not job.preferred_skills:
        # Preserve the product contract that extracted terms are optional signals,
        # never invented requirements. Ranking can still distinguish them from
        # provider-declared preferred skills through `inferred_skills`.
        job.preferred_skills = list(job.inferred_skills)

    eligibility = " ".join(job.eligibility_requirements).lower()
    for requirement in job.visa_requirements:
        if requirement.lower() not in eligibility:
            job.eligibility_requirements.append(requirement)
            eligibility += f" {requirement.lower()}"
    job.normalization_version = 1
    return job


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return value.strip()
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    retained = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=False):
        lowered = key.lower()
        if lowered in TRACKING_QUERY_KEYS or lowered.startswith(TRACKING_QUERY_PREFIXES):
            continue
        if lowered in IDENTITY_QUERY_KEYS:
            retained.append((lowered, item_value))
    return urlunparse((parsed.scheme.lower(), host + port, path, "", urlencode(sorted(retained)), ""))


def canonical_company(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    normalized = re.sub(
        r"\b(?:pty|proprietary|limited|ltd|incorporated|inc|corporation|corp|company|co|group|holdings)\b",
        " ",
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def canonical_location(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    aliases = {
        "new south wales": "nsw",
        "victoria": "vic",
        "queensland": "qld",
        "australian capital territory": "act",
        "south australia": "sa",
        "western australia": "wa",
        "tasmania": "tas",
        "northern territory": "nt",
    }
    for source, target in aliases.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
    if "remote" in normalized and "australia" not in normalized:
        normalized = f"remote australia {normalized}"
    return re.sub(r"\s+", " ", normalized).strip()


def extract_work_arrangement(text: str, location: str) -> str:
    lowered = f"{text} {location}".lower()
    if re.search(r"\bhybrid\b", lowered):
        return "hybrid"
    if re.search(r"\b(?:remote|work from home|wfh)\b", lowered):
        return "remote"
    if re.search(r"\b(?:on[ -]?site|in office|office-based)\b", lowered):
        return "on-site"
    return "unspecified"


def extract_compensation(text: str) -> tuple[str, int, int, str] | None:
    pattern = re.compile(
        r"(?P<currency>A\$|AUD\s*\$?|\$)\s*(?P<low>\d{2,3}(?:,\d{3})?|\d{2,3})\s*(?P<low_k>[kK])?"
        r"\s*(?:-|–|—|to)\s*(?:A\$|AUD\s*\$?|\$)?\s*(?P<high>\d{2,3}(?:,\d{3})?|\d{2,3})\s*(?P<high_k>[kK])?"
    )
    match = pattern.search(text)
    if not match:
        return None
    low = _money_value(match.group("low"), bool(match.group("low_k")))
    high = _money_value(match.group("high"), bool(match.group("high_k")))
    if low > high:
        low, high = high, low
    currency = "AUD" if match.group("currency").upper().startswith(("A$", "AUD")) else "unspecified"
    return match.group(0), low, high, currency


def extract_required_years(text: str) -> tuple[int | None, int | None]:
    ranges = re.findall(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s*(?:years|yrs)", text, flags=re.IGNORECASE)
    if ranges:
        low, high = min((int(low), int(high)) for low, high in ranges)
        return low, high
    values = [int(value) for value in re.findall(r"(\d+)\+?\s*(?:years|yrs)", text, flags=re.IGNORECASE)]
    return (min(values), None) if values else (None, None)


def extract_visa_requirements(text: str) -> list[str]:
    lowered = text.lower()
    requirements: list[str] = []
    if re.search(r"\b(?:australian citizen|australian citizenship)\b", lowered):
        requirements.append("Australian citizenship required")
    elif re.search(r"\b(?:permanent resident|permanent residency)\b", lowered):
        requirements.append("Australian permanent residency or citizenship required")
    if re.search(r"\b(?:no|without)\s+(?:visa\s+)?sponsorship\b|\bsponsorship (?:is )?not available\b", lowered):
        requirements.append("Visa sponsorship unavailable")
    return requirements


def extract_contract_duration(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2})[ -]?(month|week)s?\s+(?:fixed[ -]term|contract)\b", text, re.IGNORECASE)
    if not match:
        match = re.search(r"\b(?:fixed[ -]term|contract)\s+(?:for\s+)?(\d{1,2})\s+(month|week)s?\b", text, re.IGNORECASE)
    return f"{match.group(1)} {match.group(2).lower()}s" if match else None


def extract_application_deadline(text: str) -> str | None:
    match = re.search(
        r"(?:applications? close|closing date|apply by)\s*:?[ ]*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1)
    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def extract_skills(text: str) -> list[str]:
    return [
        skill
        for skill in SKILL_TERMS
        if re.search(rf"(?<![A-Za-z0-9+#]){re.escape(skill)}(?![A-Za-z0-9+#])", text, re.IGNORECASE)
    ]


def description_fingerprint(value: str) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9+#.]{2,}", value.lower()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24] if normalized else ""


def description_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]{3,}", value.lower()))


def _money_value(value: str, explicit_k: bool) -> int:
    amount = int(value.replace(",", ""))
    return amount * 1000 if explicit_k or amount < 1000 else amount


def _unique(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(value.strip())
    return unique
