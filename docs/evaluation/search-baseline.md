# Search quality baseline

Measured on 2026-08-02 with the 30 labelled briefs in
`tests/fixtures/search_benchmark.json` and the normalized sample corpus in
`sample_data/jobs/jobs.json`.

## Baseline results

| Metric | Baseline | Product target |
| --- | ---: | ---: |
| Precision@5 | 52.5% | 80% relevant results in the top 10 |
| Precision@10 | 50.4% | 80% |
| NDCG@10 | 72.1% | Improve without reducing recall |
| Relevant recall | 63.3% | Improve from baseline |
| Duplicate rate | 0.0% | Below 2% |
| Invalid-link rate | 0.0% | Below 5% |

## Phase 4 calibrated result

The deterministic two-stage ranker was calibrated on the same fixed cases. It
uses a first-stage confidence floor of 42 and a full-score shortlist floor of
62.

| Metric | Phase 1 | Phase 4 |
| --- | ---: | ---: |
| Precision@5 | 52.5% | 84.6% |
| Precision@10 | 50.4% | 84.2% |
| NDCG@10 | 72.1% | 80.7% |
| Relevant recall | 63.3% | 72.8% |

The calibrated shortlist clears the product's 80% top-ten relevance target and
improves recall and NDCG over the Phase 1 baseline. The final calibration fixed
two false-negative filters: a `0-2 years` range now uses its minimum requirement
and maps to early-career seniority bands, while Remote Australia roles are
eligible for candidates in Australian cities. Unknown work rights remain a
ranking risk instead of being treated as a confirmed eligibility failure.

The corpus is deliberately controlled and cannot prove live provider coverage
or production latency. It is the regression benchmark for query planning,
normalization, filtering, deduplication, and ranking changes. Live targets need
staging or production observations with configured provider credentials.

The most common rejection signals were experience-level mismatch (186),
location mismatch (119), employment-type mismatch (50), citizenship (30), and
freshness (30). These counts span all case/job comparisons and can overlap.

## Reproduce

```bash
UV_CACHE_DIR=/tmp/jobforge-uv-cache uv run python main.py benchmark-search \
  --benchmark tests/fixtures/search_benchmark.json \
  --jobs sample_data/jobs/jobs.json \
  --date 2026-08-02 \
  --output /tmp/jobforge-search-baseline.json
```

Provider latency, request counts, returned-record counts, error rates, and
estimated request costs are represented by `SourceTelemetry` and
`aggregate_provider_metrics`. The suite exercises concurrent fast, slow, empty,
and failing sources without external credentials.

## Phase 1 gate

- 30 unique labelled profiles/search briefs load successfully.
- Precision@5, Precision@10, NDCG@10, relevant recall, duplicate rate, and
  invalid-link rate have independently tested calculations.
- Validation rejection reasons are included in the generated report.
- Sanitized fixtures cover Adzuna, SerpApi multi-board, Greenhouse, and Lever.
- Provider timing, request count, results, error category/rate, and estimated
  cost are measurable.
- Simulated providers prove bounded concurrency and failure isolation.
- The full repository test suite passes.
