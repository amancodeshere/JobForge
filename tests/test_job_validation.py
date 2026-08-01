from app.schemas.candidate import CandidatePreferences
from app.tools.job_search import load_jobs_from_json, validate_job


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

