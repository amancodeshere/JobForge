from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.tools.live_job_search import CompanyBoard, LiveJobSearch, LiveSearchConfig, LiveSearchError


def test_adzuna_results_are_normalized():
    def fetch_json(url: str, _timeout: float):
        assert "api.adzuna.com" in url
        return {
            "results": [
                {
                    "id": "123",
                    "title": "Graduate Python Engineer",
                    "company": {"display_name": "Example Tech"},
                    "location": {"display_name": "Sydney NSW"},
                    "contract_time": "full_time",
                    "description": "Build Python services for machine learning products.",
                    "redirect_url": "https://jobs.example/123",
                    "created": "2026-08-01T02:00:00Z",
                }
            ]
        }

    search = LiveJobSearch(
        LiveSearchConfig(adzuna_app_id="id", adzuna_app_key="key", enable_remotive=False),
        fetch_json=fetch_json,
    )
    result = search.broad_search(CandidatePreferences(target_roles=["python engineer"], locations=["Sydney"]))

    assert result.source_errors == []
    assert result.jobs[0].job_id == "adzuna-123"
    assert result.jobs[0].source == "adzuna"
    assert result.jobs[0].employment_type == "Full-time"
    assert result.jobs[0].date_posted == "2026-08-01"
    assert result.source_counts == {"adzuna": 1}


def test_serpapi_google_jobs_preserves_original_board_and_apply_link():
    def fetch_json(url: str, _timeout: float):
        assert "engine=google_jobs" in url
        assert "location=Sydney" in url
        return {
            "jobs_results": [
                {
                    "job_id": "google-stable-id",
                    "title": "Graduate Software Engineer",
                    "company_name": "Example Labs",
                    "location": "Sydney NSW",
                    "via": "LinkedIn",
                    "description": "Build and test software services with Python.",
                    "detected_extensions": {
                        "posted_at": "2 days ago",
                        "schedule_type": "Full-time",
                    },
                    "apply_options": [
                        {"title": "Indeed", "link": "https://au.indeed.com/viewjob?jk=1"},
                        {"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/123"},
                    ],
                }
            ]
        }

    search = LiveJobSearch(
        LiveSearchConfig(serpapi_api_key="key", max_search_queries=1),
        fetch_json=fetch_json,
    )
    result = search.broad_search(
        CandidatePreferences(target_roles=["software engineer"], locations=["Sydney"])
    )

    assert result.sources_attempted == ["serpapi-google-jobs"]
    assert result.source_counts == {"serpapi-google-jobs": 1}
    assert result.jobs[0].source == "serpapi:linkedin"
    assert result.jobs[0].application_url == "https://www.linkedin.com/jobs/view/123"
    assert result.jobs[0].employment_type == "Full-time"
    assert result.jobs[0].date_posted is not None


def test_serpapi_falls_back_to_first_valid_apply_option():
    search = LiveJobSearch(
        LiveSearchConfig(serpapi_api_key="key", max_search_queries=1),
        fetch_json=lambda *_args: {
            "jobs_results": [
                {
                    "job_id": "seek-job",
                    "title": "Data Engineer",
                    "company_name": "Data Co",
                    "location": "Remote Australia",
                    "via": "SEEK",
                    "description": "Build data engineering pipelines.",
                    "apply_options": [
                        {"title": "Broken", "link": "javascript:alert(1)"},
                        {"title": "SEEK", "link": "https://www.seek.com.au/job/123"},
                    ],
                }
            ]
        },
    )

    result = search.broad_search(CandidatePreferences(target_roles=["data engineer"]))

    assert result.jobs[0].source == "serpapi:seek"
    assert result.jobs[0].application_url == "https://www.seek.com.au/job/123"


def test_targeted_sources_filter_irrelevant_jobs_and_capture_failures():
    def fetch_json(url: str, _timeout: float):
        if "greenhouse" in url:
            return {
                "jobs": [
                    {
                        "id": 7,
                        "title": "Machine Learning Engineer",
                        "location": {"name": "Sydney"},
                        "content": "<p>Build Python machine learning systems.</p>",
                        "absolute_url": "https://boards.example/jobs/7",
                        "updated_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "id": 8,
                        "title": "Account Executive",
                        "location": {"name": "Sydney"},
                        "content": "Enterprise sales role.",
                        "absolute_url": "https://boards.example/jobs/8",
                        "updated_at": "2026-08-01T00:00:00Z",
                    },
                ]
            }
        raise LiveSearchError("lever unavailable")

    search = LiveJobSearch(
        LiveSearchConfig(
            enable_remotive=False,
            greenhouse_boards=(CompanyBoard("Example Tech", "example"),),
            lever_sites=(CompanyBoard("Other Tech", "other"),),
        ),
        fetch_json=fetch_json,
    )
    result = search.targeted_search(
        CandidateProfile(target_roles=["machine learning engineer"], career_themes=["machine learning"])
    )

    assert [job.job_id for job in result.jobs] == ["greenhouse-example-7"]
    assert "Example Tech" == result.jobs[0].company
    assert result.jobs[0].description == "Build Python machine learning systems."
    assert len(result.source_errors) == 1
    assert result.source_errors[0].startswith("lever:other:")


def test_malformed_live_records_are_skipped():
    search = LiveJobSearch(
        LiveSearchConfig(enable_remotive=True),
        fetch_json=lambda *_args: {"jobs": [{"id": 1, "title": "Missing URL"}]},
    )

    result = search.broad_search(CandidatePreferences(target_roles=["engineer"]))

    assert result.jobs == []


def test_broad_search_filters_provider_false_positives():
    search = LiveJobSearch(
        LiveSearchConfig(enable_remotive=True),
        fetch_json=lambda *_args: {
            "jobs": [
                {
                    "id": 1,
                    "title": "Patient Care Specialist",
                    "company_name": "Health Co",
                    "description": "Coordinate clinical patient services.",
                    "url": "https://jobs.example/health",
                    "job_type": "full_time",
                    "publication_date": "2026-08-01",
                },
                {
                    "id": 2,
                    "title": "Machine Learning Engineer",
                    "company_name": "AI Co",
                    "description": "Build Python model services.",
                    "url": "https://jobs.example/ml",
                    "job_type": "full_time",
                    "publication_date": "2026-08-01",
                },
            ]
        },
    )

    result = search.broad_search(CandidatePreferences(target_roles=["machine learning engineer"]))

    assert [job.title for job in result.jobs] == ["Machine Learning Engineer"]


def test_short_ai_token_does_not_match_inside_unrelated_words():
    search = LiveJobSearch(
        LiveSearchConfig(enable_remotive=True),
        fetch_json=lambda *_args: {
            "jobs": [
                {
                    "id": 1,
                    "title": "Patient Care Specialist",
                    "company_name": "Health Co",
                    "description": "Maintain patient services.",
                    "url": "https://jobs.example/health",
                    "publication_date": "2026-08-01",
                }
            ]
        },
    )

    result = search.broad_search(CandidatePreferences(target_roles=["AI engineer"]))

    assert result.jobs == []


def test_role_matching_requires_a_relevant_job_title():
    search = LiveJobSearch(
        LiveSearchConfig(enable_remotive=True),
        fetch_json=lambda *_args: {
            "jobs": [
                {
                    "id": 1,
                    "title": "Remote Office Assistant",
                    "company_name": "Office Co",
                    "description": "Support a software engineering leadership team.",
                    "url": "https://jobs.example/assistant",
                    "publication_date": "2026-08-01",
                },
                {
                    "id": 2,
                    "title": "Software Developer",
                    "company_name": "Tech Co",
                    "description": "Build customer applications.",
                    "url": "https://jobs.example/developer",
                    "publication_date": "2026-08-01",
                },
            ]
        },
    )

    result = search.broad_search(CandidatePreferences(target_roles=["software engineer"]))

    assert [job.title for job in result.jobs] == ["Software Developer"]


def test_duplicate_provider_results_are_collapsed():
    payload = {
        "jobs": [
            {
                "id": 2,
                "title": "Software Developer",
                "company_name": "Tech Co",
                "description": "Build customer applications.",
                "url": "https://jobs.example/developer",
                "publication_date": "2026-08-01",
            }
        ]
    }
    search = LiveJobSearch(LiveSearchConfig(enable_remotive=True), fetch_json=lambda *_args: payload)

    result = search.broad_search(
        CandidatePreferences(target_roles=["software engineer", "software developer"])
    )

    assert len(result.jobs) == 1


def test_default_config_has_zero_key_live_source(monkeypatch):
    monkeypatch.delenv("JOBFORGE_GREENHOUSE_BOARDS", raising=False)
    monkeypatch.delenv("JOBFORGE_ENABLE_REMOTIVE", raising=False)

    config = LiveSearchConfig.from_env()

    assert config.greenhouse_boards == (CompanyBoard("Canonical", "canonical"),)
    assert config.enable_remotive is False
