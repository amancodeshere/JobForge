from __future__ import annotations

from datetime import date

from app.schemas.application import ApplicationResult, MatchingEvidence, TailoredStatement
from app.schemas.candidate import CandidateProfile, CandidatePreferences
from app.schemas.job import JobResult
from app.tools.evidence_validator import validate_application_grounding
from app.tools.llm_client import generate_application_copy
from app.tools.relevance_scoring import calculate_relevance_score, recommendation_for


class ApplicationTailorAgent:
    name = "application_tailor"

    def __init__(self) -> None:
        self.llm_attempts = 0
        self.llm_successes = 0
        self.llm_errors = 0
        self.notes: list[str] = []

    def run(
        self,
        profile: CandidateProfile,
        preferences: CandidatePreferences,
        job: JobResult,
        today: date | None = None,
    ) -> ApplicationResult:
        score = calculate_relevance_score(profile, preferences, job, today=today)
        matching = _matching_evidence(profile, job)
        gaps = _skill_gaps(profile, job)
        statements = _tailored_statements(profile, matching)
        tailored_cv = _tailored_cv(profile, job, statements, gaps)
        cover_letter = _cover_letter(profile, job, matching, gaps)
        generation_source = "deterministic"
        llm_result = generate_application_copy(profile, job, matching, gaps, statements)
        if llm_result.attempted:
            self.llm_attempts += 1
        if llm_result.error_message:
            self.llm_errors += 1
            self.notes.append(f"{job.job_id}: {llm_result.error_type}: {llm_result.error_message}")
        if llm_result.application_copy:
            candidate_application = _build_application(
                job=job,
                score=score,
                matching=matching,
                gaps=gaps,
                tailored_cv=llm_result.application_copy.tailored_cv,
                tailored_statements=llm_result.application_copy.tailored_statements,
                cover_letter=llm_result.application_copy.cover_letter,
                topics=_interview_topics(job, gaps),
                generation_source="openai",
            )
            candidate_application.quality_checks = validate_application_grounding(candidate_application, profile)
            if _can_accept_llm_copy(candidate_application):
                tailored_cv = llm_result.application_copy.tailored_cv
                cover_letter = llm_result.application_copy.cover_letter
                statements = llm_result.application_copy.tailored_statements
                generation_source = "openai"
                self.llm_successes += 1
            else:
                self.llm_errors += 1
                self.notes.append(f"{job.job_id}: OpenAI copy rejected by evidence validation.")
        topics = _interview_topics(job, gaps)
        application = _build_application(
            job=job,
            score=score,
            matching=matching,
            gaps=gaps,
            tailored_cv=tailored_cv,
            tailored_statements=statements,
            cover_letter=cover_letter,
            topics=topics,
            generation_source=generation_source,
        )
        application.quality_checks = validate_application_grounding(application, profile)
        return application


def _build_application(
    job: JobResult,
    score,
    matching: list[MatchingEvidence],
    gaps: list[str],
    tailored_cv: str,
    tailored_statements: list[TailoredStatement],
    cover_letter: str,
    topics: list[str],
    generation_source: str,
) -> ApplicationResult:
    return ApplicationResult(
        job_id=job.job_id,
        job=job,
        relevance_score=score.overall_score,
        score_breakdown=score,
        recommendation=recommendation_for(score.overall_score),
        job_summary=_job_summary(job),
        matching_evidence=matching,
        skill_gaps=gaps,
        tailored_cv=tailored_cv,
        tailored_statements=tailored_statements,
        cover_letter=cover_letter,
        interview_preparation_topics=topics,
        generation_source=generation_source,
        quality_checks=validate_application_grounding_stub(),
    )


def _can_accept_llm_copy(application: ApplicationResult) -> bool:
    checks = application.quality_checks
    return (
        checks.unsupported_claims == 0
        and checks.company_name_correct
        and checks.evidence_grounded
        and bool(application.tailored_statements)
    )


def validate_application_grounding_stub():
    from app.schemas.application import QualityChecks

    return QualityChecks()


def _matching_evidence(profile: CandidateProfile, job: JobResult) -> list[MatchingEvidence]:
    evidence_by_id = profile.evidence_by_id()
    skill_map = {skill.name.lower(): skill for skill in profile.skills}
    matches: list[MatchingEvidence] = []
    for requirement in [*job.required_skills, *job.preferred_skills]:
        skill = skill_map.get(requirement.lower())
        if not skill:
            continue
        evidence_text = "; ".join(evidence_by_id[eid].original_text for eid in skill.evidence_ids if eid in evidence_by_id)
        matches.append(
            MatchingEvidence(
                requirement=requirement,
                candidate_evidence=evidence_text,
                evidence_ids=skill.evidence_ids,
            )
        )
    return matches


def _skill_gaps(profile: CandidateProfile, job: JobResult) -> list[str]:
    supported = profile.supported_skill_names()
    gaps = [skill for skill in [*job.required_skills, *job.preferred_skills] if skill.lower() not in supported]
    return sorted(set(gaps))


def _tailored_statements(profile: CandidateProfile, matching: list[MatchingEvidence]) -> list[TailoredStatement]:
    statements: list[TailoredStatement] = []
    used_ids: set[str] = set()
    for match in matching[:5]:
        if not match.evidence_ids:
            continue
        primary_id = match.evidence_ids[0]
        if primary_id in used_ids:
            continue
        used_ids.add(primary_id)
        source = profile.evidence_by_id().get(primary_id)
        if not source:
            continue
        statements.append(
            TailoredStatement(
                tailored_bullet=f"Applied {match.requirement} in work evidenced by: {source.original_text}",
                evidence_ids=[primary_id],
            )
        )
    return statements


def _tailored_cv(
    profile: CandidateProfile,
    job: JobResult,
    statements: list[TailoredStatement],
    gaps: list[str],
) -> str:
    supported_skills = ", ".join(skill.name for skill in profile.skills[:14])
    target_summary = (
        f"Graduate software engineering candidate targeting {job.title} roles, with CV-backed evidence in "
        f"{supported_skills or 'relevant technical projects'}."
    )
    bullet_text = "\n".join(f"- {statement.tailored_bullet}" for statement in statements) or "- Relevant CV evidence is limited; use original CV content."
    gap_text = ", ".join(gaps) if gaps else "No major listed skill gaps identified from the job description."
    return "\n".join(
        [
            "# Tailored CV Draft",
            "",
            "## Targeted Profile",
            target_summary,
            "",
            "## Relevant Skills",
            supported_skills or "No supported technical skills extracted.",
            "",
            "## Selected Evidence-Based Highlights",
            bullet_text,
            "",
            "## Gaps To Avoid Overclaiming",
            gap_text,
        ]
    )


def _cover_letter(
    profile: CandidateProfile,
    job: JobResult,
    matching: list[MatchingEvidence],
    gaps: list[str],
) -> str:
    evidence_sentence = " ".join(
        f"My CV shows {match.requirement} through {match.candidate_evidence}."
        for match in matching[:3]
        if match.candidate_evidence
    )
    if not evidence_sentence:
        evidence_sentence = "My CV shows adjacent technical project work relevant to the role."
    gap_sentence = ""
    if gaps:
        gap_sentence = f" I would treat {', '.join(gaps[:3])} as early ramp-up areas rather than overstate them."
    return (
        f"Dear {job.company} hiring team,\n\n"
        f"I am applying for the {job.title} role because it aligns with my interest in "
        f"{', '.join(profile.career_themes[:3]) or 'software and AI engineering'} and my graduate-level background. "
        f"{evidence_sentence}{gap_sentence}\n\n"
        f"I would welcome the chance to contribute careful engineering work to {job.company} while continuing to build depth in the technologies used by the team.\n\n"
        "Kind regards,\nAman Sharma"
    )


def _job_summary(job: JobResult) -> str:
    skills = ", ".join(job.required_skills[:5]) or "the listed technical requirements"
    return f"{job.title} at {job.company} in {job.location}. The role emphasizes {skills}."


def _interview_topics(job: JobResult, gaps: list[str]) -> list[str]:
    topics = [f"Refresh {skill}" for skill in job.required_skills[:4]]
    topics.extend(f"Prepare honest gap explanation for {gap}" for gap in gaps[:3])
    return topics or ["Prepare examples from CV projects", "Review role responsibilities"]
