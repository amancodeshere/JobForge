from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from time import perf_counter, sleep

import pytest

from app.evaluation.search_quality import (
    aggregate_provider_metrics,
    duplicate_rate,
    evaluate_benchmark,
    invalid_link_rate,
    load_benchmark,
    ndcg_at_k,
    precision_at_k,
    relevant_recall,
)
from app.schemas.candidate import CandidateProfile
from app.tools.job_search import load_jobs_from_json
from app.tools.live_job_search import CompanyBoard, LiveJobSearch, LiveSearchConfig, LiveSearchError


BENCHMARK_PATH = Path("tests/fixtures/search_benchmark.json")


def test_ranking_metrics_have_known_values():
    labels = {"best": 3, "good": 2, "marginal": 1, "bad": 0}
    ranking = ["best", "bad", "good", "marginal"]

    assert precision_at_k(ranking, labels, 3) == pytest.approx(2 / 3, abs=0.0001)
    assert relevant_recall(ranking, labels) == 1.0
    assert 0.8 < ndcg_at_k(ranking, labels, 4) < 1.0


def test_quality_rates_detect_duplicates_and_invalid_links():
    jobs = load_jobs_from_json("sample_data/jobs/jobs.json")
    duplicate = jobs[0].model_copy(update={"job_id": "duplicate"})
    invalid = jobs[1].model_copy(
        update={"job_id": "invalid", "title": "Unique Invalid Listing", "application_url": "javascript:bad"}
    )
    pool = [*jobs, duplicate, invalid]

    assert duplicate_rate(pool) == pytest.approx(1 / 14, abs=0.0001)
    assert invalid_link_rate(pool) == pytest.approx(1 / 14, abs=0.0001)


def test_benchmark_contains_thirty_diverse_labelled_search_briefs():
    cases = load_benchmark(BENCHMARK_PATH)

    assert len(cases) == 30
    assert len({case.case_id for case in cases}) == 30
    assert all(case.description and case.preferences.target_roles for case in cases)
    assert all(case.profile.skills and case.labels for case in cases)
    assert all(0 <= grade <= 3 for case in cases for grade in case.labels.values())
    assert {case.preferences.experience_level for case in cases} >= {
        "graduate",
        "internship",
        "entry-level",
        "junior",
        "senior",
    }


def test_provider_response_fixture_is_sanitized_and_complete():
    payload = json.loads(Path("tests/fixtures/provider_responses.json").read_text(encoding="utf-8"))

    assert set(payload) == {"adzuna", "serpapi_multiboard", "greenhouse", "lever"}
    serialized = json.dumps(payload)
    assert "example.test" in serialized
    assert "api_key" not in serialized.lower()
    assert "secret" not in serialized.lower()


def test_current_search_baseline_is_measurable():
    report = evaluate_benchmark(
        load_benchmark(BENCHMARK_PATH),
        load_jobs_from_json("sample_data/jobs/jobs.json"),
        today=date(2026, 8, 2),
    )

    assert report.metrics.case_count == 30
    assert report.metrics.precision_at_5 >= 0.8
    assert report.metrics.precision_at_10 >= 0.8
    assert report.metrics.ndcg_at_10 >= 0.8
    assert report.metrics.relevant_recall >= 0.7
    assert report.metrics.rejection_reasons
    assert len(report.cases) == 30


def test_sources_run_concurrently_and_record_fast_slow_empty_and_failed_telemetry():
    boards = (
        CompanyBoard("Fast", "fast"),
        CompanyBoard("Slow", "slow"),
        CompanyBoard("Empty", "empty"),
    )

    def fetch_json(url: str, _timeout: float):
        if "/slow/" in url:
            sleep(0.04)
            return {"jobs": [_greenhouse_item(2, "Machine Learning Engineer")]}
        if "/fast/" in url:
            sleep(0.015)
            return {"jobs": [_greenhouse_item(1, "Machine Learning Engineer")]}
        if "/empty/" in url:
            return {"jobs": []}
        if "lever" in url:
            sleep(0.01)
            raise LiveSearchError("network error: simulated outage")
        raise AssertionError(url)

    search = LiveJobSearch(
        LiveSearchConfig(
            greenhouse_boards=boards,
            lever_sites=(CompanyBoard("Failed", "failed"),),
            max_workers=4,
        ),
        fetch_json=fetch_json,
    )
    started = perf_counter()
    outcome = search.targeted_search(
        CandidateProfile(target_roles=["machine learning engineer"], career_themes=["machine learning"])
    )
    elapsed = perf_counter() - started

    assert elapsed < 0.09
    assert len(outcome.jobs) == 2
    assert outcome.source_counts["greenhouse:empty"] == 0
    assert outcome.source_telemetry["greenhouse:slow"].duration_ms >= 30
    assert outcome.source_telemetry["greenhouse:fast"].request_count == 1
    assert outcome.source_telemetry["lever:failed"].error_count == 1
    assert outcome.source_telemetry["lever:failed"].error_category == "network"
    assert outcome.source_errors == ["lever:failed: network error: simulated outage"]

    aggregates = aggregate_provider_metrics(
        [outcome],
        request_costs={"greenhouse:slow": 0.002, "lever:failed": 0.005},
    )
    assert aggregates["greenhouse:slow"].records_returned == 1
    assert aggregates["greenhouse:slow"].estimated_cost == 0.002
    assert aggregates["lever:failed"].error_rate == 1.0
    assert aggregates["lever:failed"].estimated_cost == 0.015
    assert outcome.source_telemetry["lever:failed"].retry_count == 2


def _greenhouse_item(identifier: int, title: str) -> dict:
    return {
        "id": identifier,
        "title": title,
        "location": {"name": "Sydney"},
        "content": "Build Python machine learning systems.",
        "absolute_url": f"https://boards.example.test/jobs/{identifier}",
        "updated_at": "2026-08-01T00:00:00Z",
    }
