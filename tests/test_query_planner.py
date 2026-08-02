from __future__ import annotations

import json
from pathlib import Path

from app.schemas.candidate import CandidatePreferences, CandidateProfile, EvidenceType, SkillEvidence
from app.tools.ats_registry import default_public_boards, indexed_workday_scopes, load_ats_registry
from app.tools.live_job_search import CompanyBoard, LiveJobSearch, LiveSearchConfig
from app.tools.query_planner import (
    distinctive_role_tokens,
    plan_for_preferences,
    plan_for_profile,
    role_match_score,
    role_matches,
)


def test_query_plan_includes_exact_alias_seniority_and_skill_variants():
    preferences = CandidatePreferences(
        target_roles=["machine learning engineer"],
        experience_levels=["graduate", "junior"],
    )
    plan = plan_for_preferences(preferences, rotation_bucket=100)

    kinds = {variant.kind for variant in plan.variants}
    texts = {variant.text.lower() for variant in plan.variants}
    assert kinds == {"exact", "alias", "seniority", "skill"}
    assert "machine learning engineer" in texts
    assert "ai engineer" in texts
    assert "graduate machine learning engineer" in texts
    assert any("pytorch" in text for text in texts)
    assert all(variant.weight > 0 for variant in plan.variants)


def test_provider_plans_keep_exact_intent_and_rotate_secondary_queries():
    preferences = CandidatePreferences(
        target_roles=["software engineer", "data analyst"],
        experience_levels=["graduate", "junior"],
    )
    plans = {
        tuple(plan_for_preferences(preferences, rotation_bucket=bucket).for_provider("serpapi-multiboard", 4))
        for bucket in range(10)
    }

    assert len(plans) > 1
    assert all("software engineer" in plan and "data analyst" in plan for plan in plans)


def test_profile_plan_adds_verified_skill_led_variants():
    profile = CandidateProfile(
        target_roles=["robotics engineer"],
        skills=[
            SkillEvidence(name="ROS2", category="robotics", evidence_type=EvidenceType.EXPLICIT),
            SkillEvidence(name="C++", category="programming", evidence_type=EvidenceType.EXPLICIT),
        ],
    )
    plan = plan_for_profile(profile)

    assert any(variant.kind == "skill" and "ros2" in variant.text.lower() for variant in plan.variants)


def test_role_taxonomy_recovers_adjacent_titles_without_generic_false_positives():
    assert role_matches("software engineer", "Backend Developer")
    assert role_matches("machine learning engineer", "Applied Scientist")
    assert role_matches("data analyst", "Business Intelligence Analyst")
    assert role_matches("computer vision engineer", "Perception Engineer")
    assert role_matches("robotics engineer", "Autonomy Engineer")
    assert not role_matches("AI engineer", "Patient Care Specialist")
    assert not role_matches("software engineer", "Executive Assistant")
    assert role_match_score("software engineer", "Backend Developer") >= 0.9
    assert distinctive_role_tokens("Senior Software Engineer") == {"software"}


def test_role_matching_benchmark_meets_precision_and_recall_gate():
    cases = json.loads(Path("tests/fixtures/role_matching_benchmark.json").read_text(encoding="utf-8"))
    predictions = [role_matches(case["requested"], case["title"]) for case in cases]
    true_positives = sum(prediction and case["relevant"] for prediction, case in zip(predictions, cases))
    false_positives = sum(prediction and not case["relevant"] for prediction, case in zip(predictions, cases))
    false_negatives = sum(not prediction and case["relevant"] for prediction, case in zip(predictions, cases))
    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)

    assert len(cases) == 30
    assert precision >= 0.9
    assert recall >= 0.9


def test_registry_is_verified_and_separates_public_apis_from_indexed_workday():
    entries = load_ats_registry()

    assert {entry.provider for entry in entries} == {"greenhouse", "lever", "ashby", "workday"}
    assert all(entry.verification_url.startswith("https://") for entry in entries)
    assert all(entry.verified_on.isoformat() == "2026-08-02" for entry in entries)
    assert {entry.company for entry in default_public_boards("greenhouse")} == {"Canonical"}
    assert {entry.company for entry in default_public_boards("lever")} == {"Deputy"}
    assert {entry.company for entry in default_public_boards("ashby")} == {"Airtasker"}
    assert all("myworkdayjobs.com" in scope for scope in indexed_workday_scopes())


def test_ashby_public_board_results_are_normalized_and_filtered():
    payload = {
        "jobs": [
            {
                "id": "job-1",
                "title": "Backend Developer",
                "location": "Sydney (Hybrid)",
                "employmentType": "FullTime",
                "descriptionPlain": "Build Python APIs and reliable services.",
                "jobUrl": "https://jobs.ashbyhq.com/example/job-1",
                "publishedAt": "2026-08-01T00:00:00Z",
                "isListed": True,
            },
            {
                "id": "job-2",
                "title": "Executive Assistant",
                "location": "Sydney",
                "descriptionPlain": "Support company leadership.",
                "jobUrl": "https://jobs.ashbyhq.com/example/job-2",
                "isListed": True,
            },
        ]
    }
    search = LiveJobSearch(
        LiveSearchConfig(ashby_boards=(CompanyBoard("Example", "example"),)),
        fetch_json=lambda *_args: payload,
    )

    outcome = search.targeted_search(CandidateProfile(target_roles=["software engineer"]))

    assert [job.job_id for job in outcome.jobs] == ["ashby-example-job-1"]
    assert outcome.jobs[0].source == "ashby:example"
    assert outcome.jobs[0].company == "Example"
    assert outcome.source_telemetry["ashby:example"].request_count == 1


def test_multiboard_site_scope_rotates_while_core_sources_remain():
    urls: list[str] = []
    search = LiveJobSearch(
        LiveSearchConfig(serpapi_api_key="key", max_search_queries=2),
        fetch_json=lambda url, _timeout: urls.append(url) or {"organic_results": []},
    )
    preferences = CandidatePreferences(target_roles=["software engineer"], locations=["Sydney"])

    search._rotation_bucket = lambda: 10  # type: ignore[method-assign]
    search.broad_search(preferences)
    search._rotation_bucket = lambda: 11  # type: ignore[method-assign]
    search.broad_search(preferences)

    assert len(urls) == 2
    assert urls[0] != urls[1]
    for url in urls:
        assert "site%3Aseek.com.au%2Fjob%2F" in url
        assert "site%3Aau.indeed.com%2Fviewjob" in url
        assert "site%3Alinkedin.com%2Fjobs%2Fview" in url
