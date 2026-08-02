# Live search design

## Provider strategy

JobForge uses structured, documented job endpoints instead of general-purpose browser automation:

| Capability | Provider | Authentication | Role |
| --- | --- | --- | --- |
| Broad Australian search | Adzuna | App ID and key | Searches roles and locations supplied by the candidate |
| Australian multi-board discovery | SerpApi Google Search | API key | Uses one request to discover direct listings across credible Australian boards and ATS sites |
| Cross-board discovery outside Australia | SerpApi Google Jobs | API key | Returns structured results where the Google Jobs country is supported |
| Targeted company search | Greenhouse Job Board API | None for public GETs | Reads configured company career boards |
| Targeted company search | Lever Postings API | None for public postings | Reads verified company career sites |
| Targeted company search | Ashby public job posting API | None for public board GETs | Reads verified company career sites |
| Targeted indexed search | Workday career sites | SerpApi key | Uses allowlisted public listing URLs; no private Workday API is assumed |
| Optional remote search | Remotive public API | None | Adds attributed remote listings for low-volume deployments |

Every adapter converts external data into `JobResult`. Independent providers and company boards run concurrently, while output ordering remains deterministic. Provider failures are isolated and exposed in `search_warnings` and agent health. Live results are never silently mixed with samples. If every live source returns no records, the optional fallback is labelled `sample_fallback`.

Agent diagnostics include correlation IDs and per-provider latency, request/retry counts, records received and rejected, duplicate removal, top-ten contribution, cache status, circuit state, and estimated request-cost units. Transient network, quota, HTTP 429, and HTTP 5xx failures receive bounded jittered retries. Malformed data and other permanent failures are not retried. A circuit breaker isolates repeatedly failing providers, ATS APIs use shorter request timeouts, and the overall deadline returns partial results rather than making every healthy provider wait for the slowest one.

Candidate profiling overlaps network-bound broad search. Source completions stream progressively to the UI, broad/profile/ATS inventories use bounded stale-while-revalidate caches, and application artifacts are generated only when the user selects a shortlisted role.

## Agent Reach boundary

Agent Reach is installed for interactive research across web pages, LinkedIn, GitHub, social platforms, video, and feeds. It is a capability router, not a structured production job provider. Its runtime invokes external command-line tools and some capabilities require browser cookies, proxies, or Exa credentials. Embedding it in the Railway request path would make retrieval less deterministic and expand the service's credential and execution surface.

JobForge therefore gives its deployed search agents narrow native tools with typed outputs. Agent Reach can be used outside the deployed request path to discover new company-board tokens and research sources, but application-ready records still require normalization and validation.

For `SERPAPI_COUNTRY=au`, JobForge uses SerpApi's regular Google Search engine with `google.com.au`. A provider-aware query planner expands requested roles into weighted exact, alias, seniority, and skill-led variants. Exact intent and the core Australian boards remain in every request; secondary variants and non-core ATS scopes rotate by a stable time bucket. The query is limited to results indexed during the last month. One live workflow therefore spends at most one SerpApi search even when several roles and sites are involved.

The maintained registry at `config/ats_boards.json` records provider, token or indexed scope, access mode, verification date, verification URL, and expected locations. Greenhouse, Lever, and Ashby entries use their documented public job-board APIs. Workday entries are explicitly `indexed_only`; JobForge does not treat authenticated Workday platform APIs or undocumented career-site internals as a general public job-search API.

The allowlist covers SEEK, Indeed, LinkedIn, Glassdoor, Workforce Australia, APS Jobs, I Work for NSW, Careers Victoria, Queensland Smart Jobs, EthicalJobs, Jora, and direct listings hosted by Greenhouse, Lever, Workday, Ashby, SmartRecruiters, and Workable. Results must match a source-specific direct-listing path. Search pages, unknown hosts, host-suffix spoofing, and malformed URLs are discarded before job validation and ranking.

The adapter uses only the title, snippet, date, and link returned by SerpApi. It never requests the matched board page from JobForge's backend. This is indexed discovery rather than first-party coverage: source freshness, distribution, and recall remain dependent on Google's index and ranking.

JobForge deliberately does not scrape job boards. SEEK's published terms prohibit data mining, robots, and screen scraping without prior written approval, while its approved developer API is designed around recruitment-software job posting and application workflows rather than unrestricted candidate job search. An academic use case does not remove those restrictions. The long-term first-party route is to request written approval or appropriate partnerships; the indexed provider keeps the current deployment functional without an anti-bot bypass.

For non-Australian countries, the existing SerpApi Google Jobs adapter remains available and preserves the observed publisher and application link. The configured country must appear in SerpApi's current Google Jobs country list.

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
JOBFORGE_ASHBY_BOARDS=Airtasker=airtasker
JOBFORGE_ENABLE_REMOTIVE=false
JOBFORGE_SEARCH_TIMEOUT=12
JOBFORGE_SEARCH_DEADLINE=11.5
JOBFORGE_SEARCH_RETRY_ATTEMPTS=3
JOBFORGE_CIRCUIT_FAILURES=3
JOBFORGE_CIRCUIT_COOLDOWN=60
JOBFORGE_RESULTS_PER_SOURCE=50
JOBFORGE_MAX_SEARCH_QUERIES=4
JOBFORGE_SEARCH_WORKERS=6
JOBFORGE_QUERY_ROTATION_MINUTES=60
JOBFORGE_BROAD_CACHE_TTL=1800
JOBFORGE_BROAD_CACHE_STALE=3600
JOBFORGE_ATS_CACHE_TTL=21600
JOBFORGE_ATS_CACHE_STALE=43200
JOBFORGE_RANKER_V2=true
JOBFORGE_RANKER_SHADOW=false
JOBFORGE_RANKER_ROLLOUT_PERCENT=100
```

Company boards use comma-separated `Company name=token` entries. Setting a board variable to an empty value disables that provider. When an override is absent, JobForge uses the enabled entries in the verified registry. Explicit environment configuration always wins.

For Australian SerpApi searches, `JOBFORGE_MAX_SEARCH_QUERIES` is the maximum number of role phrases placed in the single multi-board query. Increasing it does not increase the number of SerpApi requests per workflow. SerpApi caching remains enabled; its documentation states that identical cached searches within one hour are free and do not count toward the monthly allowance.

Remotive is disabled by default. Its public API requires attribution and advises no more than four requests per day, which is unsuitable for an uncached multi-user deployment. If it is enabled for a low-volume instance, JobForge preserves the Remotive listing URL and displays Remotive as the source.

## Ranking rollout and feedback

`JOBFORGE_RANKER_V2` is the immediate rollback switch. `JOBFORGE_RANKER_ROLLOUT_PERCENT` assigns searches deterministically to the control or candidate ranker, so a candidate remains in the same canary bucket for equivalent preferences. `JOBFORGE_RANKER_SHADOW` computes both rankings while returning only the assigned ranking; diagnostics report top-ten overlap and average movement, and shadow output never changes what the user sees.

The shortlist captures relevant, irrelevant, and hide-company signals with the search correlation ID, rank, job ID, and ranker version in a bounded process-local store. A production database can replace this store without changing the feedback schema. Promotion requires precision@10 of at least 80%, duplicate rate below 2%, invalid-link rate below 5%, p95 below 12 seconds, and provider error rate below 10%; failing any gate blocks promotion and supports an immediate rollback to v1.

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
- [SerpApi Google Search API](https://serpapi.com/search-api)
- [SerpApi Google Jobs API](https://serpapi.com/google-jobs-api)
- [SerpApi Google Jobs countries](https://serpapi.com/google-jobs-countries)
- [SEEK developer API](https://developer.seek.com/)
- [SEEK advertising terms](https://www.seek.com.au/content/terms/new-advertising-terms-seek-au.pdf)
- [Greenhouse Job Board API](https://developer.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Ashby public job posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Remotive public API](https://github.com/remotive-io/remote-jobs-api)
- [Agent Reach](https://github.com/Panniantong/Agent-Reach)
