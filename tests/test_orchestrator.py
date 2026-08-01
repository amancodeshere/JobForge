import json
from threading import Event

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


def test_orchestrator_overlaps_profile_extraction_with_broad_search(tmp_path, monkeypatch):
    orchestrator = OrchestratorAgent()
    broad_started = Event()
    original_profile_run = orchestrator.profile_agent.run
    original_broad_run = orchestrator.broad_agent.run

    def profile_run(*args, **kwargs):
        assert broad_started.wait(timeout=1), "broad search did not start while profiling was active"
        return original_profile_run(*args, **kwargs)

    def broad_run(*args, **kwargs):
        broad_started.set()
        return original_broad_run(*args, **kwargs)

    monkeypatch.setattr(orchestrator.profile_agent, "run", profile_run)
    monkeypatch.setattr(orchestrator.broad_agent, "run", broad_run)

    result = orchestrator.run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=CandidatePreferences(),
        output_path=str(tmp_path / "latest_run.json"),
        top_n=1,
    )

    assert result.applications
    assert all(item.duration_ms >= 0 for item in result.agent_health)


def test_orchestrator_reuses_precomputed_scores_during_parallel_tailoring(tmp_path, monkeypatch):
    from app.agents import orchestrator_agent

    original_score = orchestrator_agent.calculate_relevance_score
    score_calls = 0

    def counted_score(*args, **kwargs):
        nonlocal score_calls
        score_calls += 1
        return original_score(*args, **kwargs)

    monkeypatch.setattr(orchestrator_agent, "calculate_relevance_score", counted_score)
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.calculate_relevance_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("score was recalculated")),
    )

    result = OrchestratorAgent().run(
        cv_path="sample_data/cvs/aman_sharma_cv.txt",
        preferences=CandidatePreferences(),
        output_path=str(tmp_path / "latest_run.json"),
        top_n=3,
    )

    assert score_calls == result.validated_count
    assert result.recommended_count == 3
