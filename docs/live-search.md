# Live search design

## Provider strategy

JobForge uses structured, documented job endpoints instead of general-purpose browser automation:

| Capability | Provider | Authentication | Role |
| --- | --- | --- | --- |
| Broad Australian search | Adzuna | App ID and key | Searches roles and locations supplied by the candidate |
| Cross-board discovery | SerpApi Google Jobs | API key | Returns structured Google Jobs results with original publisher and apply links |
| Targeted company search | Greenhouse Job Board API | None for public GETs | Reads configured company career boards |
| Targeted company search | Lever Postings API | None for public postings | Reads configured company career sites |
| Optional remote search | Remotive public API | None | Adds attributed remote listings for low-volume deployments |

Every adapter converts external data into `JobResult`. Independent providers and company boards run concurrently, while output ordering remains deterministic. Provider failures are isolated and exposed in `search_warnings` and agent health. Live results are never silently mixed with samples. If every live source returns no records, the optional fallback is labelled `sample_fallback`.

## Agent Reach boundary

Agent Reach is installed for interactive research across web pages, LinkedIn, GitHub, social platforms, video, and feeds. It is a capability router, not a structured production job provider. Its runtime invokes external command-line tools and some capabilities require browser cookies, proxies, or Exa credentials. Embedding it in the Railway request path would make retrieval less deterministic and expand the service's credential and execution surface.

JobForge therefore gives its deployed search agents narrow native tools with typed outputs. Agent Reach can be used outside the deployed request path to discover new company-board tokens and research sources, but application-ready records still require normalization and validation.

SerpApi's Google Jobs adapter is the breadth layer. It can surface listings published through LinkedIn, Indeed, SEEK, Glassdoor, ZipRecruiter, Workday, direct employer sites, and many other sources indexed by Google Jobs. Coverage depends on what Google Jobs indexes for the query and location, so the UI reports observed publishers instead of claiming universal coverage.

## Configuration

```text
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=au
SERPAPI_API_KEY=
SERPAPI_COUNTRY=au
SERPAPI_LANGUAGE=en
JOBFORGE_GREENHOUSE_BOARDS=Canonical=canonical,Culture Amp=cultureamp
JOBFORGE_LEVER_SITES=Deputy=deputy
JOBFORGE_ENABLE_REMOTIVE=false
JOBFORGE_SEARCH_TIMEOUT=12
JOBFORGE_RESULTS_PER_SOURCE=50
JOBFORGE_MAX_SEARCH_QUERIES=4
JOBFORGE_SEARCH_WORKERS=6
```

Company boards use comma-separated `Company name=token` entries. Setting a board variable to an empty value disables that provider. If `JOBFORGE_GREENHOUSE_BOARDS` is absent, JobForge uses Canonical's public board as a zero-key live source.

Remotive is disabled by default. Its public API requires attribution and advises no more than four requests per day, which is unsuitable for an uncached multi-user deployment. If it is enabled for a low-volume instance, JobForge preserves the Remotive listing URL and displays Remotive as the source.

## Safety and quality boundaries

- Job fields are untrusted external data.
- Only HTTP(S) application URLs can reach recommendations.
- Location, employment type, freshness, seniority, experience years, and detected citizenship restrictions are validated before ranking.
- Skills inferred from an unstructured provider description are treated as preferred signals, not invented hard requirements.
- Provider descriptions sent to an LLM are bounded to 12,000 characters and explicitly identified as untrusted data.
- JobForge creates drafts and links to the original listing. It does not submit applications or automate authenticated job boards.

## Adding a provider

1. Add an adapter to `LiveJobSearch`.
2. Use an official API or explicitly permitted public feed.
3. Normalize stable IDs, original application URLs, source attribution, location, dates, employment type, and plain-text descriptions.
4. Raise `LiveSearchError` for recoverable source failures.
5. Add mocked normalization, malformed-response, deduplication, and failure-isolation tests.
6. Verify a live smoke run without committing its output.

Provider documentation:

- [Adzuna API](https://developer.adzuna.com/)
- [SerpApi Google Jobs API](https://serpapi.com/google-jobs-api)
- [Greenhouse Job Board API](https://developer.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Remotive public API](https://github.com/remotive-io/remote-jobs-api)
- [Agent Reach](https://github.com/Panniantong/Agent-Reach)
