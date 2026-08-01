from app.tools.duplicate_detection import deduplicate_jobs
from app.tools.job_search import load_jobs_from_json


def test_deduplicate_jobs_uses_title_company_location():
    jobs = load_jobs_from_json("sample_data/jobs/jobs.json")
    duplicated = [jobs[0], jobs[0].model_copy(update={"job_id": "copy"})]

    unique = deduplicate_jobs(duplicated)

    assert len(unique) == 1

