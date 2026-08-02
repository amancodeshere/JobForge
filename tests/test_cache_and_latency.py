from __future__ import annotations

from threading import Event
from time import perf_counter, sleep

from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.tools.cache import TTLCache
from app.tools.live_job_search import CompanyBoard, LiveJobSearch, LiveSearchConfig


def test_ttl_cache_serves_fresh_then_stale_while_revalidating():
    now = [0.0]
    cache: TTLCache[dict] = TTLCache(max_entries=2, clock=lambda: now[0])
    refresh_complete = Event()
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        if calls > 1:
            refresh_complete.set()
        return {"version": calls}

    assert cache.get_or_load("key", loader, ttl_seconds=10, stale_seconds=20).status == "miss"
    assert cache.get_or_load("key", loader, ttl_seconds=10, stale_seconds=20).status == "fresh"
    now[0] = 15
    stale = cache.get_or_load("key", loader, ttl_seconds=10, stale_seconds=20)

    assert stale.status == "stale"
    assert stale.value == {"version": 1}
    assert refresh_complete.wait(timeout=1)
    assert calls == 2


def test_repeated_broad_search_uses_no_second_request_and_is_over_sixty_percent_faster():
    calls = 0

    def fetch_json(_url: str, _timeout: float):
        nonlocal calls
        calls += 1
        sleep(0.05)
        return {
            "results": [
                {
                    "id": "1",
                    "title": "Software Engineer",
                    "company": {"display_name": "Example"},
                    "location": {"display_name": "Sydney"},
                    "description": "Build Python software services.",
                    "redirect_url": "https://jobs.example.test/1",
                    "created": "2026-08-01",
                }
            ]
        }

    search = LiveJobSearch(
        LiveSearchConfig(adzuna_app_id="id", adzuna_app_key="key", max_search_queries=1),
        fetch_json=fetch_json,
    )
    preferences = CandidatePreferences(target_roles=["software engineer"], locations=["Sydney"])
    started = perf_counter()
    first = search.broad_search(preferences)
    uncached_seconds = perf_counter() - started
    started = perf_counter()
    second = search.broad_search(preferences)
    cached_seconds = perf_counter() - started

    assert calls == 1
    assert first.source_telemetry["adzuna"].cache_status == "miss"
    assert second.source_telemetry["adzuna"].cache_status == "fresh"
    assert second.source_telemetry["adzuna"].request_count == 0
    assert cached_seconds < uncached_seconds * 0.4


def test_controlled_first_shortlist_and_repeat_cost_targets():
    calls = 0
    progress_times: list[float] = []
    started = perf_counter()

    def fetch_json(_url: str, _timeout: float):
        nonlocal calls
        calls += 1
        sleep(0.02)
        return {"jobs": [_greenhouse_job(1, "Backend Developer")]}

    search = LiveJobSearch(
        LiveSearchConfig(greenhouse_boards=(CompanyBoard("Example", "example"),)),
        fetch_json=fetch_json,
        progress_callback=lambda _event: progress_times.append(perf_counter() - started),
    )
    profile = CandidateProfile(target_roles=["software engineer"])
    first = search.targeted_search(profile)
    first_request_count = sum(item.request_count for item in first.source_telemetry.values())
    cached_started = perf_counter()
    second = search.targeted_search(profile)
    cached_duration = perf_counter() - cached_started
    repeat_request_count = sum(item.request_count for item in second.source_telemetry.values())

    assert progress_times[0] < 8.0
    assert cached_duration < 3.0
    assert first_request_count == 1
    assert repeat_request_count == 0
    assert calls == 1


def test_ats_inventory_is_reused_across_candidate_profiles_before_filtering():
    calls = 0

    def fetch_json(_url: str, _timeout: float):
        nonlocal calls
        calls += 1
        return {
            "jobs": [
                _greenhouse_job(1, "Backend Developer"),
                _greenhouse_job(2, "Machine Learning Engineer"),
            ]
        }

    search = LiveJobSearch(
        LiveSearchConfig(greenhouse_boards=(CompanyBoard("Example", "example"),)),
        fetch_json=fetch_json,
    )
    software = search.targeted_search(CandidateProfile(target_roles=["software engineer"]))
    machine_learning = search.targeted_search(CandidateProfile(target_roles=["machine learning engineer"]))

    assert calls == 1
    assert [job.job_id for job in software.jobs] == ["greenhouse-example-1"]
    assert [job.job_id for job in machine_learning.jobs] == ["greenhouse-example-2"]
    assert machine_learning.source_telemetry["greenhouse:example"].cache_status == "fresh"


def test_provider_completion_events_include_progressive_job_previews():
    events = []
    search = LiveJobSearch(
        LiveSearchConfig(greenhouse_boards=(CompanyBoard("Example", "example"),)),
        fetch_json=lambda *_args: {"jobs": [_greenhouse_job(1, "Backend Developer")]},
        progress_callback=events.append,
    )

    outcome = search.targeted_search(CandidateProfile(target_roles=["software engineer"]))

    assert outcome.jobs
    assert len(events) == 1
    assert events[0].status == "completed"
    assert events[0].records_returned == 1
    assert events[0].jobs[0].title == "Backend Developer"


def test_candidate_profile_cache_keys_cv_content_and_preferences(tmp_path, monkeypatch):
    cv_path = tmp_path / "unique-cache-cv.txt"
    cv_path.write_text("Unique Person\nPython software engineer project evidence", encoding="utf-8")
    calls = 0
    original = CandidateProfileAgent.run

    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(CandidateProfileAgent, "run", counted)
    preferences = CandidatePreferences(target_roles=["unique cache software engineer"])

    first = OrchestratorAgent(enable_cache=True).search(str(cv_path), preferences, limit=1)
    second = OrchestratorAgent(enable_cache=True).search(str(cv_path), preferences, limit=1)

    assert calls == 1
    assert "profile cache: miss" in first.agent_health[0].notes
    assert "profile cache: fresh" in second.agent_health[0].notes


def test_search_boundary_does_not_generate_application_materials(monkeypatch):
    monkeypatch.setattr(
        "app.agents.application_tailor_agent.ApplicationTailorAgent.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("drafting should be on demand")),
    )

    result = OrchestratorAgent().search(
        "sample_data/cvs/aman_sharma_cv.txt",
        CandidatePreferences(target_roles=["software engineer"]),
        limit=5,
    )

    assert result.ranked_jobs


def _greenhouse_job(identifier: int, title: str) -> dict:
    return {
        "id": identifier,
        "title": title,
        "location": {"name": "Sydney"},
        "content": "Build Python software and machine learning systems.",
        "absolute_url": f"https://boards.example.test/jobs/{identifier}",
        "updated_at": "2026-08-01T00:00:00Z",
    }
