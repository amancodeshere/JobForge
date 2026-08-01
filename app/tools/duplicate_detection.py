from __future__ import annotations

import re
from typing import Iterable, List

from app.schemas.job import JobResult


def normalize_key(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def deduplicate_jobs(jobs: Iterable[JobResult]) -> List[JobResult]:
    seen: set[tuple[str, str, str]] = set()
    unique: List[JobResult] = []
    for job in jobs:
        key = (
            normalize_key(job.title),
            normalize_key(job.company),
            normalize_key(job.location),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique

