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

## What works

- Candidate Profile Agent extracts CV-backed skills, projects, career themes, and evidence IDs.
- Broad Opportunity Scout searches Adzuna and, when configured for Australia, makes SEEK the primary SerpApi discovery target through Google's Australian web index. Results must be direct `seek.com.au/job/...` listings and retain the original SEEK application link. Other configured countries continue to use SerpApi Google Jobs where that engine is supported.
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
- **SerpApi SEEK discovery** is the primary Australian board integration. Set `SERPAPI_API_KEY` with `SERPAPI_COUNTRY=au`; JobForge searches Google's Australian index for direct SEEK job pages, rejects search/category pages and non-SEEK hosts, and retains the original SEEK application URL. This avoids the unsupported `google_jobs&gl=au` combination and does not scrape SEEK pages from the deployed backend.
- **SerpApi Google Jobs** remains available when `SERPAPI_COUNTRY` is set to a country supported by that engine. JobForge preserves the observed publisher and a valid original application link.
- **Greenhouse** public job-board GET endpoints require no key. Configure comma-separated `Company=board_token` entries in `JOBFORGE_GREENHOUSE_BOARDS`.
- **Lever** public postings endpoints require no key. Configure comma-separated `Company=site_token` entries in `JOBFORGE_LEVER_SITES`.
- **Remotive** is opt-in with `JOBFORGE_ENABLE_REMOTIVE=true`. Its public API requires source attribution and has strict rate guidance, so it is disabled by default for multi-user deployments.

JobForge links candidates back to the provider's original listing and shows the source on every result. It does not fetch or scrape SEEK listing pages, scrape logged-in job boards, or submit applications automatically.

No service can honestly guarantee every listing on every job site. JobForge reports exactly which providers were attempted, isolates provider failures, and combines broad indexed discovery with direct public ATS boards. SEEK index coverage depends on Google's crawl freshness; unrestricted candidate-search APIs for LinkedIn, Indeed, SEEK, and Glassdoor are not assumed where access is unavailable or partner-gated.

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

## Extension points

Add providers behind `app/tools/live_job_search.py` and normalize their output to `JobResult` objects so deduplication, validation, scoring, and dashboard rendering continue to work.
