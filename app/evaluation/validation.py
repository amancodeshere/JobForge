from __future__ import annotations

from typing import Iterable, List

from app.schemas.application import ApplicationResult, ValidationCheck, WorkflowResult
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobResult, JobStatus


def validate_candidate_profile(profile: CandidateProfile) -> ValidationCheck:
    issues: List[str] = []
    if not profile.verified_evidence:
        issues.append("No verified CV evidence extracted.")
    if not profile.skills:
        issues.append("No skills extracted from CV.")
    for skill in profile.skills:
        if not skill.evidence_ids:
            issues.append(f"Skill lacks evidence mapping: {skill.name}")
    return ValidationCheck(part="candidate_profile", passed=not issues, issues=issues)


def validate_job_pool(jobs: Iterable[JobResult]) -> ValidationCheck:
    issues: List[str] = []
    seen_ids = set()
    validated_count = 0
    for job in jobs:
        if job.job_id in seen_ids:
            issues.append(f"Duplicate job id: {job.job_id}")
        seen_ids.add(job.job_id)
        if not job.application_url:
            issues.append(f"Missing application URL: {job.job_id}")
        if job.status == JobStatus.VALIDATED:
            validated_count += 1
            if not job.description:
                issues.append(f"Validated job has no description: {job.job_id}")
    if validated_count == 0:
        issues.append("No validated jobs.")
    return ValidationCheck(part="job_pool", passed=not issues, issues=issues)


def validate_rankings(applications: Iterable[ApplicationResult]) -> ValidationCheck:
    issues: List[str] = []
    scores = [application.relevance_score for application in applications]
    if scores != sorted(scores, reverse=True):
        issues.append("Applications are not sorted by descending relevance score.")
    for application in applications:
        if application.relevance_score != application.score_breakdown.overall_score:
            issues.append(f"Score mismatch for {application.job_id}.")
    return ValidationCheck(part="ranking", passed=not issues, issues=issues)


def validate_applications(applications: Iterable[ApplicationResult]) -> ValidationCheck:
    issues: List[str] = []
    for application in applications:
        checks = application.quality_checks
        if checks.unsupported_claims:
            issues.append(f"{application.job_id} has unsupported claims.")
        if not checks.company_name_correct:
            issues.append(f"{application.job_id} cover letter company mismatch.")
        if not checks.evidence_grounded:
            issues.append(f"{application.job_id} is not fully evidence grounded.")
    return ValidationCheck(part="applications", passed=not issues, issues=issues)


def validate_dashboard_payload(result: WorkflowResult) -> ValidationCheck:
    issues: List[str] = []
    if result.discovered_count < result.validated_count:
        issues.append("Validated count exceeds discovered count.")
    if result.recommended_count != len(result.applications):
        issues.append("Recommended count does not match application payload.")
    if not result.agent_health:
        issues.append("Agent health timeline is empty.")
    return ValidationCheck(part="dashboard_payload", passed=not issues, issues=issues)

