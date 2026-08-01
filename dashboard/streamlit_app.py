from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from html import escape

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.application import WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.tools.experience_levels import EXPERIENCE_LEVELS
from app.tools.llm_client import configured_model, openai_enabled


DEFAULT_OUTPUT = ROOT / "sample_data/expected_outputs/latest_run.json"
DEFAULT_CV = ROOT / "sample_data/cvs/aman_sharma_cv.txt"
DEFAULT_JOBS = ROOT / "sample_data/jobs/jobs.json"
DEV_MODE = os.getenv("JOBFORGE_DEV_MODE", "false").lower() in {"1", "true", "yes"}


st.set_page_config(page_title="JobForge", layout="wide")


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --jf-bg: #0b1020;
            --jf-bg-soft: #111827;
            --jf-sidebar: #07111f;
            --jf-surface: #141c2f;
            --jf-surface-2: #19243a;
            --jf-line: #2b3a55;
            --jf-ink: #f6f8ff;
            --jf-muted: #aebbd2;
            --jf-teal: #2dd4bf;
            --jf-blue: #60a5fa;
            --jf-violet: #a78bfa;
            --jf-amber: #fbbf24;
            --jf-danger: #fb7185;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(45, 212, 191, 0.16), transparent 28rem),
                radial-gradient(circle at top right, rgba(96, 165, 250, 0.14), transparent 26rem),
                linear-gradient(180deg, var(--jf-bg) 0%, #0f172a 52%, #121826 100%);
            color: var(--jf-ink);
        }
        .block-container {
            padding-top: 1.5rem;
            max-width: 1180px;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--jf-sidebar) 0%, #0d1b2f 100%);
            border-right: 1px solid var(--jf-line);
        }
        [data-testid="stSidebar"] * {
            color: var(--jf-ink);
        }
        h1, h2, h3, h4, h5, h6, p, label, span, div {
            color: var(--jf-ink);
        }
        h2, h3 {
            letter-spacing: 0;
        }
        .stTextInput input,
        .stNumberInput input,
        .stTextArea textarea,
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stNumberInput input,
        [data-testid="stSidebar"] .stTextArea textarea {
            background-color: #0f172a;
            border: 1px solid #334155;
            color: #f8fafc;
            caret-color: var(--jf-teal);
            border-radius: 8px;
        }
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: #94a3b8;
            opacity: 1;
        }
        .stTextInput input:focus,
        .stNumberInput input:focus,
        .stTextArea textarea:focus {
            border-color: var(--jf-teal);
            box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.45);
        }
        div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #0f172a;
            border-color: #334155;
            border-radius: 8px;
        }
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg,
        [data-testid="stSidebar"] div[data-baseweb="select"] input,
        [data-testid="stSidebar"] div[data-baseweb="select"] span,
        [data-testid="stSidebar"] div[data-baseweb="select"] svg {
            color: #f8fafc;
            fill: #f8fafc;
        }
        div[data-baseweb="tag"] {
            background-color: rgba(45, 212, 191, 0.16);
            border: 1px solid rgba(45, 212, 191, 0.36);
        }
        div[data-baseweb="popover"],
        ul[role="listbox"] {
            background-color: #111827;
            border: 1px solid #334155;
        }
        li[role="option"],
        li[role="option"] span {
            color: #f8fafc;
        }
        li[role="option"]:hover {
            background-color: #1e293b;
        }
        [data-testid="stFileUploader"] section {
            background-color: rgba(15, 23, 42, 0.72);
            border-color: #334155;
            border-radius: 8px;
        }
        [data-testid="stFileUploader"] section * {
            color: #f8fafc;
        }
        .jf-title {
            border: 1px solid var(--jf-line);
            border-left: 6px solid var(--jf-teal);
            background: linear-gradient(135deg, rgba(20, 28, 47, 0.96), rgba(25, 36, 58, 0.88));
            border-radius: 8px;
            padding: 1.15rem 1.25rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.24);
        }
        .jf-title h1 {
            font-size: 2.6rem;
            margin: 0;
            letter-spacing: 0;
            color: var(--jf-ink);
        }
        .jf-title p {
            color: var(--jf-muted);
            margin: 0.2rem 0 0;
        }
        .jf-hero-row {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
        }
        .jf-pill {
            border: 1px solid rgba(45, 212, 191, 0.42);
            background: rgba(45, 212, 191, 0.1);
            color: #cffff8;
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .stAlert {
            background: var(--jf-surface);
            border: 1px solid var(--jf-line);
            color: var(--jf-ink);
        }
        div[data-testid="stMetric"] {
            background: var(--jf-surface);
            border: 1px solid var(--jf-line);
            border-top: 4px solid var(--jf-blue);
            border-radius: 8px;
            padding: 0.9rem;
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--jf-ink);
        }
        div.stButton > button,
        div.stDownloadButton > button,
        a[data-testid="stLinkButton"] {
            border-radius: 8px;
            border: 1px solid var(--jf-teal);
            background: linear-gradient(135deg, #0f766e, #2563eb);
            color: #ffffff;
            font-weight: 650;
        }
        div.stButton > button:hover,
        div.stDownloadButton > button:hover,
        a[data-testid="stLinkButton"]:hover {
            border-color: var(--jf-amber);
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            color: white;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--jf-line);
            border-radius: 8px;
            overflow: hidden;
            background: var(--jf-surface);
        }
        .jf-section-title {
            margin-top: 1.2rem;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
        }
        .jf-section-title h2 {
            margin: 0;
            font-size: 1.25rem;
        }
        .jf-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 0.9rem;
            margin-bottom: 1.2rem;
        }
        .jf-card {
            min-height: 210px;
            background: linear-gradient(180deg, rgba(25, 36, 58, 0.96), rgba(20, 28, 47, 0.96));
            border: 1px solid var(--jf-line);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.2);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .jf-card:hover {
            border-color: rgba(45, 212, 191, 0.7);
        }
        .jf-card-top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.75rem;
        }
        .jf-job-title {
            color: #ffffff;
            font-weight: 760;
            font-size: 1.02rem;
            line-height: 1.25;
            margin-bottom: 0.25rem;
        }
        .jf-company {
            color: var(--jf-muted);
            font-size: 0.9rem;
        }
        .jf-score {
            min-width: 3.4rem;
            text-align: center;
            color: #06111f;
            background: linear-gradient(135deg, var(--jf-teal), var(--jf-blue));
            border-radius: 8px;
            padding: 0.45rem 0.35rem;
            font-weight: 850;
        }
        .jf-score span {
            display: block;
            color: rgba(6, 17, 31, 0.82);
            font-size: 0.68rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .jf-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.8rem 0;
        }
        .jf-chip {
            border: 1px solid rgba(174, 187, 210, 0.25);
            background: rgba(15, 23, 42, 0.72);
            color: #e5edff;
            border-radius: 999px;
            padding: 0.24rem 0.55rem;
            font-size: 0.76rem;
            font-weight: 650;
        }
        .jf-link-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
            border-top: 1px solid rgba(43, 58, 85, 0.72);
            padding-top: 0.8rem;
        }
        .jf-recommendation {
            color: #dbeafe;
            font-size: 0.82rem;
            font-weight: 680;
            text-transform: capitalize;
        }
        .jf-verify {
            color: #06111f !important;
            background: var(--jf-teal);
            border: 1px solid var(--jf-teal);
            border-radius: 8px;
            padding: 0.42rem 0.72rem;
            text-decoration: none !important;
            font-weight: 800;
            white-space: nowrap;
        }
        .jf-verify:hover {
            background: var(--jf-amber);
            border-color: var(--jf-amber);
            color: #06111f !important;
        }
        .jf-panel {
            background: rgba(20, 28, 47, 0.74);
            border: 1px solid var(--jf-line);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.9rem;
        }
        .jf-panel h3 {
            margin-top: 0;
            margin-bottom: 0.7rem;
            font-size: 1rem;
        }
        .jf-list {
            margin: 0;
            padding-left: 1rem;
        }
        .jf-list li {
            color: #e5edff;
            margin: 0.35rem 0;
            line-height: 1.38;
        }
        .jf-muted {
            color: var(--jf-muted);
        }
        [data-testid="stMarkdownContainer"] a {
            color: var(--jf-teal);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            background: var(--jf-surface-2);
            color: var(--jf-ink);
        }
        .stTabs [aria-selected="true"] {
            border-bottom: 3px solid var(--jf-teal);
        }
        .jf-link {
            color: var(--jf-teal);
            font-weight: 650;
            text-decoration: none;
        }
        .jf-link:hover {
            color: var(--jf-amber);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_theme()
st.markdown(
    """
    <div class="jf-title">
      <div class="jf-hero-row">
        <div>
          <h1>JobForge</h1>
          <p>Grounded job discovery, ranking, and tailored applications.</p>
        </div>
        <div class="jf-pill">Deployment ready</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Run")
    uploaded_cv = st.file_uploader("CV", type=["pdf", "docx", "txt", "md"])
    uploaded_jobs = st.file_uploader("Jobs JSON", type=["json"])
    use_sample_cv = st.checkbox("Use sample CV", value=True)
    use_live_search = st.checkbox("Search live jobs", value=True)
    sample_fallback = st.checkbox("Use sample jobs if live search is unavailable", value=True)
    interests = st.text_area(
        "Career interests",
        "machine learning engineering\ndata science\nAI engineering\nsoftware engineering",
    )
    locations = st.text_input("Locations", "Sydney, Remote Australia")
    experience_levels = st.multiselect(
        "Experience levels",
        EXPERIENCE_LEVELS,
        default=["internship", "graduate", "entry-level", "junior", "associate"],
    )
    employment_types = st.text_input("Employment types", "Full-time")
    max_years = st.number_input("Max years required", min_value=0, max_value=10, value=2)
    posted_within = st.number_input("Posted within days", min_value=1, max_value=365, value=30)
    work_rights = st.text_input("Work rights", "Australian unrestricted work rights")
    top_n = st.number_input("Application packages", min_value=1, max_value=10, value=5)
    run_clicked = st.button("Run agents", type="primary")

    st.divider()
    st.caption(f"OpenAI: {'enabled' if openai_enabled() else 'disabled'}")
    st.caption(f"Model: {configured_model()}")
    load_sample = st.button("Load sample results")
    if DEV_MODE:
        payload_path = st.text_input("Load saved payload", str(DEFAULT_OUTPUT))
    else:
        payload_path = str(DEFAULT_OUTPUT)


def _split_lines(value: str) -> list[str]:
    items: list[str] = []
    for raw in value.replace(",", "\n").splitlines():
        item = raw.strip()
        if item:
            items.append(item)
    return items


def _path_from_upload(uploaded_file, temp_dir: Path, fallback: Path) -> str:
    if uploaded_file is None:
        return str(fallback)
    suffix = Path(uploaded_file.name).suffix or ".txt"
    path = temp_dir / f"upload{suffix}"
    path.write_bytes(uploaded_file.getbuffer())
    return str(path)


def _load_sample_payload() -> WorkflowResult | None:
    if not DEFAULT_OUTPUT.exists():
        return None
    return WorkflowResult.model_validate_json(DEFAULT_OUTPUT.read_text(encoding="utf-8"))


def _preferences_from_form() -> CandidatePreferences:
    career_interests = _split_lines(interests)
    selected_levels = experience_levels or ["graduate"]
    return CandidatePreferences(
        target_roles=[
            interest.replace("engineering", "engineer")
            for interest in career_interests
        ],
        career_interests=career_interests,
        locations=_split_lines(locations),
        experience_level=selected_levels[0],
        experience_levels=selected_levels,
        employment_types=_split_lines(employment_types),
        max_years_experience=int(max_years),
        posted_within_days=int(posted_within),
        work_rights=work_rights,
        constraints=[
            f"Posted within the last {int(posted_within)} days",
            f"No roles requiring more than {int(max_years)} years of experience",
        ],
    )


if run_clicked:
    if uploaded_cv is None and not use_sample_cv:
        st.error("Upload a CV or enable the sample CV.")
        st.stop()
    with st.spinner("Running agents and validation checks"):
        try:
            with TemporaryDirectory(prefix="jobforge-") as temp:
                temp_dir = Path(temp)
                cv_path = _path_from_upload(uploaded_cv, temp_dir, DEFAULT_CV)
                jobs_path = _path_from_upload(uploaded_jobs, temp_dir, DEFAULT_JOBS)
                result = OrchestratorAgent(sample_jobs_path=jobs_path).run(
                    cv_path=cv_path,
                    preferences=_preferences_from_form(),
                    output_path=str(temp_dir / "latest_run.json"),
                    top_n=int(top_n),
                    use_live_search=use_live_search,
                    sample_fallback=sample_fallback,
                )
            st.session_state["workflow_result"] = result
        except Exception as exc:
            st.error(f"Workflow failed: {exc}")
            st.stop()
    st.success("Workflow completed.")
elif "workflow_result" in st.session_state:
    result = st.session_state["workflow_result"]
elif load_sample:
    try:
        result = _load_sample_payload()
        if result is None:
            st.error("Sample payload is missing. Run `uv run python main.py run` locally and commit the result.")
            st.stop()
        st.session_state["workflow_result"] = result
    except Exception as exc:
        st.error(f"Could not load sample payload: {exc}")
        st.stop()
elif DEV_MODE and Path(payload_path).resolve() == DEFAULT_OUTPUT.resolve() and Path(payload_path).exists():
    try:
        result = WorkflowResult.model_validate_json(Path(payload_path).read_text(encoding="utf-8"))
    except Exception as exc:
        st.error(f"Could not load payload: {exc}")
        st.stop()
else:
    st.info("Run the agents from the sidebar or load the sample results.")
    st.stop()

metrics = st.columns(3)
metrics[0].metric("Roles discovered", result.discovered_count)
metrics[1].metric("Validated", result.validated_count)
metrics[2].metric("Recommended", result.recommended_count)

st.caption(f"Search mode: {result.search_mode} · Sources: {', '.join(result.search_sources) or 'none'}")
for warning in result.search_warnings:
    st.warning(warning)

st.markdown(
    """
    <div class="jf-section-title">
      <h2>Recommended jobs</h2>
      <span class="jf-muted">Ranked by deterministic relevance score</span>
    </div>
    """,
    unsafe_allow_html=True,
)


def _recommendation_label(value: str) -> str:
    return value.replace("_", " ")


def _job_card_html(application) -> str:
    job = application.job
    return f"""
    <div class="jf-card">
      <div>
        <div class="jf-card-top">
          <div>
            <div class="jf-job-title">{escape(job.title)}</div>
            <div class="jf-company">{escape(job.company)}</div>
          </div>
          <div class="jf-score">{application.relevance_score}<span>score</span></div>
        </div>
        <div class="jf-meta">
          <span class="jf-chip">{escape(job.location)}</span>
          <span class="jf-chip">{escape(job.employment_type)}</span>
          <span class="jf-chip">{escape(job.experience_required)}</span>
        </div>
      </div>
      <div class="jf-link-row">
        <span class="jf-recommendation">{escape(_recommendation_label(application.recommendation.value))}</span>
        <a class="jf-verify" href="{escape(job.application_url)}" target="_blank" rel="noopener noreferrer">Verify job</a>
      </div>
    </div>
    """


def _list_panel_html(title: str, items: list[str]) -> str:
    rendered_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"""
    <div class="jf-panel">
      <h3>{escape(title)}</h3>
      <ul class="jf-list">{rendered_items}</ul>
    </div>
    """


st.markdown(
    '<div class="jf-grid">' + "".join(_job_card_html(application) for application in result.applications) + "</div>",
    unsafe_allow_html=True,
)

job_labels = [f"{app.job.title} - {app.job.company}" for app in result.applications]
if job_labels:
    selected = st.selectbox("Job detail", job_labels)
    application = result.applications[job_labels.index(selected)]

    left, right = st.columns([1.1, 0.9])
    with left:
        st.markdown(
            f"""
            <div class="jf-panel">
              <h3>{escape(application.job.title)}</h3>
              <p class="jf-muted">{escape(application.job.company)} · {escape(application.job.location)}</p>
              <p>{escape(application.job_summary)}</p>
              <p class="jf-muted">Application copy: {escape(application.generation_source)}</p>
              <a class="jf-verify" href="{escape(application.job.application_url)}" target="_blank" rel="noopener noreferrer">Verify listing</a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        match_items = [
            f"{match.requirement}: {match.candidate_evidence}"
            for match in application.matching_evidence
        ]
        st.markdown(_list_panel_html("Why it matches", match_items), unsafe_allow_html=True)
        gap_items = application.skill_gaps or ["No major listed skill gaps identified."]
        st.markdown(_list_panel_html("Potential gaps", gap_items), unsafe_allow_html=True)

    with right:
        st.markdown('<div class="jf-panel"><h3>Score breakdown</h3></div>', unsafe_allow_html=True)
        st.metric("Relevance score", f"{application.relevance_score}/100")
        st.bar_chart(application.score_breakdown.components)
        st.markdown(
            _list_panel_html("Interview preparation", application.interview_preparation_topics),
            unsafe_allow_html=True,
        )

    cv_tab, letter_tab, checks_tab = st.tabs(["Tailored CV", "Cover letter", "Quality checks"])
    cv_tab.markdown(application.tailored_cv)
    cv_tab.download_button(
        "Download CV draft",
        application.tailored_cv,
        file_name=f"{application.job_id}_tailored_cv.md",
        mime="text/markdown",
    )
    letter_tab.text(application.cover_letter)
    letter_tab.download_button(
        "Download cover letter",
        application.cover_letter,
        file_name=f"{application.job_id}_cover_letter.txt",
        mime="text/plain",
    )
    checks_tab.json(application.quality_checks.model_dump())

st.subheader("Agent activity")
timeline = [
    {
        "Agent": health.agent,
        "Status": health.status,
        "Tool calls": health.tool_calls,
        "Valid": health.valid_results,
        "Invalid": health.invalid_results,
        "Errors": health.execution_errors,
        "Notes": "; ".join(health.notes) if health.notes else "-",
    }
    for health in result.agent_health
]
st.dataframe(timeline, use_container_width=True, hide_index=True)

st.subheader("Validation checkpoints")
checks = [
    {
        "Part": check.part,
        "Passed": check.passed,
        "Issues": "; ".join(check.issues) if check.issues else "-",
    }
    for check in result.validation_checks
]
st.dataframe(checks, use_container_width=True, hide_index=True)
