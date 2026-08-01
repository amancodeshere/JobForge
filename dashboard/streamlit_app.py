from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.application import WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.tools.llm_client import configured_model, openai_enabled


DEFAULT_OUTPUT = ROOT / "sample_data/expected_outputs/latest_run.json"
DEFAULT_CV = ROOT / "sample_data/cvs/aman_sharma_cv.txt"
DEFAULT_JOBS = ROOT / "sample_data/jobs/jobs.json"
DEV_MODE = os.getenv("JOBFORGE_DEV_MODE", "false").lower() in {"1", "true", "yes"}


st.set_page_config(page_title="JobForge", layout="wide")
st.title("JobForge")

with st.sidebar:
    st.subheader("Run")
    uploaded_cv = st.file_uploader("CV", type=["pdf", "docx", "txt", "md"])
    uploaded_jobs = st.file_uploader("Jobs JSON", type=["json"])
    use_sample_cv = st.checkbox("Use sample CV", value=True)
    interests = st.text_area(
        "Career interests",
        "machine learning engineering\ndata science\nAI engineering\nsoftware engineering",
    )
    locations = st.text_input("Locations", "Sydney, Remote Australia")
    experience_level = st.selectbox("Experience level", ["graduate", "internship", "junior"], index=0)
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
    return CandidatePreferences(
        target_roles=[
            interest.replace("engineering", "engineer")
            for interest in career_interests
        ],
        career_interests=career_interests,
        locations=_split_lines(locations),
        experience_level=experience_level,
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

st.subheader("Recommended jobs")
rows = [
    {
        "Job": application.job.title,
        "Company": application.job.company,
        "Score": application.relevance_score,
        "Recommendation": application.recommendation.value.replace("_", " "),
        "Location": application.job.location,
        "Generated by": application.generation_source,
    }
    for application in result.applications
]
st.dataframe(rows, use_container_width=True, hide_index=True)

job_labels = [f"{app.job.title} - {app.job.company}" for app in result.applications]
if job_labels:
    selected = st.selectbox("Job detail", job_labels)
    application = result.applications[job_labels.index(selected)]

    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader(application.job.title)
        st.caption(application.job.company)
        st.metric("Relevance score", f"{application.relevance_score}/100")
        st.caption(f"Application copy: {application.generation_source}")
        st.write(application.job_summary)
        st.markdown("**Why it matches**")
        for match in application.matching_evidence:
            st.write(f"- {match.requirement}: {match.candidate_evidence}")
        st.markdown("**Potential gaps**")
        if application.skill_gaps:
            for gap in application.skill_gaps:
                st.write(f"- {gap}")
        else:
            st.write("- No major listed skill gaps identified.")
        st.link_button("Open application", application.job.application_url)

    with right:
        st.subheader("Score breakdown")
        st.bar_chart(application.score_breakdown.components)
        st.markdown("**Interview preparation**")
        for topic in application.interview_preparation_topics:
            st.write(f"- {topic}")

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
