from __future__ import annotations

from app.schemas.job import JobResult
from app.tools.duplicate_detection import deduplicate_jobs, jobs_are_duplicates
from app.tools.job_normalization import canonicalize_url, normalize_job


def test_normalization_extracts_all_structured_search_fields_once():
    job = normalize_job(
        _job(
            job_id="structured-1",
            title="Senior Machine Learning Engineer",
            company="Example Technology Pty Ltd",
            location="Sydney, New South Wales (Hybrid)",
            description=(
                "Build Python, PyTorch and Kubernetes services. Requires 5-7 years experience. "
                "Salary A$160K–A$190K. Australian citizenship required; sponsorship is not available. "
                "This is a 12-month contract. Applications close 31 August 2026."
            ),
            application_url="https://jobs.example.test/roles/123/?utm_source=board&ref=abc",
        )
    )

    assert job.canonical_url == "https://jobs.example.test/roles/123"
    assert job.canonical_company == "example technology"
    assert job.canonical_location == "sydney nsw hybrid"
    assert job.work_arrangement == "hybrid"
    assert (job.compensation_min, job.compensation_max, job.compensation_currency) == (160000, 190000, "AUD")
    assert (job.required_years_min, job.required_years_max) == (5, 7)
    assert "senior" in job.seniority_levels
    assert "Australian citizenship required" in job.visa_requirements
    assert "Visa sponsorship unavailable" in job.visa_requirements
    assert job.contract_duration == "12 months"
    assert job.application_deadline == "2026-08-31"
    assert {"Python", "PyTorch", "Kubernetes"} <= set(job.inferred_skills)
    assert job.description_fingerprint
    assert job.source_provenance == ["adzuna"]
    assert job.source_job_ids == ["structured-1"]


def test_canonical_url_preserves_identity_parameters_and_drops_tracking():
    assert canonicalize_url(
        "https://www.indeed.com/viewjob?utm_campaign=x&jk=stable-id&from=search#top"
    ) == "https://indeed.com/viewjob?jk=stable-id"


def test_cross_provider_duplicates_merge_into_richest_direct_record_with_provenance():
    broad = normalize_job(
        _job(
            job_id="adzuna-123",
            source="adzuna",
            title="Software Developer",
            company="Example Co Pty Ltd",
            location="Sydney NSW",
            description="Build Python APIs.",
            application_url="https://redirect.example.test/job/123?utm_source=adzuna",
            date_posted="2026-07-31",
        )
    )
    direct = normalize_job(
        _job(
            job_id="greenhouse-example-999",
            source="greenhouse:example",
            title="Software Engineer",
            company="Example Company",
            location="Sydney, New South Wales",
            description="Build, test and operate reliable Python APIs using FastAPI, PostgreSQL and Docker.",
            application_url="https://boards.example.test/jobs/999?gh_src=tracking",
            date_posted="2026-08-01",
        )
    )

    result = deduplicate_jobs([broad, direct])

    assert len(result) == 1
    merged = result[0]
    assert merged.job_id == "greenhouse-example-999"
    assert merged.application_url.startswith("https://boards.example.test/")
    assert merged.description == direct.description
    assert merged.date_posted == "2026-08-01"
    assert merged.duplicate_count == 2
    assert merged.source_provenance == ["adzuna", "greenhouse:example"]
    assert merged.source_job_ids == ["adzuna-123", "greenhouse-example-999"]
    assert {"Python", "FastAPI", "PostgreSQL", "Docker"} <= set(merged.inferred_skills)


def test_distinct_requisitions_from_same_provider_are_not_fuzzy_merged():
    first = normalize_job(
        _job(
            job_id="greenhouse-example-1",
            source="greenhouse:example",
            title="Software Engineer",
            application_url="https://boards.example.test/jobs/1",
        )
    )
    second = normalize_job(
        _job(
            job_id="greenhouse-example-2",
            source="greenhouse:example",
            title="Software Engineer",
            application_url="https://boards.example.test/jobs/2",
        )
    )

    assert not jobs_are_duplicates(first, second)
    assert len(deduplicate_jobs([first, second])) == 2


def test_conflicting_seniority_is_not_merged_across_providers():
    graduate = normalize_job(
        _job(
            job_id="seek-grad",
            source="seek",
            title="Graduate Software Engineer",
            application_url="https://seek.example.test/jobs/grad",
        )
    )
    senior = normalize_job(
        _job(
            job_id="adzuna-senior",
            source="adzuna",
            title="Senior Software Engineer",
            description="Requires 7+ years of experience building Python services.",
            application_url="https://adzuna.example.test/jobs/senior",
        )
    )

    assert not jobs_are_duplicates(graduate, senior)


def _job(
    *,
    job_id: str,
    title: str,
    company: str = "Example Technology",
    location: str = "Sydney NSW",
    description: str = "Build and maintain Python software services.",
    source: str = "adzuna",
    application_url: str = "https://jobs.example.test/role",
    date_posted: str = "2026-08-01",
) -> JobResult:
    return JobResult(
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        employment_type="Full-time",
        description=description,
        source=source,
        application_url=application_url,
        date_found="2026-08-02",
        date_posted=date_posted,
    )
