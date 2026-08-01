from datetime import date

import pytest

from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.schemas.application import TailoredStatement
from app.schemas.candidate import CandidatePreferences, CandidateProfile, EvidenceItem, Project, SkillEvidence
from app.schemas.candidate import EvidenceType
from app.schemas.job import JobResult
from app.services.latex_resume import (
    LatexCompileError,
    build_resume_latex,
    compile_resume_pdf,
    latex_engine_available,
)


def _profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_name="Aman Sharma",
        experience_level="graduate",
        locations=["Sydney"],
        skills=[
            SkillEvidence(
                name="Python",
                category="languages",
                evidence_type=EvidenceType.EXPLICIT,
                evidence_ids=["cv-002"],
            )
        ],
        projects=[
            Project(
                name="Search & ranking",
                description="Built a search and ranking service using Python.",
                technologies=["Python"],
                evidence_ids=["cv-002"],
            )
        ],
        verified_evidence=[
            EvidenceItem(
                evidence_id="cv-001",
                cv_section="Education",
                original_text="Bachelor of Engineering, UNSW",
            ),
            EvidenceItem(
                evidence_id="cv-002",
                cv_section="Projects/Experience",
                original_text="Built a search and ranking service using Python.",
            ),
        ],
    )


def _job() -> JobResult:
    return JobResult(
        job_id="job-1",
        title="Graduate Software Engineer",
        company="Example & Co",
        location="Sydney",
        employment_type="Full-time",
        description="Build Python services.",
        source="test",
        application_url="https://jobs.example/1",
        date_found="2026-08-01",
        date_posted="2026-08-01",
        required_skills=["Python"],
    )


def test_latex_source_escapes_external_values_and_uses_trusted_template():
    source = build_resume_latex(
        _profile(),
        _job(),
        [TailoredStatement(tailored_bullet=r"Built 100% of R&D {work} without \\input tricks.", evidence_ids=["cv-002"])],
    )

    assert source.startswith("% JobForge trusted resume template")
    assert r"Example \& Co" in source
    assert r"100\%" in source
    assert r"\{work\}" in source
    assert r"\\input tricks" not in source


def test_compiler_rejects_untrusted_latex():
    with pytest.raises(LatexCompileError, match="trusted JobForge template"):
        compile_resume_pdf(r"\documentclass{article}\begin{document}Nope\end{document}")


@pytest.mark.skipif(not latex_engine_available(), reason="LaTeX engine not installed")
def test_latex_resume_compiles_to_verified_pdf():
    source = build_resume_latex(
        _profile(),
        _job(),
        [TailoredStatement(tailored_bullet="Built a search and ranking service using Python.", evidence_ids=["cv-002"])],
    )

    compiled = compile_resume_pdf(source, expected_name="Aman Sharma")

    assert compiled.pdf_bytes.startswith(b"%PDF")
    assert compiled.page_count in {1, 2}
    assert "Aman Sharma" in compiled.extracted_text
    assert "Graduate Software Engineer" in compiled.extracted_text


def test_tailor_agent_always_produces_latex_without_exposing_skill_gaps(monkeypatch):
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.generate_application_copy",
        lambda *_args, **_kwargs: __import__(
            "app.tools.llm_client", fromlist=["LLMGenerationResult"]
        ).LLMGenerationResult(),
    )
    application = ApplicationTailorAgent().run(
        _profile(),
        CandidatePreferences(target_roles=["software engineer"]),
        _job(),
        today=date(2026, 8, 1),
    )

    assert application.tailored_cv_latex.startswith("% JobForge trusted resume template")
    assert "Gaps To Avoid Overclaiming" not in application.tailored_cv
