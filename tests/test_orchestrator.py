import json

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.candidate import CandidatePreferences
from app.tools.llm_client import LLMGenerationResult


def test_orchestrator_produces_validated_recommendations(tmp_path):
    preferences = CandidatePreferences.model_validate(
        json.loads(open("sample_data/preferences.json", encoding="utf-8").read())
    )
    output = tmp_path / "latest_run.json"

    result = OrchestratorAgent().run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=preferences,
        output_path=str(output),
        top_n=5,
    )

    assert result.discovered_count == 12
    assert result.validated_count == 8
    assert result.recommended_count == 5
    assert all(check.passed for check in result.validation_checks)
    assert all(app.quality_checks.unsupported_claims == 0 for app in result.applications)
    assert output.exists()


def test_orchestrator_tailors_only_top_n_jobs(tmp_path, monkeypatch):
    preferences = CandidatePreferences.model_validate(
        json.loads(open("sample_data/preferences.json", encoding="utf-8").read())
    )
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.generate_application_copy",
        lambda *_args, **_kwargs: LLMGenerationResult(
            attempted=True,
            error_type="test",
            error_message="forced fallback",
        ),
    )

    result = OrchestratorAgent().run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=preferences,
        output_path=str(tmp_path / "latest_run.json"),
        top_n=2,
    )

    tailoring_health = next(item for item in result.agent_health if item.agent == "application_tailor")
    assert result.recommended_count == 2
    assert tailoring_health.tool_calls == 2
