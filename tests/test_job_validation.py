from app.schemas.candidate import CandidatePreferences
from app.tools.job_search import broad_queries, load_jobs_from_json, validate_job


def test_job_validation_rejects_senior_and_part_time_roles():
    preferences = CandidatePreferences(
        employment_types=["Full-time"],
        max_years_experience=2,
        posted_within_days=30,
        work_rights="Australian unrestricted work rights",
    )
    jobs = {job.job_id: job for job in load_jobs_from_json("sample_data/jobs/jobs.json")}

    senior = validate_job(jobs["job-009"], preferences)
    part_time = validate_job(jobs["job-010"], preferences)
    citizen = validate_job(jobs["job-011"], preferences)

    assert senior.status == "rejected"
    assert part_time.status == "rejected"
    assert citizen.status == "rejected"


def test_job_validation_allows_selected_senior_level():
    preferences = CandidatePreferences(
        experience_levels=["senior"],
        employment_types=["Full-time"],
        max_years_experience=8,
        posted_within_days=30,
        work_rights="Australian unrestricted work rights",
    )
    senior = load_jobs_from_json("sample_data/jobs/jobs.json")[8]

    checked = validate_job(senior, preferences)

    assert checked.status == "validated"


def test_broad_queries_use_multiple_experience_levels():
    preferences = CandidatePreferences(
        target_roles=["machine learning engineer"],
        locations=["Sydney"],
        experience_levels=["graduate", "internship", "associate"],
    )

    queries = broad_queries(preferences)

    assert "graduate machine learning engineer Sydney" in queries
    assert "internship machine learning engineer Sydney" in queries
    assert "associate machine learning engineer Sydney" in queries
