from __future__ import annotations

from time import perf_counter, sleep

from app.schemas.candidate import CandidateProfile
from app.tools.live_job_search import CompanyBoard, LiveJobSearch, LiveSearchConfig, LiveSearchError
from app.tools.resilience import CircuitBreakerRegistry, RetryPolicy


def _profile() -> CandidateProfile:
    return CandidateProfile(target_roles=["software engineer"], career_themes=["software"])


def _greenhouse_payload(job_id: int = 1) -> dict:
    return {
        "jobs": [{
            "id": job_id,
            "title": "Software Engineer",
            "location": {"name": "Sydney"},
            "content": "Build reliable software systems with Python.",
            "absolute_url": f"https://job-boards.greenhouse.io/example/jobs/{job_id}",
            "updated_at": "2026-08-01T00:00:00Z",
        }]
    }


def test_transient_provider_failure_retries_then_recovers_without_blocking_other_sources():
    attempts = 0

    def fetch_json(_url: str, _timeout: float):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LiveSearchError("HTTP 503")
        return _greenhouse_payload()

    search = LiveJobSearch(
        LiveSearchConfig(
            greenhouse_boards=(CompanyBoard("Example", "example"),),
            retry_attempts=3,
        ),
        fetch_json=fetch_json,
        sleeper=lambda _delay: None,
    )
    outcome = search.targeted_search(_profile())

    assert len(outcome.jobs) == 1
    assert outcome.source_telemetry["greenhouse:example"].request_count == 2
    assert outcome.source_telemetry["greenhouse:example"].retry_count == 1
    assert outcome.source_errors == []


def test_non_transient_malformed_response_is_not_retried():
    calls = 0

    def fetch_json(_url: str, _timeout: float):
        nonlocal calls
        calls += 1
        return []

    outcome = LiveJobSearch(
        LiveSearchConfig(greenhouse_boards=(CompanyBoard("Example", "example"),)),
        fetch_json=fetch_json,
        sleeper=lambda _delay: None,
    ).targeted_search(_profile())

    assert calls == 1
    assert outcome.source_telemetry["greenhouse:example"].error_category == "invalid_response"


def test_circuit_breaker_opens_and_recovers_after_cooldown():
    now = [0.0]
    breaker = CircuitBreakerRegistry(failure_threshold=2, cooldown_seconds=10, clock=lambda: now[0])
    breaker.record_failure("provider")
    assert breaker.allow("provider")
    breaker.record_failure("provider")
    assert not breaker.allow("provider")
    now[0] = 11.0
    assert breaker.allow("provider")
    breaker.record_success("provider")
    assert breaker.state("provider") == "closed"


def test_overall_deadline_returns_partial_result_and_marks_slow_provider():
    def fetch_json(url: str, _timeout: float):
        if "/slow/" in url:
            sleep(0.12)
            return _greenhouse_payload(2)
        return _greenhouse_payload(1)

    search = LiveJobSearch(
        LiveSearchConfig(
            greenhouse_boards=(CompanyBoard("Fast", "fast"), CompanyBoard("Slow", "slow")),
            overall_deadline_seconds=0.03,
            retry_attempts=1,
            max_workers=2,
        ),
        fetch_json=fetch_json,
    )
    started = perf_counter()
    outcome = search.targeted_search(_profile())

    assert perf_counter() - started < 0.09
    assert outcome.deadline_exceeded
    assert len(outcome.jobs) == 1
    assert outcome.source_telemetry["greenhouse:slow"].error_category == "timeout"
    assert outcome.correlation_id


def test_retry_policy_is_bounded_and_jittered():
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=0.5)
    assert policy.delay(1, random_value=0.0) == 0.05
    assert policy.delay(2, random_value=1.0) == 0.30000000000000004
    assert policy.delay(9, random_value=1.0) == 0.75
