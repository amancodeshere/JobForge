# JobForge

JobForge is a hackathon-ready multi-agent employability assistant. It reads a candidate CV and preferences, discovers jobs from a controlled fallback dataset, validates eligibility, ranks matches with deterministic scoring, and generates grounded application packages.

## Quick start

```bash
uv sync --extra dev
uv run python main.py run
uv run python main.py validate
uv run python main.py doctor
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
- Broad Opportunity Scout and Targeted Job Researcher search the sample/fallback jobs with different query strategies.
- Job validation rejects senior, stale, wrong-employment-type, missing-description, and citizenship-gated roles.
- Relevance scoring is deterministic:
  - 30% required skill match
  - 15% preferred skill match
  - 15% experience-level compatibility
  - 15% career-interest alignment
  - 10% project-domain similarity
  - 10% eligibility compatibility
  - 5% freshness
- Application Tailor produces a tailored CV draft and cover letter using evidence mappings.
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

Use a real PDF or DOCX with `--cv path/to/cv.pdf`. PDF parsing uses `pypdf`; DOCX parsing uses `python-docx`.

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

Replace `app/tools/job_search.py` with approved job-search APIs or company career feeds. Keep the output as `JobResult` objects so deduplication, validation, scoring, and dashboard rendering continue to work.
