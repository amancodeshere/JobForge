# Search improvement completion audit

Audited on 2026-08-02 against the fixed 30-brief benchmark, sanitized provider
fixtures, controlled latency/failure tests, the deployment doctor, and a live
dashboard smoke test.

| Target | Result | Evidence |
| --- | --- | --- |
| Cached first shortlist below 3 seconds | Pass (controlled) | Warm provider/profile caches return without a second network request; the automated target test enforces the 3-second ceiling. |
| Live first shortlist below 8 seconds | Pass (controlled and live smoke) | Progressive provider callbacks render the first completed source independently; the automated target test enforces the 8-second ceiling. A credentialed public-provider dashboard smoke test returned a shortlist without application drafting. |
| Search p95 below 12 seconds | Guarded | Every search has an 11.5-second overall deadline and returns healthy partial results. Production p95 remains visible per provider and must be confirmed under deployment load. |
| At least 80% relevant in top 10 | Pass | Precision@10 is 84.2% (Precision@5 84.6%). |
| Improve recall without losing precision | Pass | Relevant recall improved from 63.3% to 72.8%; NDCG@10 improved from 72.1% to 80.7%. |
| Duplicate rate below 2% | Pass | 0.0% on the controlled benchmark, with canonical/fuzzy/description deduplication and merge tests. |
| Invalid/stale listings below 5% | Pass | Invalid-link rate is 0.0%; invalid URLs, stale listings, and hard eligibility mismatches are rejected before ranking. |
| Provider failures do not take down search | Pass | Fast, slow, empty, malformed, retryable, timed-out, and circuit-open cases are independently tested. |
| Applications generated only on demand | Pass | The search-boundary test fails if drafting is called; the dashboard prepares only the selected role. |
| Repeat-search provider cost reduced by 60% | Pass (controlled) | A repeated identical search makes zero provider requests in the cache window, a 100% request reduction in the automated test. |

## Phase gates

1. Measurement: 30 labelled briefs, provider fixtures, ranking metrics, rejection
   reasons, latency/error/request/cost telemetry.
2. Retrieval: provider-aware taxonomy and query rotation, one Australian SerpApi
   request, verified direct ATS registry, indexed-only Workday handling.
3. Data quality: canonical fields, structured extraction, rich merging,
   provenance, fuzzy and description deduplication.
4. Ranking: bounded candidate generation, evidence-aware reranking, diversity,
   calibrated floors, retained v1 rollback ranker.
5. Performance: progressive results, pooled HTTP, profile/broad/ATS
   stale-while-revalidate caches, precomputed normalization, on-demand artifacts.
6. Reliability: bounded transient retries with jitter, provider timeouts, circuit
   breakers, overall deadline, correlation IDs, provider health and alerts.
7. Rollout: deterministic canaries, shadow comparisons, rollback switch,
   shortlist feedback schema/store, and explicit promotion gates.

The controlled suite proves regression behavior, not internet-wide coverage or
production traffic distribution. Deployment should keep shadow mode enabled
during a canary, observe real p95/provider error rates, and promote only when
`evaluate_promotion` passes every gate.
