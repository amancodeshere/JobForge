from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html import escape
from pathlib import Path
from queue import Empty, Queue
import sys
from tempfile import TemporaryDirectory

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.application import WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.tools.experience_levels import EXPERIENCE_LEVELS
from dashboard.access import authenticated_subject, bind_session, local_access_enabled
from dashboard.documents import inspect_cv
from dashboard.results import render_results, _source_label
from dashboard.theme import inject_theme

st.set_page_config(page_title="JobForge · Your next opportunity", layout="wide", initial_sidebar_state="auto")
inject_theme()

LOCAL_MODE = local_access_enabled(os.environ)
subject = authenticated_subject(st.user.to_dict())
bind_session(st.session_state, subject or ("local-owner" if LOCAL_MODE else None))


def auth_ready() -> bool:
    try:
        auth = st.secrets.get("auth", {})
        return all(auth.get(key) for key in (
            "redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url"
        ))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return False


def masthead(label: str) -> None:
    st.html(f'<div class="jf-masthead"><div class="jf-wordmark">JobForge<span class="jf-wordmark-dot">.</span></div><div class="jf-live-mark">{escape(label)}</div></div>')


def landing() -> None:
    masthead("A clearer path to your next role")
    st.html('''<section class="jf-hero jf-landing">
      <div class="jf-language-front"><div class="jf-language-copy"><h1><span>Find your</span><span>next move.</span></h1></div>
      <div class="jf-language-summary"><strong>Your experience.<br>A more focused search.</strong>
      <p>Turn your CV into a shortlist you can actually act on. Find current roles, understand the fit, and prepare an application grounded in what you’ve done.</p></div></div></section>''')
    start, demo, _ = st.columns([1, 1, 1.4])
    start.page_link(workspace_page if subject or LOCAL_MODE else login_page, label="Open my workspace" if subject or LOCAL_MODE else "Get started / sign in", use_container_width=True)
    demo.page_link(demo_page, label="Explore the demo", use_container_width=True)
    st.html('''<section class="jf-empty"><div><h2>Less searching.<br>More direction.</h2><p>One place to move from your CV to your next application.</p></div>
    <div class="jf-steps"><div class="jf-step"><strong>Bring your experience</strong><span>Drop in your CV. Check the readable text before you continue.</span></div>
    <div class="jf-step"><strong>Choose your direction</strong><span>Set the roles, locations and experience levels that matter to you.</span></div>
    <div class="jf-step"><strong>Make your next move</strong><span>Review ranked matches and prepare materials for the role you choose.</span></div></div></section>''')
    st.caption("Live sources and sample results are always labelled. Applications are drafted only when you ask.")


def login() -> None:
    masthead("Your workspace starts here")
    if subject or LOCAL_MODE:
        st.switch_page(workspace_page)
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.html('<section class="jf-login-copy"><h1>A place for<br>your next move.</h1><p>Bring your CV, define your search, and keep your shortlist in focus.</p></section>')
    with right:
        with st.container(border=True):
            st.subheader("Welcome to JobForge")
            st.write("Sign in or create your account with the connected identity provider.")
            if auth_ready():
                if st.button("Continue to secure sign-in", type="primary", width="stretch"):
                    try:
                        st.login()
                    except Exception:
                        st.error("Sign-in could not start. Try again, or ask the app owner to check the identity provider settings.")
                st.caption("Your provider handles your password. JobForge never asks for it.")
            else:
                st.info("Sign-in is waiting for the app owner to connect an identity provider. You can explore the demo now.")
                st.page_link(demo_page, label="Explore demonstration results", use_container_width=True)
            st.caption("Your CV and results stay in this browser session. Refreshing or signing out can clear them; account history is not connected yet.")


def demo() -> None:
    masthead("Demonstration · sample data")
    st.title("See a search come together")
    st.write("Explore a sample candidate’s ranked roles, evidence and prepared application drafts.")
    st.info("These are demonstration results from a fixed dataset, not current vacancies or your personal results.")
    st.page_link(workspace_page if subject or LOCAL_MODE else login_page, label="Start with my own CV", use_container_width=False)
    path = ROOT / "sample_data/expected_outputs/latest_run.json"
    try:
        result = WorkflowResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.error("The demonstration is temporarily unavailable. Please try again later.")
        return
    render_results(result, scope="demo")


def split_values(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def run_search(preferences: CandidatePreferences, limit: int) -> None:
    progress_events: Queue = Queue()
    panel = st.status("Finding roles that fit your brief…", expanded=True)
    preview = st.empty()
    found = []
    try:
        with TemporaryDirectory(prefix="jobforge-") as temp:
            document = st.session_state["cv_document"]
            path = Path(temp) / ("cv" + Path(document["name"]).suffix.lower())
            path.write_bytes(document["content"])
            orchestrator = OrchestratorAgent(
                sample_jobs_path=str(ROOT / "sample_data/jobs/jobs.json"),
                progress_callback=progress_events.put, enable_cache=True,
            )
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashboard-search") as executor:
                future = executor.submit(orchestrator.search, cv_path=str(path), preferences=preferences,
                                         use_live_search=True, sample_fallback=False, limit=limit)
                while not future.done():
                    try:
                        event = progress_events.get(timeout=0.1)
                    except Empty:
                        continue
                    if event.status == "completed":
                        panel.write(f"{_source_label(event.source)} · {event.records_returned} matching roles")
                        found.extend(event.jobs)
                        preview.markdown("\n".join(f"- **{job.title}** — {job.company}" for job in found[:5]))
                    else:
                        panel.write(f"{_source_label(event.source)} is unavailable. Other sources will continue.")
                result = future.result()
        panel.update(label="Your shortlist is ready", state="complete", expanded=False)
        preview.empty()
        st.session_state.update(search_result=result, search_preferences=preferences, generated_applications={}, _next_step="Results")
        st.rerun()
    except Exception:
        panel.update(label="Your search needs attention", state="error", expanded=False)
        st.error("We couldn't complete the search. Your CV and preferences are still here. Try again or check the configured job sources.")


def document_step() -> None:
    st.header("Start with your experience")
    st.write("Drop your CV below. We’ll check that it’s readable before finding roles for you.")
    upload_key = f"cv_upload_{st.session_state.get('_upload_version', 0)}"

    def on_upload() -> None:
        st.session_state.pop("cv_document", None)
        st.session_state.pop("cv_error", None)
        upload = st.session_state.get(upload_key)
        if upload is None:
            return
        content = upload.getvalue()
        try:
            text = inspect_cv(upload.name, content)
            st.session_state["cv_document"] = dict(name=upload.name, content=content, text=text, digest=sha256(content).hexdigest())
        except ValueError as exc:
            st.session_state["cv_error"] = str(exc)

    st.file_uploader("Upload your CV", type=["pdf", "docx", "txt", "md"],
                     help="PDF, DOCX, TXT or Markdown · up to 10 MB · one CV",
                     key=upload_key, on_change=on_upload, max_upload_size=10)
    if st.session_state.get("cv_error"):
        st.error(st.session_state["cv_error"])
    document = st.session_state.get("cv_document")
    if document:
        st.success(f"{document['name']} is ready · {len(document['text'].split()):,} readable words")
        with st.expander("Check extracted CV text"):
            st.text(document["text"][:12000])
        if st.button("Remove CV"):
            st.session_state.pop("cv_document", None)
            st.session_state["_upload_version"] = st.session_state.get("_upload_version", 0) + 1
            st.rerun()
    st.caption("Your document is processed in temporary storage. It is not added to the demo or saved to the repository.")
    if st.button("Continue to preferences", type="primary", disabled=not document):
        st.session_state["_next_step"] = "Preferences"
        st.rerun()


def preference_step() -> None:
    if not st.session_state.get("cv_document"):
        st.info("Upload your CV in the CV step first.")
        return
    st.header("What does your next role look like?")
    st.caption(f"Searching with {st.session_state['cv_document']['name']} · preferences remain editable after a search.")
    with st.form("search_brief"):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            interests = st.text_area("Target roles", placeholder="e.g. Data analyst\nSoftware engineer", key="roles")
            locations = st.text_input("Locations", placeholder="e.g. Sydney, Remote Australia", key="locations")
            levels = st.multiselect("Experience levels", EXPERIENCE_LEVELS, key="levels")
        with col2:
            employment = st.multiselect("Employment types", ["Full-time", "Part-time", "Contract", "Casual", "Internship"], default=["Full-time"], key="employment")
            work_rights = st.text_input("Work rights", placeholder="e.g. Australian unrestricted work rights", key="work_rights")
            count = st.slider("Shortlist size", 5, 25, 10, key="shortlist_size")
        with st.expander("Refine eligibility and exclusions"):
            a, b = st.columns(2)
            years = a.number_input("Maximum experience required (years)", 0, 40, 5, key="years")
            age = b.number_input("Maximum listing age (days)", 1, 365, 30, key="age")
            excluded_companies = st.text_input("Exclude companies", help="Comma-separated exact names", key="excluded_companies")
            excluded_keywords = st.text_input("Exclude keywords", help="Comma-separated terms", key="excluded_keywords")
        submitted = st.form_submit_button("Find matching jobs", type="primary", width="stretch")
    if submitted:
        if not split_values(interests) or not split_values(locations) or not levels or not employment or not work_rights.strip():
            st.error("Add a target role, location, experience level, employment type and work rights to start your search.")
            return
        preferences = CandidatePreferences(target_roles=split_values(interests), career_interests=split_values(interests),
            locations=split_values(locations), experience_level=levels[0], experience_levels=levels,
            employment_types=employment, max_years_experience=int(years), posted_within_days=int(age),
            work_rights=work_rights.strip(), excluded_companies=split_values(excluded_companies),
            excluded_keywords=split_values(excluded_keywords))
        run_search(preferences, count)


def workspace() -> None:
    if not subject and not LOCAL_MODE:
        login()
        return
    name = st.user.get("name", "Your workspace") if subject else "Your local workspace"
    masthead(str(name))
    with st.sidebar:
        st.html('<div class="jf-sidebar-brand"><strong>Your next move</strong><span>From your experience to a focused shortlist.</span></div>')
        st.caption("Signed in" if subject else "Local personal mode · no account")
        document = st.session_state.get("cv_document")
        st.write(document["name"] if document else "No CV added yet")
        st.caption("Session workspace · documents and results are not yet saved between sessions.")
        if subject and st.button("Sign out", width="stretch"):
            st.session_state.clear()
            st.logout()
        if st.button("Clear workspace", width="stretch"):
            st.session_state.clear()
            st.rerun()
    st.title("Your job search")
    if "_next_step" in st.session_state:
        st.session_state["workspace_step"] = st.session_state.pop("_next_step")
    step = st.segmented_control("Search journey", ["CV", "Preferences", "Results"], default="CV", key="workspace_step", selection_mode="single")
    if step == "Preferences":
        preference_step()
    elif step == "Results":
        result = st.session_state.get("search_result")
        if result is None:
            st.header("Your shortlist will appear here")
            st.write("Add your CV and choose your preferences to find current roles. The demo has its own page if you’d like to see an example.")
        else:
            st.caption(f"Results for {result.candidate_profile.candidate_name} · based on your last completed search")
            render_results(result, scope="workspace")
    else:
        document_step()


home_page = st.Page(landing, title="Home", default=True)
demo_page = st.Page(demo, title="Explore demo", url_path="demo")
login_page = st.Page(login, title="Sign in", url_path="login")
workspace_page = st.Page(workspace, title="Workspace", url_path="workspace")
pages = [home_page, demo_page, workspace_page] if subject or LOCAL_MODE else [home_page, demo_page, login_page, workspace_page]
# Keep widgets alive while users navigate the three workspace steps.
for key in ("workspace_step", "roles", "locations", "levels", "employment", "work_rights",
            "shortlist_size", "years", "age", "excluded_companies", "excluded_keywords"):
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]
st.navigation(pages, position="top").run()
