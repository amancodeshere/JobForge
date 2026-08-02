from __future__ import annotations

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.candidate import CandidatePreferences
from app.tools.rollout import (
    FeedbackStore,
    PromotionMetrics,
    RolloutConfig,
    SearchFeedback,
    compare_rankings,
    evaluate_promotion,
    rollout_decision,
)


def test_canary_assignment_is_stable_and_honours_kill_switches():
    config = RolloutConfig(ranker_v2_enabled=True, rollout_percent=37)
    first = rollout_decision("candidate-search", config)
    assert rollout_decision("candidate-search", config) == first
    assert 0 <= first.bucket < 100
    assert rollout_decision("candidate-search", RolloutConfig(rollout_percent=0)).ranker == "v1"
    assert rollout_decision("candidate-search", RolloutConfig(rollout_percent=100)).ranker == "v2"
    assert rollout_decision("candidate-search", RolloutConfig(ranker_v2_enabled=False, rollout_percent=100)).ranker == "v1"


def test_shadow_comparison_measures_overlap_and_movement():
    comparison = compare_rankings(["a", "b", "c"], ["b", "a", "d"])
    assert comparison.top_ten_overlap == 0.5
    assert comparison.average_displacement == 1.0


def test_shadow_mode_never_changes_control_output():
    preferences = CandidatePreferences(
        target_roles=["software engineer", "machine learning engineer"],
        locations=["Sydney", "Remote"],
        experience_level="graduate",
    )
    control = OrchestratorAgent(
        rollout_config=RolloutConfig(ranker_v2_enabled=False, shadow_enabled=False),
    ).search("sample_data/cvs/aman_sharma_cv.txt", preferences, limit=10)
    shadow = OrchestratorAgent(
        rollout_config=RolloutConfig(ranker_v2_enabled=False, shadow_enabled=True),
    ).search("sample_data/cvs/aman_sharma_cv.txt", preferences, limit=10)

    assert [item.job.job_id for item in shadow.ranked_jobs] == [item.job.job_id for item in control.ranked_jobs]
    assert shadow.shadow_comparison
    assert control.shadow_comparison == {}


def test_feedback_store_is_bounded_and_keeps_evaluation_context():
    store = FeedbackStore(max_entries=2)
    for index in range(3):
        store.add(SearchFeedback(correlation_id="search-1", job_id=f"job-{index}", signal="relevant", ranker="v2", rank=index + 1))
    snapshot = store.snapshot()
    assert [item.job_id for item in snapshot] == ["job-1", "job-2"]
    assert snapshot[-1].ranker == "v2"


def test_promotion_requires_every_quality_latency_and_reliability_gate():
    approved = evaluate_promotion(PromotionMetrics(
        precision_at_ten=0.804,
        duplicate_rate=0.0,
        invalid_rate=0.0,
        p95_latency_seconds=8.0,
        provider_error_rate=0.02,
    ))
    rejected = evaluate_promotion(PromotionMetrics(
        precision_at_ten=0.79,
        duplicate_rate=0.02,
        invalid_rate=0.05,
        p95_latency_seconds=12.0,
        provider_error_rate=0.10,
    ))
    assert approved.approved
    assert not rejected.approved
    assert set(rejected.failed_gates) == {
        "precision_at_ten", "duplicate_rate", "invalid_rate", "p95_latency", "provider_error_rate"
    }
