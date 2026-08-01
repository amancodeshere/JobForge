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
from app.services.latex_resume import LatexCompileError, compile_resume_pdf
from app.tools.experience_levels import EXPERIENCE_LEVELS
from app.tools.llm_client import configured_model, openai_enabled


DEFAULT_OUTPUT = ROOT / "sample_data/expected_outputs/latest_run.json"
DEFAULT_CV = ROOT / "sample_data/cvs/aman_sharma_cv.txt"
DEFAULT_JOBS = ROOT / "sample_data/jobs/jobs.json"
DEV_MODE = os.getenv("JOBFORGE_DEV_MODE", "false").lower() in {"1", "true", "yes"}


st.set_page_config(page_title="JobForge", layout="wide")


@st.cache_data(show_spinner=False, max_entries=20)
def _compile_cv_pdf(latex_source: str, candidate_name: str) -> tuple[bytes, str, int]:
    compiled = compile_resume_pdf(latex_source, expected_name=candidate_name)
    return compiled.pdf_bytes, compiled.engine, compiled.page_count


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --jf-bg: #090e18;
            --jf-bg-soft: #0f1726;
            --jf-sidebar: #07101c;
            --jf-surface: #131d30;
            --jf-surface-2: #18243a;
            --jf-line: #2a3a54;
            --jf-ink: #f6f8ff;
            --jf-muted: #b8c4d8;
            --jf-teal: #2dd4bf;
            --jf-teal-soft: #99f6e4;
            --jf-blue: #77a9ff;
            --jf-amber: #fbbf24;
            --jf-danger: #fb7185;
            --jf-radius: 10px;
        }
        .stApp {
            background-color: var(--jf-bg);
            color: var(--jf-ink);
        }
        .block-container {
            padding-top: 1.75rem;
            padding-bottom: 4rem;
            max-width: 1240px;
        }
        [data-testid="stSidebar"] {
            background: var(--jf-sidebar);
            border-right: 1px solid var(--jf-line);
            min-width: 320px;
            max-width: 320px;
        }
        [data-testid="stSidebar"][aria-expanded="false"] {
            min-width: 256px;
            max-width: 256px;
        }
        [data-testid="stSidebar"] * {
            color: var(--jf-ink);
        }
        h1, h2, h3, h4, h5, h6, p, label, span, div {
            color: var(--jf-ink);
        }
        h2, h3 {
            letter-spacing: -0.02em;
        }
        [data-testid="stBaseButton-header"] {
            display: none;
        }
        header[data-testid="stHeader"] {
            background: rgba(9, 14, 24, 0.94);
            border-bottom: 1px solid rgba(42, 58, 84, 0.5);
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
            border-radius: var(--jf-radius);
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
            box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.18);
        }
        div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #0f172a;
            border-color: #334155;
            border-radius: var(--jf-radius);
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
            border-radius: var(--jf-radius);
        }
        [data-testid="stFileUploader"] section * {
            color: #f8fafc;
        }
        .jf-title {
            border: 1px solid var(--jf-line);
            background: var(--jf-surface);
            border-radius: var(--jf-radius);
            padding: 1.4rem 1.5rem;
            margin-bottom: 1.1rem;
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28);
        }
        .jf-title h1 {
            font-size: clamp(2.35rem, 5vw, 3.35rem);
            margin: 0;
            letter-spacing: -0.04em;
            line-height: 0.95;
            white-space: nowrap;
            color: var(--jf-ink);
        }
        .jf-title p {
            color: var(--jf-muted);
            margin: 0.55rem 0 0;
            max-width: 58ch;
            line-height: 1.5;
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
            padding: 0.35rem 0.75rem;
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
            border-radius: var(--jf-radius);
            padding: 1rem 1.05rem;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.2);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--jf-ink);
        }
        div.stButton > button,
        div.stDownloadButton > button,
        a[data-testid="stLinkButton"] {
            min-height: 44px;
            border-radius: var(--jf-radius);
            border: 1px solid var(--jf-teal);
            background: var(--jf-teal);
            color: #06111f;
            font-weight: 750;
        }
        div.stButton > button:hover,
        div.stDownloadButton > button:hover,
        a[data-testid="stLinkButton"]:hover {
            border-color: var(--jf-teal-soft);
            background: var(--jf-teal-soft);
            color: #06111f;
            transform: translateY(-1px);
        }
        div.stButton > button:focus-visible,
        div.stDownloadButton > button:focus-visible,
        .jf-verify:focus-visible {
            outline: 3px solid rgba(251, 191, 36, 0.7);
            outline-offset: 3px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--jf-line);
            border-radius: var(--jf-radius);
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
            font-size: clamp(1.4rem, 3vw, 1.8rem);
        }
        .jf-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 0.9rem;
            margin-bottom: 1.2rem;
        }
        .jf-card {
            min-height: 210px;
            background: var(--jf-surface);
            border: 1px solid var(--jf-line);
            border-radius: var(--jf-radius);
            padding: 1.05rem;
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .jf-card:hover {
            border-color: rgba(45, 212, 191, 0.7);
            transform: translateY(-2px);
            box-shadow: 0 18px 42px rgba(0, 0, 0, 0.3);
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
            background: var(--jf-teal);
            border-radius: var(--jf-radius);
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
            border-radius: var(--jf-radius);
            padding: 0.55rem 0.78rem;
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
            background: var(--jf-surface);
            border: 1px solid var(--jf-line);
            border-radius: var(--jf-radius);
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
        .jf-mode-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.55rem;
            color: var(--jf-muted);
            font-size: 0.86rem;
            margin: 0.9rem 0 1.35rem;
        }
        .jf-mode-strip strong {
            color: var(--jf-ink);
        }
        .jf-source {
            border: 1px solid rgba(45, 212, 191, 0.32);
            background: rgba(45, 212, 191, 0.08);
            color: var(--jf-teal-soft);
            border-radius: 999px;
            padding: 0.2rem 0.55rem;
            font-weight: 700;
        }
        .jf-empty {
            border: 1px solid var(--jf-line);
            background: var(--jf-surface);
            border-radius: var(--jf-radius);
            padding: clamp(1.25rem, 4vw, 2.5rem);
            box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
        }
        .jf-empty h2 {
            margin: 0 0 0.55rem;
            font-size: clamp(1.55rem, 4vw, 2.1rem);
        }
        .jf-empty p {
            color: var(--jf-muted);
            max-width: 65ch;
            line-height: 1.55;
        }
        .jf-steps {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            margin-top: 1.4rem;
        }
        .jf-step {
            border-top: 1px solid var(--jf-line);
            padding-top: 0.85rem;
        }
        .jf-step strong {
            display: block;
            color: var(--jf-ink);
            margin-bottom: 0.25rem;
        }
        .jf-step span {
            color: var(--jf-muted);
            font-size: 0.9rem;
            line-height: 1.4;
        }
        [data-testid="stExpander"] {
            border-color: var(--jf-line);
            border-radius: var(--jf-radius);
            background: rgba(15, 23, 38, 0.48);
        }
        .jf-check-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.65rem;
        }
        .jf-check {
            border: 1px solid var(--jf-line);
            border-radius: var(--jf-radius);
            padding: 0.75rem;
            color: var(--jf-muted);
        }
        .jf-check strong {
            color: var(--jf-teal-soft);
            display: block;
            margin-bottom: 0.2rem;
        }
        @media (prefers-reduced-motion: no-preference) {
            .jf-card,
            div.stButton > button,
            div.stDownloadButton > button {
                transition: transform 160ms ease-out, border-color 160ms ease-out, box-shadow 160ms ease-out, background 160ms ease-out;
            }
        }
        @media (max-width: 700px) {
            .block-container {
                padding: 1rem 1rem 3rem;
            }
            .jf-title {
                padding: 1.1rem;
            }
            .jf-hero-row {
                display: block;
            }
            .jf-title h1 {
                font-size: 2.45rem;
                white-space: normal;
                overflow-wrap: normal;
                word-break: keep-all;
            }
            .jf-pill {
                display: inline-block;
                margin-top: 1rem;
            }
            .jf-section-title {
                display: block;
            }
            .jf-section-title .jf-muted {
                display: block;
                margin-top: 0.3rem;
            }
            .jf-grid,
            .jf-steps {
                grid-template-columns: 1fr;
            }
            .jf-card {
                min-height: 0;
            }
            .jf-link-row {
                align-items: stretch;
                flex-direction: column;
            }
            .jf-verify {
                text-align: center;
                min-height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
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
        <div class="jf-pill">Live search · evidence grounded</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Search setup")
    st.caption("Define the roles worth pursuing. JobForge verifies the evidence before it drafts.")

    with st.expander("Candidate and sources", expanded=True):
        uploaded_cv = st.file_uploader("CV", type=["pdf", "docx", "txt", "md"])
        use_sample_cv = st.checkbox("Use the sample CV", value=True)
        use_live_search = st.checkbox("Search current listings", value=True)
        sample_fallback = st.checkbox("Fall back to sample jobs", value=True)
        uploaded_jobs = st.file_uploader(
            "Fallback jobs JSON",
            type=["json"],
            help="Optional controlled dataset used only in sample or fallback mode.",
        )

    with st.expander("Role preferences", expanded=True):
        interests = st.text_area(
            "Career interests",
            "machine learning engineering\ndata science\nAI engineering\nsoftware engineering",
            help="One role family or interest per line.",
        )
        locations = st.text_input("Locations", "Sydney, Remote Australia")
        experience_levels = st.multiselect(
            "Experience levels",
            EXPERIENCE_LEVELS,
            default=["internship", "graduate", "entry-level", "junior", "associate"],
        )
        employment_types = st.text_input("Employment types", "Full-time")

    with st.expander("Eligibility and exclusions"):
        max_years = st.number_input("Maximum experience required", min_value=0, max_value=10, value=2)
        posted_within = st.number_input("Maximum listing age (days)", min_value=1, max_value=365, value=30)
        work_rights = st.text_input("Work rights", "Australian unrestricted work rights")
        excluded_companies = st.text_input(
            "Excluded companies",
            "",
            help="Comma-separated exact company names.",
        )
        excluded_keywords = st.text_input(
            "Excluded keywords",
            "",
            help="Reject listings containing any of these comma-separated terms.",
        )

    top_n = st.number_input("Application packages to prepare", min_value=1, max_value=10, value=5)
    run_clicked = st.button("Find matching jobs", type="primary", width="stretch")

    st.divider()
    st.caption(f"Drafting: {'OpenAI · ' + configured_model() if openai_enabled() else 'deterministic mode'}")
    load_sample = st.button("Explore sample results", width="stretch")
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
        excluded_companies=_split_lines(excluded_companies),
        excluded_keywords=_split_lines(excluded_keywords),
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
    st.html(
        """
        <section class="jf-empty">
          <h2>Start with a focused search</h2>
          <p>JobForge turns your CV and constraints into a ranked shortlist, then prepares application drafts backed by evidence from your experience.</p>
          <div class="jf-steps">
            <div class="jf-step"><strong>Set your target</strong><span>Choose role families, locations, and experience levels.</span></div>
            <div class="jf-step"><strong>Validate the fit</strong><span>Reject stale, ineligible, or mismatched listings before ranking.</span></div>
            <div class="jf-step"><strong>Prepare honestly</strong><span>Generate CV and letter drafts without inventing experience.</span></div>
          </div>
        </section>
        """
    )
    action_col, hint_col = st.columns([0.42, 0.58], vertical_alignment="center")
    with action_col:
        explore_sample = st.button("Explore sample results", type="primary", width="stretch")
    with hint_col:
        st.caption("Or open Search setup to run a current search with your own CV.")
    if explore_sample:
        try:
            sample_result = _load_sample_payload()
            if sample_result is None:
                st.error("Sample results are unavailable. Run the sample workflow locally to restore them.")
                st.stop()
            st.session_state["workflow_result"] = sample_result
            st.rerun()
        except Exception as exc:
            st.error(f"Sample results could not be loaded: {exc}")
    st.stop()

metrics = st.columns(3)
metrics[0].metric("Roles discovered", result.discovered_count)
metrics[1].metric("Validated", result.validated_count)
metrics[2].metric("Recommended", result.recommended_count)

source_badges = "".join(
    f'<span class="jf-source">{escape(source.replace("sample-", "sample · "))}</span>'
    for source in result.search_sources
)
st.html(
    f'<div class="jf-mode-strip"><strong>{escape(result.search_mode.replace("_", " ").title())} search</strong>'
    f'<span>Sources</span>{source_badges or "<span>none</span>"}</div>'
)
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
    return value.replace("_", " ").title()


def _source_label(source: str) -> str:
    if source.startswith("sample-"):
        return "Sample data"
    if source.startswith("serpapi:"):
        return source.split(":", 1)[1].replace("-", " ").title()
    provider = source.split(":", 1)[0]
    return provider.replace("-", " ").title()


def _job_card_html(application) -> str:
    job = application.job
    link_label = "Open demo listing" if result.search_mode.startswith("sample") else "Open original listing"
    return f"""
    <article class="jf-card">
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
          <span class="jf-chip">{escape(_source_label(job.source))}</span>
        </div>
      </div>
      <div class="jf-link-row">
        <span class="jf-recommendation">{escape(_recommendation_label(application.recommendation.value))}</span>
        <a class="jf-verify" href="{escape(job.application_url)}" target="_blank" rel="noopener noreferrer" aria-label="{escape(link_label)} for {escape(job.title)}">{escape(link_label)}</a>
      </div>
    </article>
    """


def _list_panel_html(title: str, items: list[str]) -> str:
    rendered_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"""
    <div class="jf-panel">
      <h3>{escape(title)}</h3>
      <ul class="jf-list">{rendered_items}</ul>
    </div>
    """


st.html(
    '<div class="jf-grid">' + "".join(_job_card_html(application) for application in result.applications) + "</div>",
)

job_labels = [f"{app.job.title} - {app.job.company}" for app in result.applications]
if job_labels:
    selected = st.selectbox("Job detail", job_labels)
    application = result.applications[job_labels.index(selected)]

    left, right = st.columns([1.1, 0.9])
    with left:
        detail_link_label = "Open demo listing" if result.search_mode.startswith("sample") else "Open original listing"
        st.html(
            f"""
            <div class="jf-panel">
              <h3>{escape(application.job.title)}</h3>
              <p class="jf-muted">{escape(application.job.company)} · {escape(application.job.location)}</p>
              <p>{escape(application.job_summary)}</p>
              <p class="jf-muted">Source: {escape(_source_label(application.job.source))} · Drafting: {escape(application.generation_source)}</p>
              <a class="jf-verify" href="{escape(application.job.application_url)}" target="_blank" rel="noopener noreferrer">{escape(detail_link_label)}</a>
            </div>
            """,
        )
        match_items = [
            f"{match.requirement}: {match.candidate_evidence}"
            for match in application.matching_evidence
        ]
        st.html(_list_panel_html("Why it matches", match_items))
        gap_items = application.skill_gaps or ["No major listed skill gaps identified."]
        st.html(_list_panel_html("Potential gaps", gap_items))

    with right:
        st.html('<div class="jf-panel"><h3>Score breakdown</h3><p class="jf-muted">How the evidence maps to this role.</p></div>')
        st.metric("Relevance score", f"{application.relevance_score}/100")
        st.bar_chart(application.score_breakdown.components)
        st.html(_list_panel_html("Interview preparation", application.interview_preparation_topics))

    cv_tab, letter_tab, checks_tab = st.tabs(["Tailored CV", "Cover letter", "Quality checks"])
    cv_tab.markdown(application.tailored_cv)
    if application.tailored_cv_latex:
        cv_tab.caption("Generated from validated CV evidence using JobForge's trusted LaTeX template.")
        try:
            with cv_tab.spinner("Compiling verified PDF"):
                cv_pdf, cv_engine, cv_pages = _compile_cv_pdf(
                    application.tailored_cv_latex,
                    result.candidate_profile.candidate_name,
                )
            cv_tab.download_button(
                "Download tailored CV PDF",
                cv_pdf,
                file_name=f"{application.job_id}_tailored_cv.pdf",
                mime="application/pdf",
                type="primary",
            )
            cv_tab.caption(f"Verified {cv_pages}-page PDF · compiled with {cv_engine}")
        except LatexCompileError as exc:
            cv_tab.warning(str(exc))
        cv_tab.download_button(
            "Download LaTeX source",
            application.tailored_cv_latex,
            file_name=f"{application.job_id}_tailored_cv.tex",
            mime="application/x-tex",
        )
    else:
        cv_tab.info("Run a fresh workflow to generate the LaTeX and PDF version of this CV.")
    cv_tab.download_button(
        "Download text draft",
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
    with checks_tab:
        quality = application.quality_checks
        check_items = [
            ("Evidence grounded", quality.evidence_grounded),
            ("Company verified", quality.company_name_correct),
            ("Eligible", quality.job_eligible),
            ("Score explained", quality.score_explained),
        ]
        rendered_checks = "".join(
            f'<div class="jf-check"><strong>{"Passed" if passed else "Needs review"}</strong>{escape(label)}</div>'
            for label, passed in check_items
        )
        st.html(f'<div class="jf-check-grid">{rendered_checks}</div>')
        if quality.issues:
            st.warning(" · ".join(quality.issues))
        with st.expander("Technical validation data"):
            st.json(quality.model_dump())

with st.expander("Workflow diagnostics"):
    st.caption("Operational details for troubleshooting search, validation, and drafting.")
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
    st.dataframe(timeline, width="stretch", hide_index=True)

    st.subheader("Validation checkpoints")
    checks = [
        {
            "Part": check.part,
            "Passed": check.passed,
            "Issues": "; ".join(check.issues) if check.issues else "-",
        }
        for check in result.validation_checks
    ]
    st.dataframe(checks, width="stretch", hide_index=True)
