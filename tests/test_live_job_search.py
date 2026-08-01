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
