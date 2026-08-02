from __future__ import annotations

from collections import Counter
from datetime import date

from app.schemas.candidate import CandidatePreferences, CandidateProfile, EvidenceType, SkillEvidence
from app.schemas.job import JobResult
from app.tools.job_normalization import normalize_job
from app.tools.relevance_scoring import calculate_relevance_score, rank_jobs


def test_two_stage_ranker_bounds_full_scoring_to_fifty_candidates(monkeypatch):
    from app.tools import relevance_scoring

    calls = 0
    original = relevance_scoring.calculate_relevance_score

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(relevance_scoring, "calculate_relevance_score", counted)
    jobs = [_job(index, company=f"Company {index}") for index in range(60)]

    ranked = rank_jobs(_profile(), _preferences(), jobs, candidate_limit=50, result_floor=0)

    assert calls == 50
    assert len(ranked) == 50


def test_diversity_reranker_prevents_one_company_or_role_from_dominating_top_ten():
    jobs = [
        _job(index, company="Acme", title="Software Engineer", required_skills=["Python"])
        for index in range(6)
    ]
    jobs.extend(
        _job(index + 10, company=f"Alternative {index}", title=f"Backend Engineer {index}")
        for index in range(8)
    )

    ranked = rank_jobs(_profile(), _preferences(), jobs, result_limit=10, result_floor=0)
    companies = Counter(job.canonical_company for job, _score in ranked)

    assert len(ranked) == 10
    assert companies["acme"] <= 2
    assert all(score.base_score is not None for _job_result, score in ranked)
    assert all("company_diversity" in score.rerank_adjustments for _job_result, score in ranked)


def test_ranking_explains_role_transferable_skills_preferences_and_source_quality():
    preferences = CandidatePreferences(
        target_roles=["machine learning engineer"],
        locations=["Sydney"],
        experience_levels=["junior"],
        work_arrangements=["hybrid"],
        salary_min=140_000,
        preferred_companies=["Preferred AI Pty Ltd"],
        max_years_experience=3,
    )
    profile = CandidateProfile(
        target_roles=["machine learning engineer"],
        skills=[SkillEvidence(name="PyTorch", category="ML", evidence_type=EvidenceType.EXPLICIT)],
    )
    job = normalize_job(
        _job(
            1,
            title="AI Engineer",
            company="Preferred AI",
            description=(
                "Hybrid role using TensorFlow. Salary A$150K-A$170K. "
                "Requires 2 years of machine learning experience."
            ),
            required_skills=["TensorFlow"],
            source="greenhouse:preferred",
        )
    )

    score = calculate_relevance_score(profile, preferences, job, today=date(2026, 8, 2))

    assert score.components["role_compatibility"] >= 90
    assert 50 <= score.components["required_skills"] < 100
    assert score.components["experience_level"] > 0
    assert score.components["work_arrangement"] == 100
    assert score.components["compensation"] == 100
    assert score.components["company_industry"] == 100
    assert score.components["source_quality"] >= 80


def test_excessive_required_experience_is_a_hard_negative_signal():
    job = normalize_job(
        _job(
            2,
            title="Senior Software Engineer",
            description="Requires 7+ years of software engineering experience.",
        )
    )
    score = calculate_relevance_score(_profile(), _preferences(), job, today=date(2026, 8, 2))

    assert job.required_years_min == 7
    assert score.components["experience_level"] == 0


def _profile() -> CandidateProfile:
    return CandidateProfile(
        target_roles=["software engineer"],
        experience_levels=["graduate", "junior"],
        skills=[SkillEvidence(name="Python", category="programming", evidence_type=EvidenceType.EXPLICIT)],
    )


def _preferences() -> CandidatePreferences:
    return CandidatePreferences(
        target_roles=["software engineer"],
        locations=["Sydney"],
        experience_levels=["graduate", "junior"],
        max_years_experience=2,
    )


def _job(
    index: int,
    *,
    company: str = "Example",
    title: str = "Graduate Software Engineer",
    description: str = "Build reliable Python software services in Sydney.",
    required_skills: list[str] | None = None,
    source: str = "seek",
) -> JobResult:
    return JobResult(
        job_id=f"job-{index}",
        title=title,
        company=company,
        location="Sydney NSW",
        employment_type="Full-time",
        description=description,
        source=source,
        application_url=f"https://jobs.example.test/{index}",
        date_found="2026-08-02",
        date_posted="2026-08-01",
        required_skills=required_skills or [],
        experience_required="Graduate",
    )
