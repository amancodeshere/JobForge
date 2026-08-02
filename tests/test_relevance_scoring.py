from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.schemas.candidate import CandidatePreferences
from app.tools.job_search import load_jobs_from_json
from app.tools.relevance_scoring import WEIGHTS, calculate_relevance_score


def test_relevance_scoring_is_deterministic_and_weighted():
    preferences = CandidatePreferences.model_validate(
        {
            "target_roles": ["machine learning engineer"],
            "career_interests": ["machine learning engineering"],
            "locations": ["Sydney"],
            "experience_level": "graduate",
            "employment_types": ["Full-time"],
            "max_years_experience": 2,
            "posted_within_days": 30,
            "work_rights": "Australian unrestricted work rights",
        }
    )
    profile = CandidateProfileAgent().run("sample_data/cvs/aman_sharma_cv.txt", preferences)
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]

    score = calculate_relevance_score(profile, preferences, job)

    assert score.overall_score >= 80
    assert set(score.components) == set(WEIGHTS)
    assert sum(score.weights.values()) == 1.0
    assert score.base_score == score.overall_score


def test_unmatched_live_stack_does_not_receive_fixture_level_score():
    preferences = CandidatePreferences(
        target_roles=["software engineer"],
        career_interests=["software engineering"],
        experience_levels=["graduate", "junior"],
        locations=["Remote Australia"],
        work_rights="Australian unrestricted work rights",
    )
    profile = CandidateProfileAgent().run("sample_data/cvs/aman_sharma_cv.txt", preferences)
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0].model_copy(
        update={
            "job_id": "live-go-role",
            "title": "Go Software Engineer",
            "description": "Build Go and Linux container infrastructure.",
            "required_skills": ["Go", "Linux"],
            "preferred_skills": ["Rust"],
            "experience_required": "Junior",
            "location": "Remote",
        }
    )

    score = calculate_relevance_score(profile, preferences, job)

    assert score.components["required_skills"] == 0
    assert score.components["project_similarity"] <= 40
    assert score.overall_score < 78


def test_missing_provider_skill_metadata_is_neutral_not_positive():
    preferences = CandidatePreferences(target_roles=["software engineer"])
    profile = CandidateProfileAgent().run("sample_data/cvs/aman_sharma_cv.txt", preferences)
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0].model_copy(
        update={"required_skills": [], "preferred_skills": []}
    )

    score = calculate_relevance_score(profile, preferences, job)

    assert score.components["required_skills"] == 50
    assert score.components["preferred_skills"] == 50
