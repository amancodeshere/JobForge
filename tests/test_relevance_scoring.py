from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.schemas.candidate import CandidatePreferences
from app.tools.job_search import load_jobs_from_json
from app.tools.relevance_scoring import calculate_relevance_score


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
    assert set(score.components) == {
        "required_skills",
        "preferred_skills",
        "experience_level",
        "career_interest",
        "project_similarity",
        "eligibility",
        "freshness",
    }

