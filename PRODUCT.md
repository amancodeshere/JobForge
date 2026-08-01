# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

JobForge serves Australian job seekers across every career stage, from graduates and early-career applicants through experienced professionals and executives. They use it to reduce the time and uncertainty involved in finding credible roles and preparing truthful, targeted applications.

## Product Purpose

JobForge turns a candidate CV and explicit preferences into a current, validated and ranked job shortlist, then prepares evidence-grounded application materials. Success means users can move from a broad search to a confident application package without losing sight of listing provenance, eligibility or the evidence behind each recommendation.

## Positioning

JobForge combines live multi-source discovery, deterministic validation and ranking, and evidence-constrained application drafting in one traceable workflow. It does not present generated claims as candidate experience or hide whether results came from live providers, fallbacks or sample data.

## Operating Context

Users upload a PDF, DOCX or text CV; set role, location, seniority, employment and eligibility preferences; run a live or sample-backed search; review ranked roles and score evidence; open the original listing; and download a tailored CV PDF, LaTeX source and cover letter. The deployed product runs as a Streamlit application on Railway and must remain effective on desktop and mobile web.

## Capabilities and Constraints

- Live search combines SerpApi, Adzuna and configured public ATS boards while reporting the exact search mode and attempted sources.
- Australian indexed discovery is designed to use one SerpApi request per workflow because the free plan is limited to 250 searches per month.
- Search coverage cannot guarantee every listing on every job board and must not imply private or partner-only API access.
- Candidate uploads and generated workflow output remain in temporary storage and session state rather than being committed to the repository.
- Drafting may use OpenAI or a deterministic fallback; validation remains deterministic.
- Application documents are evidence-grounded, and trusted LaTeX is compiled and verified before PDF download.
- The interface must preserve access to original listings, source provenance, quality checks and operational diagnostics.

## Brand Commitments

The product name is JobForge. Its voice is formal, clear, composed and credible without becoming cold or exclusive. It must welcome professionals at every career level and avoid hype, gamification and unsupported claims. There are no existing logo or colour constraints.

## Evidence on Hand

The repository contains a controlled sample CV, job dataset and expected workflow output for demonstration and testing. It contains no customer logos, testimonials, commercial benchmarks or other third-party proof, so the interface must not fabricate them.

## Product Principles

1. Show where every recommendation came from.
2. Prefer defensible evidence over persuasive invention.
3. Make complex search and application work feel orderly and easy to navigate.
4. Serve every career level without making the experience feel generic.
5. Keep expensive or limited provider usage visible and efficient.

## Accessibility & Inclusion

The web interface targets WCAG 2.2 AA, including keyboard-visible controls, sufficient contrast, reduced-motion support, clear status language, usable touch targets and responsive layouts.
