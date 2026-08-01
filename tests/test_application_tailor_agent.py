import json

from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.schemas.application import LLMApplicationCopy, TailoredStatement
from app.schemas.candidate import CandidatePreferences
from app.tools.evidence_validator import validate_application_grounding
from app.tools.job_search import load_jobs_from_json
from app.tools.llm_client import LLMGenerationResult, _parse_json_object


def _profile_preferences_job():
    preferences = CandidatePreferences.model_validate(
        json.loads(open("sample_data/preferences.json", encoding="utf-8").read())
    )
    profile = CandidateProfileAgent().run("sample_data/cvs/aman_sharma_cv.txt", preferences)
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]
    return profile, preferences, job


def test_valid_llm_copy_is_accepted(monkeypatch):
    profile, preferences, job = _profile_preferences_job()
    bullet = "Used Python in CV-backed project work for model and data workflows."
    llm_copy = LLMApplicationCopy(
        tailored_cv=f"# Tailored CV\n- {bullet}",
        cover_letter=f"Dear {job.company} hiring team,\n\n{bullet}\n\nKind regards,\nAman Sharma",
        tailored_statements=[
            TailoredStatement(tailored_bullet=bullet, evidence_ids=["cv-004"]),
        ],
        risk_notes=[],
    )
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.generate_application_copy",
        lambda *_args, **_kwargs: LLMGenerationResult(attempted=True, success=True, application_copy=llm_copy),
    )

    application = ApplicationTailorAgent().run(profile, preferences, job)

    assert application.generation_source == "openai"
    assert application.tailored_cv == llm_copy.tailored_cv
    assert application.quality_checks.unsupported_claims == 0


def test_unsafe_llm_copy_falls_back_to_deterministic(monkeypatch):
    profile, preferences, job = _profile_preferences_job()
    bullet = "Built production AWS and Kubernetes systems with 5 years experience."
    llm_copy = LLMApplicationCopy(
        tailored_cv=f"# Tailored CV\n- {bullet}",
        cover_letter=f"Dear Wrong Company,\n\n{bullet}",
        tailored_statements=[
            TailoredStatement(tailored_bullet=bullet, evidence_ids=[]),
        ],
        risk_notes=["unsafe"],
    )
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.generate_application_copy",
        lambda *_args, **_kwargs: LLMGenerationResult(attempted=True, success=True, application_copy=llm_copy),
    )

    application = ApplicationTailorAgent().run(profile, preferences, job)

    assert application.generation_source == "deterministic"
    assert job.company in application.cover_letter
    assert application.quality_checks.unsupported_claims == 0


def test_llm_json_parser_requires_structured_copy():
    assert _parse_json_object('{"tailored_cv": "x", "cover_letter": "y"}') is not None
    assert _parse_json_object('{"tailored_cv": "x"}') is None
    assert _parse_json_object("not-json") is None


def test_grounding_validator_flags_overclaims(monkeypatch):
    profile, preferences, job = _profile_preferences_job()
    bullet = "Built production AWS systems with 5 years experience."
    llm_copy = LLMApplicationCopy(
        tailored_cv=f"# Tailored CV\n- {bullet}",
        cover_letter=f"Dear {job.company} hiring team,\n\n{bullet}",
        tailored_statements=[
            TailoredStatement(tailored_bullet=bullet, evidence_ids=["cv-004"]),
        ],
        risk_notes=[],
    )
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.generate_application_copy",
        lambda *_args, **_kwargs: LLMGenerationResult(attempted=True, success=True, application_copy=llm_copy),
    )

    application = ApplicationTailorAgent().run(profile, preferences, job)

    assert application.generation_source == "deterministic"
    unsafe_application = application.model_copy(
        update={
            "tailored_cv": llm_copy.tailored_cv,
            "cover_letter": llm_copy.cover_letter,
            "tailored_statements": llm_copy.tailored_statements,
            "generation_source": "openai",
        }
    )
    checks = validate_application_grounding(unsafe_application, profile)
    assert checks.unsupported_claims > 0


def test_deterministic_cover_letter_uses_extracted_candidate_name():
    profile, preferences, job = _profile_preferences_job()

    application = ApplicationTailorAgent().run(profile, preferences, job)

    assert application.cover_letter.endswith("Kind regards,\nAman Sharma")
