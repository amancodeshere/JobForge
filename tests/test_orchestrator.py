import json

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.candidate import CandidatePreferences
from app.tools.llm_client import LLMGenerationResult
from app.tools.live_job_search import SearchOutcome
from app.tools.job_search import load_jobs_from_json


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


def test_orchestrator_uses_live_jobs_without_mixing_sample_data(tmp_path):
    class FakeLiveSearch:
        def broad_search(self, _preferences):
            job = load_jobs_from_json("sample_data/jobs/jobs.json")[0].model_copy(
                update={"job_id": "live-001", "source": "test-live"}
            )
            return SearchOutcome(jobs=[job], sources_attempted=["test-live"])

        def targeted_search(self, _profile):
            return SearchOutcome(sources_attempted=["test-board"])

    preferences = CandidatePreferences.model_validate(
        json.loads(open("sample_data/preferences.json", encoding="utf-8").read())
    )
    result = OrchestratorAgent(live_search=FakeLiveSearch()).run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=preferences,
        output_path=str(tmp_path / "latest_run.json"),
        top_n=5,
        use_live_search=True,
    )

    assert result.search_mode == "live"
    assert result.search_sources == ["test-live", "test-board"]
    assert result.discovered_count == 1
    assert [application.job_id for application in result.applications] == ["live-001"]


def test_orchestrator_marks_sample_fallback(tmp_path):
    class EmptyLiveSearch:
        def broad_search(self, _preferences):
            return SearchOutcome(sources_attempted=["offline"], source_errors=["offline: timeout"])

        def targeted_search(self, _profile):
            return SearchOutcome()

    result = OrchestratorAgent(live_search=EmptyLiveSearch()).run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=CandidatePreferences(),
        output_path=str(tmp_path / "latest_run.json"),
        use_live_search=True,
    )

    assert result.search_mode == "sample_fallback"
    assert "sample" in result.search_sources
    assert any("bundled sample" in warning for warning in result.search_warnings)
