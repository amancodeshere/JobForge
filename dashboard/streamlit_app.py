from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
import sys
from tempfile import TemporaryDirectory
from html import escape

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.schemas.application import JobSearchResult, WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.services.latex_resume import LatexCompileError, compile_resume_pdf
from app.tools.experience_levels import EXPERIENCE_LEVELS
from app.tools.llm_client import configured_model, openai_enabled
from app.tools.relevance_scoring import recommendation_for
from app.tools.rollout import FEEDBACK_STORE, SearchFeedback
from dashboard.theme import inject_theme


DEFAULT_OUTPUT = ROOT / "sample_data/expected_outputs/latest_run.json"
DEFAULT_CV = ROOT / "sample_data/cvs/aman_sharma_cv.txt"
DEFAULT_JOBS = ROOT / "sample_data/jobs/jobs.json"
DEV_MODE = os.getenv("JOBFORGE_DEV_MODE", "false").lower() in {"1", "true", "yes"}


st.set_page_config(page_title="JobForge", layout="wide")


@st.cache_data(show_spinner=False, max_entries=20)
def _compile_cv_pdf(latex_source: str, candidate_name: str) -> tuple[bytes, str, int]:
    compiled = compile_resume_pdf(latex_source, expected_name=candidate_name)
    return compiled.pdf_bytes, compiled.engine, compiled.page_count



st.html(
    """
    <!--
    THESIS: Career language becomes evidence; this surface refuses the generic recruitment card dashboard.
    OWN-WORLD: Mineral-white workspace, deep-slate search dossier, condensed role typography, strict rules, and eucalyptus evidence signals.
    STORY: Define a search, see broad intent resolve into verified opportunities, inspect the case, and prepare an honest application.
    FIRST VIEWPORT: A 31% search rail anchors a monumental language front; the primary search action remains fixed within the rail.
    FORM: Opportunity Front, approved composition A, seed e11640c4.
    FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
    -->
    <span class="jf-direction-contract" aria-hidden="true"></span>
    """
)
inject_theme()
st.markdown(
    """
    <section class="jf-hero">
      <div class="jf-masthead">
        <div class="jf-wordmark">JobForge</div>
        <div class="jf-live-mark">Live search · evidence grounded</div>
      </div>
      <div class="jf-language-front">
        <div class="jf-language-copy">
          <h1 aria-label="Forge a career">
            <span>Forge a</span><span>career</span>
          </h1>
        </div>
        <div class="jf-language-summary">
          <strong>Find stronger opportunities. Apply with evidence.</strong>
          <p>JobForge searches live, credible job sources, ranks each role against your CV and preferences, and prepares tailored application materials without inventing experience.</p>
        </div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.html(
        """
        <div class="jf-sidebar-brand">
          <strong>Search brief</strong>
          <span>Define the opportunity. JobForge verifies the evidence before it drafts.</span>
        </div>
        """
    )

    with st.expander("Candidate profile", expanded=True):
        uploaded_cv = st.file_uploader("CV or résumé", type=["pdf", "docx", "txt", "md"])
        use_sample_cv = st.checkbox("Use the sample CV", value=True)

    with st.expander("Opportunity focus", expanded=True):
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
        max_years = st.number_input(
            "Maximum experience required",
            min_value=0,
            max_value=40,
            value=2,
            help="Set up to 40 years for executive searches.",
        )
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

    st.divider()
    st.caption(f"Drafting: {'OpenAI · ' + configured_model() if openai_enabled() else 'deterministic mode'}")
    load_sample = st.button("Open demonstration results", width="stretch")
    if DEV_MODE:
        payload_path = st.text_input("Load saved payload", str(DEFAULT_OUTPUT))
    else:
        payload_path = str(DEFAULT_OUTPUT)

    with st.container(key="search_action_tray"):
        top_n = st.number_input(
            "Shortlist size",
            min_value=5,
            max_value=25,
            value=10,
            help="Application materials are prepared later, one selected role at a time.",
        )
        run_clicked = st.button("Run live opportunity search", type="primary", width="stretch")


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


def _source_label(source: str) -> str:
    if source.startswith("sample-"):
        return "Sample data"
    if source.startswith("serpapi:"):
        return source.split(":", 1)[1].replace("-", " ").title()
    provider = source.split(":", 1)[0]
    return provider.replace("-", " ").title()


if run_clicked:
    if uploaded_cv is None and not use_sample_cv:
        st.error("Add a CV or enable the sample profile before starting the search.")
        st.stop()
    preferences = _preferences_from_form()
    progress_events: Queue = Queue()
    progressive_jobs = []
    progress_panel = st.status("Searching current sources…", expanded=True)
    preview = st.empty()
    try:
        with TemporaryDirectory(prefix="jobforge-") as temp:
            temp_dir = Path(temp)
            cv_path = _path_from_upload(uploaded_cv, temp_dir, DEFAULT_CV)
            orchestrator = OrchestratorAgent(
                sample_jobs_path=str(DEFAULT_JOBS),
                progress_callback=progress_events.put,
                enable_cache=True,
            )
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashboard-search") as executor:
                future = executor.submit(
                    orchestrator.search,
                    cv_path=cv_path,
                    preferences=preferences,
                    use_live_search=True,
                    sample_fallback=False,
                    limit=int(top_n),
                )
                while not future.done():
                    try:
                        event = progress_events.get(timeout=0.1)
                    except Empty:
                        continue
                    if event.status == "completed":
                        progress_panel.write(
                            f"{_source_label(event.source)} returned {event.records_returned} matching roles "
                            f"in {event.duration_ms} ms."
                        )
                        progressive_jobs.extend(event.jobs)
                        visible = progressive_jobs[:8]
                        preview.markdown(
                            "\n".join(f"- **{job.title}** — {job.company}" for job in visible)
                        )
                    else:
                        progress_panel.write(f"{_source_label(event.source)} could not complete: {event.message}")
                result = future.result()
        progress_panel.update(label="Search complete", state="complete", expanded=False)
        preview.empty()
        st.session_state["search_result"] = result
        st.session_state["search_preferences"] = preferences
        st.session_state["generated_applications"] = {}
        st.session_state.pop("workflow_result", None)
    except Exception as exc:
        progress_panel.update(label="Search needs attention", state="error", expanded=True)
        st.error(f"The search could not be completed. Review the search brief and try again. Technical detail: {exc}")
        st.stop()
    st.success("Your ranked shortlist is ready. Prepare application materials only for the role you choose.")
elif load_sample:
    try:
        result = _load_sample_payload()
        if result is None:
            st.error("Sample payload is missing. Run `uv run python main.py run` locally and commit the result.")
            st.stop()
        st.session_state["workflow_result"] = result
        st.session_state.pop("search_result", None)
    except Exception as exc:
        st.error(f"Could not load sample payload: {exc}")
        st.stop()
elif "search_result" in st.session_state:
    result = st.session_state["search_result"]
elif "workflow_result" in st.session_state:
    result = st.session_state["workflow_result"]
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
          <div>
            <h2>Build your search case</h2>
            <p>JobForge turns your CV and constraints into a ranked shortlist, then prepares application drafts backed by evidence from your experience.</p>
          </div>
          <div class="jf-steps">
            <div class="jf-step"><strong>Define the opportunity</strong><span>Set role families, locations, seniority and eligibility.</span></div>
            <div class="jf-step"><strong>Test the evidence</strong><span>Remove stale, ineligible and mismatched listings before ranking.</span></div>
            <div class="jf-step"><strong>Prepare with integrity</strong><span>Create CV and letter drafts without inventing experience.</span></div>
          </div>
        </section>
        """
    )
    action_col, hint_col = st.columns([0.42, 0.58], vertical_alignment="center")
    with action_col:
        explore_sample = st.button("Review demonstration results", type="primary", width="stretch")
    with hint_col:
        st.caption("Or open the Search brief to run a current search with your own CV.")
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

is_search_result = isinstance(result, JobSearchResult)
if st.session_state.pop("application_ready_notice", None):
    st.success("Application materials are ready for review.")
if is_search_result:
    generated_applications = st.session_state.setdefault("generated_applications", {})
    display_entries = [
        (ranked.job, ranked.score_breakdown, generated_applications.get(ranked.job.job_id))
        for ranked in result.ranked_jobs
    ]
else:
    display_entries = [
        (application.job, application.score_breakdown, application)
        for application in result.applications
    ]

metrics = st.columns(3)
metrics[0].metric("Roles discovered", result.discovered_count)
metrics[1].metric("Validated", result.validated_count)
metrics[2].metric("Shortlisted", len(display_entries))

source_badges = "".join(
    f'<span class="jf-source">{escape(_source_label(source))}</span>'
    for source in result.search_sources
)
st.html(
    f'<div class="jf-mode-strip"><strong>{escape(result.search_mode.replace("_", " ").title())} search</strong>'
    f'<span>Sources</span>{source_badges or "<span>none</span>"}</div>'
)
if not display_entries:
    st.warning("No roles cleared the relevance threshold. Broaden the role, location, or experience settings and run the search again.")
for warning in result.search_warnings:
    st.warning(warning)

st.markdown(
    """
    <div class="jf-section-title">
      <h2>Opportunity shortlist</h2>
      <span class="jf-muted">Ranked by transparent, deterministic evidence scoring</span>
    </div>
    """,
    unsafe_allow_html=True,
)


def _recommendation_label(value: str) -> str:
    return value.replace("_", " ").title()


def _provenance_label(job) -> str:
    sources = job.source_provenance or [job.source]
    if len(sources) == 1:
        return _source_label(sources[0])
    return f"Seen on {len(sources)} sources"


def _provenance_detail(job) -> str:
    sources = job.source_provenance or [job.source]
    return ", ".join(_source_label(source) for source in sources)


def _job_card_html(job, score_breakdown, application) -> str:
    link_label = "Open demo listing" if result.search_mode.startswith("sample") else "Open original listing"
    recommendation = recommendation_for(score_breakdown.overall_score)
    preparation_state = "Application ready" if application else "Ready to prepare"
    return f"""
    <article class="jf-card">
      <div>
        <div class="jf-card-top">
          <div>
            <div class="jf-job-title">{escape(job.title)}</div>
            <div class="jf-company">{escape(job.company)}</div>
          </div>
          <div class="jf-score">{score_breakdown.overall_score}<span>score</span></div>
        </div>
        <div class="jf-meta">
          <span class="jf-chip">{escape(job.location)}</span>
          <span class="jf-chip">{escape(job.employment_type)}</span>
          <span class="jf-chip">{escape(job.experience_required)}</span>
          <span class="jf-chip">{escape(_provenance_label(job))}</span>
        </div>
      </div>
      <div class="jf-link-row">
        <span class="jf-recommendation">{escape(_recommendation_label(recommendation.value))} · {escape(preparation_state)}</span>
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
    '<div class="jf-grid">'
    + "".join(_job_card_html(job, score, application) for job, score, application in display_entries)
    + "</div>",
)

job_labels = [f"{job.title} - {job.company}" for job, _score, _application in display_entries]
if job_labels:
    selected = st.selectbox("Review an opportunity", job_labels)
    selected_index = job_labels.index(selected)
    job, score_breakdown, application = display_entries[selected_index]

    if is_search_result:
        st.caption(f"Ranked by {result.ranker_version} · result {selected_index + 1} of {len(display_entries)}")
        feedback_columns = st.columns(3)
        for column, label, signal in [
            (feedback_columns[0], "Good match", "relevant"),
            (feedback_columns[1], "Not relevant", "irrelevant"),
            (feedback_columns[2], "Hide company", "hide_company"),
        ]:
            if column.button(label, key=f"feedback-{signal}-{job.job_id}", use_container_width=True):
                FEEDBACK_STORE.add(SearchFeedback(
                    correlation_id=(result.correlation_ids or ["local"])[0],
                    job_id=job.job_id,
                    signal=signal,
                    ranker=result.ranker_version,
                    rank=selected_index + 1,
                ))
                st.toast("Feedback recorded for ranking evaluation.")

    left, right = st.columns([1.1, 0.9])
    with left:
        detail_link_label = "Open demo listing" if result.search_mode.startswith("sample") else "Open original listing"
        summary = application.job_summary if application else job.description
        drafting_state = application.generation_source if application else "not prepared"
        st.html(
            f"""
            <div class="jf-panel">
              <h3>{escape(job.title)}</h3>
              <p class="jf-muted">{escape(job.company)} · {escape(job.location)}</p>
              <p>{escape(summary[:1800])}</p>
              <p class="jf-muted">Sources: {escape(_provenance_detail(job))} · Drafting: {escape(drafting_state)}</p>
              <a class="jf-verify" href="{escape(job.application_url)}" target="_blank" rel="noopener noreferrer">{escape(detail_link_label)}</a>
            </div>
            """,
        )
        if application:
            match_items = [
                f"{match.requirement}: {match.candidate_evidence}"
                for match in application.matching_evidence
            ]
            st.html(_list_panel_html("Matching evidence", match_items))
            gap_items = application.skill_gaps or ["No major listed skill gaps identified."]
            st.html(_list_panel_html("Potential gaps", gap_items))
        else:
            structured_facts = [
                f"Working arrangement: {job.work_arrangement}",
                f"Experience: {job.experience_required}",
                f"Skills observed: {', '.join(job.required_skills or job.inferred_skills) or 'not specified'}",
            ]
            if job.compensation_text:
                structured_facts.append(f"Compensation: {job.compensation_text}")
            st.html(_list_panel_html("Listing facts", structured_facts))

    with right:
        st.html('<div class="jf-panel"><h3>Evidence score</h3><p class="jf-muted">How your verified experience maps to this opportunity.</p></div>')
        st.metric("Relevance score", f"{score_breakdown.overall_score}/100")
        st.bar_chart(score_breakdown.components)
        if application:
            st.html(_list_panel_html("Interview preparation", application.interview_preparation_topics))

    if application is None and is_search_result:
        st.info("Application materials have not been generated. Your shortlist remains available without spending drafting time or model usage.")
        if st.button("Prepare application for this role", type="primary", key=f"prepare-{job.job_id}"):
            preferences = st.session_state.get("search_preferences")
            if preferences is None:
                st.error("The search brief is no longer available. Run the search again before preparing an application.")
            else:
                with st.spinner("Preparing an evidence-grounded CV and cover letter…"):
                    application = ApplicationTailorAgent().run(
                        result.candidate_profile,
                        preferences,
                        job,
                        today=result.validation_date,
                        precomputed_score=score_breakdown,
                    )
                st.session_state["generated_applications"][job.job_id] = application
                st.session_state["application_ready_notice"] = job.job_id
                st.rerun()

    if application:
        cv_tab, letter_tab, checks_tab = st.tabs(["Tailored CV & PDF", "Cover letter", "Evidence checks"])
        cv_tab.markdown(application.tailored_cv)
        if application.tailored_cv_latex:
            cv_tab.caption("Generated from validated CV evidence using JobForge's trusted LaTeX template.")
            try:
                with cv_tab:
                    with st.spinner("Compiling verified PDF"):
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
            cv_tab.info("This application does not include a LaTeX CV source.")
        cv_tab.download_button(
            "Download text draft",
            application.tailored_cv,
            file_name=f"{application.job_id}_tailored_cv.md",
            mime="text/markdown",
        )
        letter_tab.markdown(application.cover_letter)
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

with st.expander("Search provenance & diagnostics"):
    st.caption("Operational evidence for search, validation and ranking. Drafting appears only after a role is prepared.")
    st.subheader("Agent activity")
    timeline = [
        {
            "Agent": health.agent,
            "Status": health.status,
            "Tool calls": health.tool_calls,
            "Valid": health.valid_results,
            "Invalid": health.invalid_results,
            "Errors": health.execution_errors,
            "Duration (ms)": health.duration_ms,
            "Notes": "; ".join(health.notes) if health.notes else "-",
        }
        for health in result.agent_health
    ]
    st.dataframe(timeline, width="stretch", hide_index=True)

    provider_health = getattr(result, "provider_health", [])
    if provider_health:
        st.subheader("Provider health")
        st.dataframe(
            [
                {
                    "Provider": item.source,
                    "Status": item.status,
                    "Latency (ms)": item.duration_ms,
                    "Requests": item.requests,
                    "Retries": item.retries,
                    "Received": item.records_received,
                    "Rejected": item.records_rejected,
                    "Top 10": item.top_ten_contribution,
                    "Cache": item.cache_status,
                    "Circuit": item.circuit_state,
                    "Cost units": item.estimated_cost_units,
                }
                for item in provider_health
            ],
            width="stretch",
            hide_index=True,
        )
        for alert in getattr(result, "search_alerts", []):
            st.warning(alert)
        correlation_ids = getattr(result, "correlation_ids", [])
        if correlation_ids:
            st.caption(f"Search correlation: {' · '.join(correlation_ids)}")
        if getattr(result, "shadow_comparison", {}):
            comparison = result.shadow_comparison
            st.caption(
                "Shadow ranking (not shown to users): "
                f"{comparison.get('top_ten_overlap', 0):.0%} top-ten overlap · "
                f"{comparison.get('average_displacement', 0):.1f} average position movement"
            )

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

st.html(
    """
    <footer class="jf-footer">
      JobForge keeps listing provenance visible and constrains application drafts to evidence from the supplied CV. Uploaded files are processed in temporary session storage.
    </footer>
    """
)
