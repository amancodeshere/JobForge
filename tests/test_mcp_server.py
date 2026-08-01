from __future__ import annotations

import asyncio
from datetime import date
import json

from app.schemas.application import JobSearchResult, RankedJob, ScoreBreakdown
from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.tools.job_search import load_jobs_from_json
from jobforge_mcp.http import BearerTokenMiddleware
from jobforge_mcp.models import SearchJobsRequest
from jobforge_mcp.server import mcp, search_jobs


def test_mcp_registers_only_the_approved_tools():
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {"search_jobs", "prepare_application"}
    search_tool = next(tool for tool in tools if tool.name == "search_jobs")
    assert search_tool.inputSchema["properties"]["request"]["$ref"]
    assert search_tool.outputSchema is not None


def test_search_tool_returns_ranked_matches_without_candidate_evidence(monkeypatch):
    job = load_jobs_from_json("sample_data/jobs/jobs.json")[0]
    score = ScoreBreakdown(overall_score=83, components={}, weights={})
    fake_result = JobSearchResult(
        candidate_profile=CandidateProfile(),
        search_mode="live",
        search_sources=["test-provider"],
        discovered_count=1,
        validated_count=1,
        validation_date=date(2026, 8, 2),
        ranked_jobs=[RankedJob(job=job, score_breakdown=score)],
    )
    monkeypatch.setattr("jobforge_mcp.server.service.search_jobs", lambda *_args, **_kwargs: fake_result)

    response = search_jobs(
        SearchJobsRequest(
            cv_text="Candidate\nPython developer",
            preferences=CandidatePreferences(),
            limit=1,
        )
    )

    assert response.matches[0].job.job_id == job.job_id
    assert response.matches[0].score_breakdown.overall_score == 83
    assert "candidate_profile" not in response.model_dump()


def test_remote_transport_fails_closed_and_rejects_invalid_tokens(monkeypatch):
    async def accepted(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    protected_app = BearerTokenMiddleware(accepted)
    monkeypatch.delenv("JOBFORGE_MCP_API_TOKEN", raising=False)
    missing_status, _headers, _body = asyncio.run(_request(protected_app, "/mcp"))
    health_status, _headers, health_body = asyncio.run(_request(protected_app, "/health"))

    monkeypatch.setenv("JOBFORGE_MCP_API_TOKEN", "correct-token")
    invalid_status, invalid_headers, _body = asyncio.run(
        _request(protected_app, "/mcp", authorization="Bearer wrong-token")
    )
    valid_status, _headers, _body = asyncio.run(
        _request(protected_app, "/mcp", authorization="Bearer correct-token")
    )

    assert missing_status == 503
    assert health_status == 200
    assert json.loads(health_body) == {"status": "locked", "authentication_configured": False}
    assert invalid_status == 401
    assert invalid_headers[b"www-authenticate"] == b"Bearer"
    assert valid_status == 204


async def _request(app, path: str, authorization: str | None = None) -> tuple[int, dict[bytes, bytes], bytes]:
    messages = []
    headers = [] if authorization is None else [(b"authorization", authorization.encode("ascii"))]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], dict(start.get("headers", [])), body
