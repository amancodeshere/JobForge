from __future__ import annotations

import re
from typing import Iterable, List


EXPERIENCE_LEVELS = [
    "internship",
    "graduate",
    "entry-level",
    "junior",
    "associate",
    "mid-level",
    "senior",
    "staff",
    "principal",
    "manager",
    "director",
]

LEVEL_ALIASES = {
    "entry level": "entry-level",
    "entry-level": "entry-level",
    "intern": "internship",
    "internship": "internship",
    "grad": "graduate",
    "graduate": "graduate",
    "junior": "junior",
    "associate": "associate",
    "mid": "mid-level",
    "mid-level": "mid-level",
    "intermediate": "mid-level",
    "senior": "senior",
    "lead": "senior",
    "staff": "staff",
    "principal": "principal",
    "manager": "manager",
    "director": "director",
}


def normalize_experience_level(level: str) -> str:
    cleaned = re.sub(r"[_\s]+", " ", level.strip().lower())
    return LEVEL_ALIASES.get(cleaned, cleaned.replace(" ", "-"))


def normalize_experience_levels(levels: Iterable[str]) -> List[str]:
    normalized = []
    for level in levels:
        item = normalize_experience_level(level)
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def infer_job_experience_levels(text: str) -> List[str]:
    lowered = text.lower()
    inferred: list[str] = []
    patterns = [
        ("internship", r"\b(?:intern|internship)\b"),
        ("graduate", r"\b(?:graduate|grad)\b"),
        ("entry-level", r"\bentry[-\s]?level\b"),
        ("junior", r"\bjunior\b"),
        ("associate", r"\bassociate\b"),
        ("mid-level", r"\b(?:mid[-\s]?level|intermediate)\b"),
        ("senior", r"\b(?:senior|lead)\b"),
        ("staff", r"\bstaff\b"),
        ("principal", r"\bprincipal\b"),
        ("manager", r"\bmanager\b"),
        ("director", r"\bdirector\b"),
    ]
    for level, pattern in patterns:
        if re.search(pattern, lowered):
            inferred.append(level)
    return inferred


def has_experience_overlap(job_text: str, allowed_levels: Iterable[str]) -> bool:
    inferred = set(infer_job_experience_levels(job_text))
    if not inferred:
        return True
    return bool(inferred & set(normalize_experience_levels(allowed_levels)))

