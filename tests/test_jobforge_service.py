from __future__ import annotations

import json
from datetime import date

import pytest

from app.schemas.candidate import CandidatePreferences
from app.services.jobforge import JobForgeService, MAX_CV_CHARACTERS
from app.tools.job_search import load_jobs_from_json


def _preferences() -> CandidatePreferences:
    with open("sample_data/preferences.json", encoding="utf-8") as handle:
        return CandidatePreferences.model_validate(json.load(handle))


def test_service_searches_without_persisting_cv():
    cv_text = open("sample_data/cvs/aman_sharma_cv.txt", encoding="utf-8").read()

    result = JobForgeService().search_jobs(
        cv_text,
        _preferences(),
        limit=2,
        use_live_search=False,
    )

    assert result.search_mode == "sample"
    assert len(result.ranked_jobs) == 2
    assert not result.candidate_profile.source_cv or not result.candidate_profile.source_cv.startswith("sample_data/")


def test_service_prepares_only_a_validated_job(monkeypatch):
    monkeypatch.setenv("JOBFORGE_USE_OPENAI", "false")
    cv_text = open("sample_data/cvs/aman_sharma_cv.txt", encoding="utf-8").read()
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]

    result = JobForgeService().prepare_application(
        cv_text,
        _preferences(),
        job,
        today=date(2025, 3, 10),
    )

    assert result.job_id == job.job_id
    assert result.quality_checks.unsupported_claims == 0
    assert result.tailored_cv_latex


def test_service_rejects_oversized_cv():
    with pytest.raises(ValueError, match="must not exceed"):
        JobForgeService().search_jobs(
            "x" * (MAX_CV_CHARACTERS + 1),
            CandidatePreferences(),
            use_live_search=False,
        )
