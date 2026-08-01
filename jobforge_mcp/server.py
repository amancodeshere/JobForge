from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.services.jobforge import JobForgeService
from jobforge_mcp.models import (
    PrepareApplicationRequest,
    PrepareApplicationResponse,
    SearchJobMatch,
    SearchJobsRequest,
    SearchJobsResponse,
)


mcp = FastMCP(
    "JobForge",
    instructions=(
        "Search current credible job sources, rank validated listings against CV evidence, "
        "and prepare evidence-grounded application materials. Search is live-only and never "
        "falls back to demonstration data. Never invent candidate experience."
    ),
    json_response=True,
    stateless_http=True,
    max_request_body_size=512 * 1024,
)
service = JobForgeService()


@mcp.tool(
    title="Search live jobs",
    description=(
        "Search live configured job providers, validate listings, and return ranked matches. "
        "This can consume provider quota but does not draft application materials."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def search_jobs(request: SearchJobsRequest) -> SearchJobsResponse:
    result = service.search_jobs(
        request.cv_text,
        request.preferences,
        limit=request.limit,
        use_live_search=True,
        sample_fallback=False,
    )
    return SearchJobsResponse(
        search_mode=result.search_mode,
        search_sources=result.search_sources,
        search_warnings=result.search_warnings,
        discovered_count=result.discovered_count,
        validated_count=result.validated_count,
        validation_date=result.validation_date,
        matches=[
            SearchJobMatch(job=ranked.job, score_breakdown=ranked.score_breakdown)
            for ranked in result.ranked_jobs
        ],
    )


@mcp.tool(
    title="Prepare application",
    description=(
        "Revalidate one selected listing and prepare an evidence-grounded tailored CV, "
        "trusted LaTeX source, cover letter, and interview topics."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def prepare_application(request: PrepareApplicationRequest) -> PrepareApplicationResponse:
    application = service.prepare_application(
        request.cv_text,
        request.preferences,
        request.job,
    )
    return PrepareApplicationResponse(application=application)


if __name__ == "__main__":
    mcp.run(transport="stdio")

