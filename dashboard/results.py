from __future__ import annotations
from html import escape
import streamlit as st
from app.agents.application_tailor_agent import ApplicationTailorAgent
from app.schemas.application import JobSearchResult
from app.services.latex_resume import LatexCompileError, compile_resume_pdf
from app.tools.relevance_scoring import recommendation_for
from app.tools.rollout import FEEDBACK_STORE, SearchFeedback


def _source_label(source: str) -> str:
    if source.startswith("sample-"):
        return "Sample data"
    if source.startswith("serpapi:"):
        return source.split(":", 1)[1].replace("-", " ").title()
    return source.split(":", 1)[0].replace("-", " ").title()


@st.cache_data(show_spinner=False, max_entries=20)
def _compile_cv_pdf(latex_source: str, candidate_name: str) -> tuple[bytes, str, int]:
    compiled = compile_resume_pdf(latex_source, expected_name=candidate_name)
    return compiled.pdf_bytes, compiled.engine, compiled.page_count


def render_results(result, *, scope: str) -> None:
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


    filter_col, sort_col = st.columns([2, 1])
    query = filter_col.text_input("Filter your shortlist", placeholder="Role, company or location", key=f"{scope}-filter")
    order = sort_col.selectbox("Sort by", ["Best match", "Company A–Z", "Role A–Z"], key=f"{scope}-sort")
    if query.strip():
        display_entries = [entry for entry in display_entries if query.casefold().strip() in
                           f"{entry[0].title} {entry[0].company} {entry[0].location}".casefold()]
    if order == "Company A–Z":
        display_entries.sort(key=lambda entry: entry[0].company.casefold())
    elif order == "Role A–Z":
        display_entries.sort(key=lambda entry: entry[0].title.casefold())
    if not display_entries:
        st.info("No roles match this filter. Clear it to see your full shortlist.")

    st.html(
        '<div class="jf-grid">'
        + "".join(_job_card_html(job, score, application) for job, score, application in display_entries)
        + "</div>",
    )

    job_labels = [f"{job.title} - {job.company}" for job, _score, _application in display_entries]
    if job_labels:
        selected_index = st.selectbox("Review an opportunity", range(len(job_labels)), format_func=lambda index: job_labels[index], key=f"{scope}-selected")
        job, score_breakdown, application = display_entries[selected_index]

        if is_search_result:
            original_rank = next(index for index, ranked in enumerate(result.ranked_jobs, 1) if ranked.job.job_id == job.job_id)
            st.caption(f"Evidence rank {original_rank} · {result.ranker_version} · showing {len(display_entries)} of {len(result.ranked_jobs)} roles")
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
                        rank=original_rank,
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
            if score_breakdown.components:
                st.bar_chart(score_breakdown.components)
            else:
                st.caption("This sample includes an overall score only; component scores appear with a new search.")
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
            pdf_key = f"{scope}-pdf-ready-{application.job_id}"
            if application.tailored_cv_latex and cv_tab.button("Create downloadable PDF", key=f"{scope}-pdf-{application.job_id}"):
                st.session_state[pdf_key] = True
            if application.tailored_cv_latex and st.session_state.get(pdf_key):
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
            if application.tailored_cv_latex:
                cv_tab.download_button(
                    "Download LaTeX source",
                    application.tailored_cv_latex,
                    file_name=f"{application.job_id}_tailored_cv.tex",
                    mime="application/x-tex",
                )
            elif not application.tailored_cv_latex:
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
