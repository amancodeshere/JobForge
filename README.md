# JobForge

JobForge is a multi-agent employability assistant. It reads a candidate CV and preferences, discovers current jobs from live provider APIs and public company boards, validates eligibility, ranks matches with deterministic scoring, and generates grounded application packages. A controlled sample dataset remains available for offline demos and tests.

## Quick start

```bash
uv sync --extra dev
uv run python main.py run
uv run python main.py run --live
uv run python main.py validate
uv run python main.py doctor
uv run python main.py export-cv --payload sample_data/expected_outputs/latest_run.json
uv run pytest
uv run streamlit run dashboard/streamlit_app.py
uv run python -m jobforge_mcp.server
```

The CLI sample run writes `sample_data/expected_outputs/latest_run.json`. The deployed dashboard keeps user runs in `st.session_state` and temporary files, so uploaded CV output is not written back to the repo path.

## Railway deployment

This project is configured as one Railway web service with Streamlit acting as both frontend and lightweight backend.

1. Push the repo to GitHub.
2. Create a Railway project from that GitHub repo.
3. Railway will use `railway.toml`.
4. Add environment variables:

```text
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5-mini
JOBFORGE_USE_OPENAI=true
JOBFORGE_DEMO_DATE=2026-08-01
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
ADZUNA_COUNTRY=au
SERPAPI_API_KEY=your_serpapi_key
SERPAPI_COUNTRY=au
SERPAPI_LANGUAGE=en
JOBFORGE_GREENHOUSE_BOARDS=Canonical=canonical,Culture Amp=cultureamp
JOBFORGE_LEVER_SITES=Deputy=deputy
```

Optional cost-saving mode:

```text
JOBFORGE_USE_OPENAI=false
```

The Railway start command is:

```bash
python -m streamlit run dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port ${PORT:-8501} --server.headless true
```

The health check path is:

```text
/_stcore/health
```

Pre-deploy checks:

```bash
uv run python main.py run
uv run python main.py validate
uv run python main.py doctor
uv run pytest
```

The repo also includes a GitHub Actions workflow that installs from `requirements.txt`, runs tests, validates the sample payload, and starts Streamlit long enough to check `/_stcore/health`.

### Optional MCP service

JobForge also provides an allowlisted MCP server with separate `search_jobs` and `prepare_application` tools. Run it locally over stdio with:

```bash
uv run python -m jobforge_mcp.server
```

For remote access, deploy a second Railway service from the same repository using `/railway.mcp.toml` and set `JOBFORGE_MCP_API_TOKEN`. The Streamlit service remains configured by `/railway.toml`; do not replace it. See [docs/mcp.md](docs/mcp.md) for client configuration, remote deployment, authentication, and security boundaries.

## What works

- Candidate Profile Agent extracts CV-backed skills, projects, career themes, and evidence IDs.
- Broad Opportunity Scout searches Adzuna and, when configured for Australia, uses one SerpApi request to search selected roles and locations across SEEK, Indeed, LinkedIn, Glassdoor, Australian government portals, specialist boards, and established ATS-hosted company careers pages. Only recognized direct-listing URLs are accepted. Other configured countries continue to use SerpApi Google Jobs where that engine is supported.
- Targeted Job Researcher reads current postings from configured Greenhouse and Lever company boards. Canonical's public Greenhouse board is enabled by default so live mode works without an API key.
- Experience level is a multi-select, covering internship, graduate, entry-level, junior, associate, mid-level, senior, staff, principal, manager, and director searches.
- Job validation rejects stale, wrong-employment-type, missing-description, citizenship-gated, and experience-level mismatched roles.
- Candidate exclusions support exact company names and title/description keywords; JSON constraints can also use `Exclude company: ...` or `Exclude keyword: ...`.
- Relevance scoring is deterministic:
  - 30% required skill match
  - 15% preferred skill match
  - 15% experience-level compatibility
  - 15% career-interest alignment
  - 10% project-domain similarity
  - 10% eligibility compatibility
  - 5% freshness
- Application Tailor produces a tailored CV draft, trusted escaped LaTeX source, verified PDF, and cover letter using evidence mappings. PDF compilation uses Tectonic and is cached per selected application in the dashboard.
- Quality checks reject unsupported claims, company-name mismatches, invalid rankings, malformed dashboard payloads, and unsafe LLM drafts.
- Streamlit dashboard shows recommended roles, job details, score breakdowns, application packages, agent activity, and validation checkpoints.
- Optional OpenAI drafting uses `OPENAI_MODEL`, defaulting to `gpt-5-mini`, while deterministic validation still checks the output. If OpenAI fails or returns unsafe copy, the app visibly falls back to deterministic generation.

## CLI

```bash
uv run python main.py run \
  --cv sample_data/cvs/aman_sharma_cv.txt \
  --preferences sample_data/preferences.json \
  --jobs sample_data/jobs/jobs.json \
  --output sample_data/expected_outputs/latest_run.json \
  --top-n 5
```

Live search:

```bash
uv run python main.py run --live --no-sample-fallback
```

Live runs report their exact mode and sources. If all live sources fail or return no records, the default behavior is an explicitly labelled `sample_fallback`; use `--no-sample-fallback` when only current listings are acceptable.

## Live job sources

- **Adzuna** provides broad geographic and keyword search. Create credentials at the Adzuna developer portal and set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.
- **SerpApi multi-board discovery** is the primary Australian indexed-search integration. Set `SERPAPI_API_KEY` with `SERPAPI_COUNTRY=au`; JobForge combines all selected roles, locations, and credible site scopes into one Google Australia request per workflow. It accepts direct listings from SEEK, Indeed, LinkedIn, Glassdoor, Workforce Australia, APS Jobs, selected state-government and specialist boards, plus Greenhouse, Lever, Workday, Ashby, SmartRecruiters, and Workable. Search/category pages, unknown hosts, and malformed URLs are rejected.
- **SerpApi Google Jobs** remains available when `SERPAPI_COUNTRY` is set to a country supported by that engine. JobForge preserves the observed publisher and a valid original application link.
- **Greenhouse** public job-board GET endpoints require no key. Configure comma-separated `Company=board_token` entries in `JOBFORGE_GREENHOUSE_BOARDS`.
- **Lever** public postings endpoints require no key. Configure comma-separated `Company=site_token` entries in `JOBFORGE_LEVER_SITES`.
- **Remotive** is opt-in with `JOBFORGE_ENABLE_REMOTIVE=true`. Its public API requires source attribution and has strict rate guidance, so it is disabled by default for multi-user deployments.

JobForge links candidates back to the provider's original listing and shows the source on every result. The indexed search consumes only SerpApi's structured Google result fields; it does not fetch or scrape the listed job-board pages, access logged-in pages, or submit applications automatically.

No service can honestly guarantee every listing on every job site. JobForge reports exactly which providers were attempted, isolates provider failures, and combines broad indexed discovery with direct public ATS boards. Coverage depends on Google's crawl freshness and ranking; unrestricted candidate-search APIs for LinkedIn, Indeed, SEEK, and Glassdoor are not assumed where access is unavailable or partner-gated.

See [docs/live-search.md](docs/live-search.md) for provider behavior, configuration, safety boundaries, and the Agent Reach evaluation.

Use a real PDF or DOCX with `--cv path/to/cv.pdf`. PDF parsing uses `pypdf`; DOCX parsing uses `python-docx`.

Export a compiled tailored CV from any fresh workflow payload:

```bash
uv run python main.py export-cv \
  --payload sample_data/expected_outputs/latest_run.json \
  --job-index 0 \
  --output output/pdf/tailored_cv.pdf
```

The compiler accepts only JobForge's trusted template, escapes all CV and job values, disables shell escape when using `pdflatex`, and reopens every PDF to verify its page count, extractable text, and candidate name. Railway installs Tectonic through `nixpacks.toml`.

Deployment readiness:

```bash
uv run python main.py doctor
uv run python main.py doctor --require-openai
```

## Cost controls

- Australian indexed discovery uses exactly one SerpApi request per live workflow, regardless of how many selected roles or supported sites are included. `JOBFORGE_MAX_SEARCH_QUERIES` controls how many role phrases are combined into that request; it no longer multiplies Australian SerpApi calls.
- Exact repeated SerpApi searches retain the provider's default cache behavior, so identical requests may be served from SerpApi's free one-hour cache.
- Keep search on approved APIs or the sample fallback dataset during demos.
- Run deterministic filtering and scoring before any LLM drafting.
- Generate application packages only for the top jobs.
- The orchestrator scores all validated jobs first and only calls the tailoring agent for `top_n`.
- Candidate profiling overlaps broad network discovery; independent providers and selected-job drafts use bounded worker pools. Tune drafting concurrency with `JOBFORGE_TAILOR_WORKERS` (default `3`).
- Keep `JOBFORGE_USE_OPENAI=false` for free demos that do not need generated prose.
- Use `gpt-5-mini` for the drafting path unless a higher-accuracy model is required.

## Architecture

```text
CV + preferences
      |
      v
Orchestrator / Quality Controller
      |
      +--> Candidate Profile Agent
      +--> Broad Opportunity Scout
      +--> Targeted Job Researcher
      +--> Job validation + scoring
      +--> Application Tailor
      +--> Dashboard Agent
```

Each stage exchanges Pydantic JSON objects and emits a validation checkpoint.

The Streamlit UI, CLI, and MCP transport share `JobForgeService`; MCP does not replace or bypass the live provider layer.

## Extension points

Add providers behind `app/tools/live_job_search.py` and normalize their output to `JobResult` objects so deduplication, validation, scoring, and dashboard rendering continue to work.
