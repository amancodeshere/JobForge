from __future__ import annotations

import re
from typing import List

from app.schemas.application import ApplicationResult, QualityChecks
from app.schemas.candidate import CandidateProfile


HIGH_RISK_UNSUPPORTED_TERMS = [
    "kubernetes",
    "spark",
    "aws",
    "commercial ml",
    "production cloud",
]

EXPERIENCE_OVERCLAIM_PATTERNS = [
    r"\b[3-9]\+?\s*(?:years|yrs)\b",
    r"\b\d{2,}\+?\s*(?:years|yrs)\b",
    r"\bsenior\b",
    r"\blead\b",
]


def validate_application_grounding(application: ApplicationResult, profile: CandidateProfile) -> QualityChecks:
    issues: List[str] = []
    evidence_ids = set(profile.evidence_by_id())
    unsupported = 0

    body = f"{application.tailored_cv}\n{application.cover_letter}".lower()
    for statement in application.tailored_statements:
        if not statement.evidence_ids:
            unsupported += 1
            issues.append(f"Tailored statement lacks evidence: {statement.tailored_bullet}")
        missing_ids = [item for item in statement.evidence_ids if item not in evidence_ids]
        if missing_ids:
            unsupported += len(missing_ids)
            issues.append(f"Unknown evidence ids: {', '.join(missing_ids)}")

        if statement.tailored_bullet and statement.tailored_bullet.lower() not in body:
            unsupported += 1
            issues.append(f"Tailored statement not present in generated documents: {statement.tailored_bullet}")

    supported_skills = profile.supported_skill_names()
    gap_terms = {gap.lower() for gap in application.skill_gaps}
    for term in HIGH_RISK_UNSUPPORTED_TERMS:
        if _claims_skill(body, term) and term not in supported_skills and term not in gap_terms:
            unsupported += 1
            issues.append(f"Potential unsupported claim: {term}")

    for term in gap_terms:
        if _claims_skill(body, term):
            unsupported += 1
            issues.append(f"Gap appears claimed as experience: {term}")

    for pattern in EXPERIENCE_OVERCLAIM_PATTERNS:
        if re.search(pattern, body):
            unsupported += 1
            issues.append("Potential experience-level overclaim.")
            break

    company_name_correct = application.job.company.lower() in application.cover_letter.lower()
    if not company_name_correct:
        issues.append("Cover letter does not mention the correct company.")

    return QualityChecks(
        unsupported_claims=unsupported,
        company_name_correct=company_name_correct,
        evidence_grounded=unsupported == 0,
        job_eligible=not application.job.rejection_reasons,
        score_explained=bool(application.score_breakdown.components),
        issues=issues,
    )


def _claims_skill(body: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    claim_patterns = [
        rf"\b(?:experience|experienced|proficient|skilled|built|developed|implemented|deployed|managed|used|using)\b[^.\n]*\b{escaped}\b",
        rf"\b{escaped}\b[^.\n]*\b(?:experience|proficiency|implementation|deployment)\b",
    ]
    return any(re.search(pattern, body) for pattern in claim_patterns)
