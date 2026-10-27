from datetime import date

from app.schemas.candidate import CandidatePreferences
from app.schemas.job import JobResult
from app.tools.experience_levels import infer_job_experience_levels
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

    checked = validate_job(senior, preferences, today=date(2026, 8, 1))

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


def test_executive_titles_are_supported():
    levels = infer_job_experience_levels("Chief Operating Officer on the executive leadership team")

    assert "executive" in levels


def test_zero_to_two_year_range_matches_early_career_bands_and_uses_minimum_requirement():
    levels = infer_job_experience_levels("Engineering role requiring 0-2 years experience")
    preferences = CandidatePreferences(experience_levels=["internship", "graduate"], max_years_experience=1)
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]

    checked = validate_job(job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert {"graduate", "entry-level", "junior"} <= set(levels)
    assert "Requires more than 1 years of experience." not in checked.rejection_reasons


def test_remote_australia_role_matches_candidate_in_an_australian_city():
    preferences = CandidatePreferences(experience_levels=["graduate", "junior"], locations=["Sydney"])
    remote_job = load_jobs_from_json("sample_data/jobs/jobs.json")[1]

    checked = validate_job(remote_job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert "Location does not match preferences." not in checked.rejection_reasons


def test_unknown_work_rights_are_flagged_in_scoring_but_not_hard_rejected():
    preferences = CandidatePreferences(experience_levels=["junior"], locations=["Canberra"], work_rights=None)
    citizen_job = load_jobs_from_json("sample_data/jobs/jobs.json")[10]

    checked = validate_job(citizen_job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert "Requires Australian citizenship." not in checked.rejection_reasons


def test_job_validation_ignores_senior_colleague_mentions():
    preferences = CandidatePreferences(
        experience_levels=["graduate", "junior"],
        locations=["Sydney"],
        work_rights="Australian unrestricted work rights",
    )
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0].model_copy(
        update={"description": "Graduate role collaborating with senior engineers in Sydney."}
    )

    checked = validate_job(job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert checked.status == "validated"


def test_job_validation_enforces_location_and_safe_application_url():
    preferences = CandidatePreferences(
        experience_levels=["graduate"],
        locations=["Sydney", "Remote Australia"],
        work_rights="Australian unrestricted work rights",
    )
    source = load_jobs_from_json("sample_data/jobs/jobs.json")[0]
    wrong_location = source.model_copy(update={"location": "New York, USA"})
    unsafe_url = source.model_copy(update={"application_url": "javascript:alert(1)"})

    location_result = validate_job(wrong_location, preferences, today=__import__("datetime").date(2026, 8, 1))
    url_result = validate_job(unsafe_url, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert "Location does not match preferences." in location_result.rejection_reasons
    assert "Application URL is not a valid HTTP(S) link." in url_result.rejection_reasons


def test_live_description_citizenship_requirement_is_enforced():
    preferences = CandidatePreferences(
        experience_levels=["graduate"],
        locations=["Sydney"],
        work_rights="Australian unrestricted work rights",
    )
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0].model_copy(
        update={
            "eligibility_requirements": [],
            "description": "Graduate engineering role. Applicants must be an Australian citizen.",
        }
    )

    checked = validate_job(job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert checked.status == "rejected"
    assert "Requires Australian citizenship." in checked.rejection_reasons


def test_inferred_description_skills_are_not_invented_as_requirements():
    job = JobResult(
        job_id="live-1",
        title="Software Engineer",
        company="Example",
        location="Remote",
        employment_type="Full-time",
        description="Build Go, Linux and Docker services.",
        source="live",
        application_url="https://jobs.example/1",
        date_found="2026-08-01",
    )

    checked = validate_job(job, CandidatePreferences(), today=__import__("datetime").date(2026, 8, 1))

    assert checked.required_skills == []
    assert {"Go", "Linux", "Docker"}.issubset(set(checked.preferred_skills))


def test_structured_exclusions_and_constraint_aliases_are_enforced():
    preferences = CandidatePreferences(
        excluded_companies=["Harbour AI Labs"],
        constraints=["Exclude keyword: defence"],
    )
    company_job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]
    keyword_job = load_jobs_from_json("sample_data/jobs/jobs.json")[1].model_copy(
        update={"description": "Build defence computer vision software."}
    )

    company_result = validate_job(company_job, preferences, today=__import__("datetime").date(2026, 8, 1))
    keyword_result = validate_job(keyword_job, preferences, today=__import__("datetime").date(2026, 8, 1))

    assert "Company is excluded by candidate preferences." in company_result.rejection_reasons
    assert "Contains excluded keyword: defence." in keyword_result.rejection_reasons
