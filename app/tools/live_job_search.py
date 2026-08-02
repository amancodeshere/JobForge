from __future__ import annotations

import html
import hashlib
import json
import os
import re
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.schemas.job import JobResult
from app.tools.ats_registry import default_public_boards, indexed_workday_scopes
from app.tools.cache import TTLCache
from app.tools.job_normalization import normalize_job
from app.tools.query_planner import plan_for_preferences, plan_for_profile, role_matches
from app.tools.resilience import CircuitBreakerRegistry, RetryPolicy, retry_call


USER_AGENT = "JobForge/0.2 (+https://github.com/)"
_BROAD_SEARCH_CACHE: TTLCache[list[JobResult]] = TTLCache(max_entries=256)
_ATS_BOARD_CACHE: TTLCache[list[JobResult]] = TTLCache(max_entries=128)
_HTTP_CLIENT = httpx.Client(
    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    limits=httpx.Limits(max_connections=24, max_keepalive_connections=12),
    follow_redirects=True,
)
LOGGER = logging.getLogger("jobforge.search")


class LiveSearchError(RuntimeError):
    """A recoverable failure from an external job source."""


@dataclass(frozen=True)
class CompanyBoard:
    company: str
    token: str


@dataclass(frozen=True)
class IndexedJobSite:
    source: str
    domains: tuple[str, ...]
    path_pattern: str
    search_scope: str
    id_query_parameter: str = ""


INDEXED_JOB_SITES = (
    IndexedJobSite("seek", ("seek.com.au", "au.seek.com"), r"/job/\d+", "seek.com.au/job/"),
    IndexedJobSite("indeed", ("indeed.com",), r"/viewjob$", "au.indeed.com/viewjob", "jk"),
    IndexedJobSite("linkedin", ("linkedin.com",), r"/jobs/view/", "linkedin.com/jobs/view"),
    IndexedJobSite(
        "glassdoor",
        ("glassdoor.com.au", "glassdoor.com"),
        r"/job-listing/",
        "glassdoor.com.au/job-listing/",
        "jl",
    ),
    IndexedJobSite(
        "workforce-australia",
        ("workforceaustralia.gov.au",),
        r"/individuals/jobs/details/",
        "workforceaustralia.gov.au/individuals/jobs/details/",
    ),
    IndexedJobSite("aps-jobs", ("apsjobs.gov.au",), r"/s/job-details", "apsjobs.gov.au/s/job-details"),
    IndexedJobSite("i-work-for-nsw", ("iworkfor.nsw.gov.au",), r"/job/", "iworkfor.nsw.gov.au/job/"),
    IndexedJobSite("careers-victoria", ("careers.vic.gov.au",), r"/jobs/", "careers.vic.gov.au/jobs/"),
    IndexedJobSite("smart-jobs-qld", ("smartjobs.qld.gov.au",), r"/jobs/", "smartjobs.qld.gov.au/jobs/"),
    IndexedJobSite("ethical-jobs", ("ethicaljobs.com.au",), r"/members/", "ethicaljobs.com.au/members/"),
    IndexedJobSite("jora", ("jora.com",), r"/job/", "au.jora.com/job/"),
    IndexedJobSite("greenhouse", ("greenhouse.io",), r"/jobs/", "job-boards.greenhouse.io"),
    IndexedJobSite("lever", ("jobs.lever.co",), r"/[^/]+/[^/]+", "jobs.lever.co"),
    IndexedJobSite("workday", ("myworkdayjobs.com",), r"/job/", "myworkdayjobs.com"),
    IndexedJobSite("ashby", ("jobs.ashbyhq.com",), r"/[^/]+/[^/]+", "jobs.ashbyhq.com"),
    IndexedJobSite("smartrecruiters", ("jobs.smartrecruiters.com",), r"/[^/]+/", "jobs.smartrecruiters.com"),
    IndexedJobSite("workable", ("apply.workable.com",), r"/[^/]+/j/", "apply.workable.com"),
)


@dataclass(frozen=True)
class LiveSearchConfig:
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "au"
    enable_remotive: bool = False
    serpapi_api_key: str = ""
    serpapi_country: str = "au"
    serpapi_language: str = "en"
    greenhouse_boards: tuple[CompanyBoard, ...] = ()
    lever_sites: tuple[CompanyBoard, ...] = ()
    ashby_boards: tuple[CompanyBoard, ...] = ()
    request_timeout: float = 12.0
    results_per_source: int = 50
    max_search_queries: int = 4
    max_workers: int = 6
    query_rotation_minutes: int = 60
    broad_cache_ttl_seconds: int = 1800
    broad_cache_stale_seconds: int = 3600
    ats_cache_ttl_seconds: int = 21600
    ats_cache_stale_seconds: int = 43200
    overall_deadline_seconds: float = 11.5
    retry_attempts: int = 3
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "LiveSearchConfig":
        return cls(
            adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
            adzuna_app_key=os.getenv("ADZUNA_APP_KEY", "").strip(),
            adzuna_country=os.getenv("ADZUNA_COUNTRY", "au").strip().lower() or "au",
            enable_remotive=_env_flag("JOBFORGE_ENABLE_REMOTIVE", False),
            serpapi_api_key=os.getenv("SERPAPI_API_KEY", "").strip(),
            serpapi_country=os.getenv("SERPAPI_COUNTRY", "au").strip().lower() or "au",
            serpapi_language=os.getenv("SERPAPI_LANGUAGE", "en").strip().lower() or "en",
            greenhouse_boards=tuple(
                _parse_company_boards(os.environ["JOBFORGE_GREENHOUSE_BOARDS"])
                if "JOBFORGE_GREENHOUSE_BOARDS" in os.environ
                else _registry_boards("greenhouse")
            ),
            lever_sites=tuple(
                _parse_company_boards(os.environ["JOBFORGE_LEVER_SITES"])
                if "JOBFORGE_LEVER_SITES" in os.environ
                else _registry_boards("lever")
            ),
            ashby_boards=tuple(
                _parse_company_boards(os.environ["JOBFORGE_ASHBY_BOARDS"])
                if "JOBFORGE_ASHBY_BOARDS" in os.environ
                else _registry_boards("ashby")
            ),
            request_timeout=_env_float("JOBFORGE_SEARCH_TIMEOUT", 12.0, minimum=1.0, maximum=30.0),
            results_per_source=_env_int("JOBFORGE_RESULTS_PER_SOURCE", 50, minimum=1, maximum=100),
            max_search_queries=_env_int("JOBFORGE_MAX_SEARCH_QUERIES", 4, minimum=1, maximum=8),
            max_workers=_env_int("JOBFORGE_SEARCH_WORKERS", 6, minimum=1, maximum=12),
            query_rotation_minutes=_env_int("JOBFORGE_QUERY_ROTATION_MINUTES", 60, minimum=15, maximum=1440),
            broad_cache_ttl_seconds=_env_int("JOBFORGE_BROAD_CACHE_TTL", 1800, minimum=60, maximum=3600),
            broad_cache_stale_seconds=_env_int("JOBFORGE_BROAD_CACHE_STALE", 3600, minimum=0, maximum=21600),
            ats_cache_ttl_seconds=_env_int("JOBFORGE_ATS_CACHE_TTL", 21600, minimum=900, maximum=86400),
            ats_cache_stale_seconds=_env_int("JOBFORGE_ATS_CACHE_STALE", 43200, minimum=0, maximum=172800),
            overall_deadline_seconds=_env_float("JOBFORGE_SEARCH_DEADLINE", 11.5, minimum=2.0, maximum=30.0),
            retry_attempts=_env_int("JOBFORGE_SEARCH_RETRY_ATTEMPTS", 3, minimum=1, maximum=5),
            circuit_failure_threshold=_env_int("JOBFORGE_CIRCUIT_FAILURES", 3, minimum=1, maximum=10),
            circuit_cooldown_seconds=_env_float("JOBFORGE_CIRCUIT_COOLDOWN", 60.0, minimum=1.0, maximum=900.0),
        )


@dataclass
class SearchOutcome:
    jobs: list[JobResult] = field(default_factory=list)
    sources_attempted: list[str] = field(default_factory=list)
    source_errors: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    source_telemetry: dict[str, "SourceTelemetry"] = field(default_factory=dict)
    correlation_id: str = ""
    deadline_exceeded: bool = False


@dataclass(frozen=True)
class SourceTelemetry:
    """Measured provider behavior for one search operation."""

    source: str
    duration_ms: int = 0
    request_count: int = 0
    records_returned: int = 0
    error_count: int = 0
    error_category: str = ""
    cache_status: str = "miss"
    cache_hits: int = 0
    retry_count: int = 0
    circuit_state: str = "closed"
    estimated_cost_units: float = 0.0


@dataclass(frozen=True)
class SearchProgressEvent:
    source: str
    status: str
    records_returned: int
    duration_ms: int
    jobs: tuple[JobResult, ...] = ()
    message: str = ""


JsonFetcher = Callable[[str, float], Any]
ProgressCallback = Callable[[SearchProgressEvent], None]


class LiveJobSearch:
    """Fetch and normalize jobs from live, documented job endpoints."""

    def __init__(
        self,
        config: LiveSearchConfig | None = None,
        fetch_json: JsonFetcher | None = None,
        progress_callback: ProgressCallback | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or LiveSearchConfig.from_env()
        self.fetch_json = fetch_json or _request_json
        self._broad_cache = _BROAD_SEARCH_CACHE if fetch_json is None else TTLCache(max_entries=64)
        self._ats_cache = _ATS_BOARD_CACHE if fetch_json is None else TTLCache(max_entries=64)
        self.progress_callback = progress_callback
        self._sleeper = sleeper
        self._circuits = CircuitBreakerRegistry(
            failure_threshold=self.config.circuit_failure_threshold,
            cooldown_seconds=self.config.circuit_cooldown_seconds,
        )
        self._request_counts: dict[str, int] = {}
        self._retry_counts: dict[str, int] = {}
        self._cache_statuses: dict[str, str] = {}
        self._request_counts_lock = Lock()

    def broad_search(self, preferences: CandidatePreferences) -> SearchOutcome:
        rotation_bucket = self._rotation_bucket()
        plan = plan_for_preferences(preferences, rotation_bucket=rotation_bucket)
        operations: list[tuple[str, Callable[[], list[JobResult]]]] = []
        if self.config.adzuna_app_id and self.config.adzuna_app_key:
            queries = plan.for_provider("adzuna", self.config.max_search_queries)
            operations.append(("adzuna", lambda: self._cached_broad("adzuna", preferences, queries, lambda: self._search_adzuna(preferences, queries))))
        if self.config.enable_remotive:
            queries = plan.for_provider("remotive", min(3, self.config.max_search_queries))
            operations.append(("remotive", lambda: self._cached_broad("remotive", preferences, queries, lambda: self._search_remotive(preferences, queries))))
        if self.config.serpapi_api_key:
            if self.config.serpapi_country == "au":
                queries = plan.for_provider("serpapi-multiboard", self.config.max_search_queries)
                operations.append(
                    ("serpapi-multiboard", lambda: self._cached_broad("serpapi-multiboard", preferences, queries, lambda: self._search_serpapi_multiboard(preferences, queries, rotation_bucket)))
                )
            else:
                queries = plan.for_provider("serpapi-google-jobs", self.config.max_search_queries)
                operations.append(("serpapi-google-jobs", lambda: self._cached_broad("serpapi-google-jobs", preferences, queries, lambda: self._search_serpapi_jobs(preferences, queries))))
        return self._run_sources(operations)

    def targeted_search(self, profile: CandidateProfile) -> SearchOutcome:
        operations: list[tuple[str, Callable[[], list[JobResult]]]] = []
        for board in self.config.greenhouse_boards:
            source = f"greenhouse:{board.token}"
            operations.append((source, lambda board=board: self._search_greenhouse(board, profile)))
        for board in self.config.lever_sites:
            source = f"lever:{board.token}"
            operations.append((source, lambda board=board: self._search_lever(board, profile)))
        for board in self.config.ashby_boards:
            source = f"ashby:{board.token}"
            operations.append((source, lambda board=board: self._search_ashby(board, profile)))
        return self._run_sources(operations)

    def _rotation_bucket(self) -> int:
        seconds = self.config.query_rotation_minutes * 60
        return int(datetime.now(timezone.utc).timestamp() // seconds)

    def _run_sources(
        self,
        operations: list[tuple[str, Callable[[], list[JobResult]]]],
    ) -> SearchOutcome:
        outcome = SearchOutcome(
            sources_attempted=[source for source, _ in operations],
            correlation_id=uuid.uuid4().hex[:16],
        )
        if not operations:
            return outcome
        results: dict[str, list[JobResult]] = {}
        durations: dict[str, int] = {}
        errors: dict[str, str] = {}
        with self._request_counts_lock:
            self._request_counts = {source: 0 for source, _ in operations}
            self._retry_counts = {source: 0 for source, _ in operations}
            self._cache_statuses = {source: "miss" for source, _ in operations}
        workers = min(self.config.max_workers, len(operations))
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job-source")
        futures = {executor.submit(_timed_source, operation): source for source, operation in operations}
        completed: set[object] = set()
        try:
            for future in as_completed(futures, timeout=self.config.overall_deadline_seconds):
                completed.add(future)
                source = futures[future]
                try:
                    results[source], durations[source] = future.result()
                    self._emit_progress(
                        SearchProgressEvent(
                            source=source,
                            status="completed",
                            records_returned=len(results[source]),
                            duration_ms=durations[source],
                            jobs=tuple(results[source][:10]),
                        )
                    )
                except LiveSearchError as exc:
                    errors[source] = str(exc)
                    durations[source] = int(getattr(exc, "duration_ms", 0))
                    self._emit_progress(
                        SearchProgressEvent(
                            source=source,
                            status="failed",
                            records_returned=0,
                            duration_ms=durations[source],
                            message=str(exc),
                        )
                    )
        except TimeoutError:
            outcome.deadline_exceeded = True
            for future, source in futures.items():
                if future not in completed:
                    future.cancel()
                    errors[source] = f"overall deadline exceeded ({self.config.overall_deadline_seconds:g}s)"
                    durations[source] = round(self.config.overall_deadline_seconds * 1000)
                    self._emit_progress(SearchProgressEvent(source=source, status="timed_out", records_returned=0, duration_ms=durations[source], message=errors[source]))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        for source, _ in operations:
            jobs = results.get(source, [])
            outcome.jobs.extend(jobs)
            outcome.source_counts[source] = len(jobs)
            if source in errors:
                outcome.source_errors.append(f"{source}: {errors[source]}")
            with self._request_counts_lock:
                request_count = self._request_counts.get(source, 0)
                cache_status = self._cache_statuses.get(source, "miss")
                retry_count = self._retry_counts.get(source, 0)
            outcome.source_telemetry[source] = SourceTelemetry(
                source=source,
                duration_ms=durations.get(source, 0),
                request_count=request_count,
                records_returned=len(jobs),
                error_count=1 if source in errors else 0,
                error_category=_error_category(errors.get(source, "")),
                cache_status=cache_status,
                cache_hits=1 if cache_status in {"fresh", "stale"} else 0,
                retry_count=retry_count,
                circuit_state=self._circuits.state(source),
                estimated_cost_units=float(request_count),
            )
        outcome.jobs = _unique_jobs(outcome.jobs)
        LOGGER.info(json.dumps({
            "event": "search.complete",
            "correlation_id": outcome.correlation_id,
            "sources": outcome.sources_attempted,
            "records": len(outcome.jobs),
            "errors": len(outcome.source_errors),
            "deadline_exceeded": outcome.deadline_exceeded,
        }, sort_keys=True))
        return outcome

    def _fetch(self, source: str, url: str) -> Any:
        if not self._circuits.allow(source):
            raise LiveSearchError("circuit open; provider temporarily isolated")

        def operation() -> Any:
            with self._request_counts_lock:
                self._request_counts[source] = self._request_counts.get(source, 0) + 1
            return self.fetch_json(url, self._provider_timeout(source))

        policy = RetryPolicy(max_attempts=self.config.retry_attempts)
        kwargs = {"sleeper": self._sleeper} if self._sleeper else {}
        try:
            payload, retry_count = retry_call(operation, policy, _is_retryable_error, **kwargs)
            with self._request_counts_lock:
                self._retry_counts[source] = self._retry_counts.get(source, 0) + retry_count
            self._circuits.record_success(source)
            return payload
        except Exception as exc:
            with self._request_counts_lock:
                self._retry_counts[source] = self._retry_counts.get(source, 0) + int(getattr(exc, "retry_count", 0))
            self._circuits.record_failure(source)
            if isinstance(exc, LiveSearchError):
                raise
            raise LiveSearchError(f"network error: {exc}") from exc

    def _provider_timeout(self, source: str) -> float:
        # Search indexes are allowed the full timeout; predictable ATS JSON APIs
        # fail faster so a single board cannot consume the whole search budget.
        if source.startswith(("greenhouse:", "lever:", "ashby:")):
            return min(self.config.request_timeout, 6.0)
        return self.config.request_timeout

    def _cached_broad(
        self,
        source: str,
        preferences: CandidatePreferences,
        queries: list[str],
        loader: Callable[[], list[JobResult]],
    ) -> list[JobResult]:
        cache_key = _stable_cache_key(
            source,
            {
                "queries": queries,
                "locations": preferences.locations,
                "levels": preferences.selected_experience_levels(),
                "employment_types": preferences.employment_types,
                "rotation_bucket": self._rotation_bucket(),
            },
        )
        result = self._broad_cache.get_or_load(
            cache_key,
            loader,
            ttl_seconds=self.config.broad_cache_ttl_seconds,
            stale_seconds=self.config.broad_cache_stale_seconds,
        )
        with self._request_counts_lock:
            self._cache_statuses[source] = result.status
        return result.value

    def _cached_ats_inventory(
        self,
        source: str,
        loader: Callable[[], list[JobResult]],
    ) -> list[JobResult]:
        result = self._ats_cache.get_or_load(
            source,
            loader,
            ttl_seconds=self.config.ats_cache_ttl_seconds,
            stale_seconds=self.config.ats_cache_stale_seconds,
        )
        with self._request_counts_lock:
            self._cache_statuses[source] = result.status
        return result.value

    def _emit_progress(self, event: SearchProgressEvent) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(event)
        except Exception:
            # Presentation callbacks must never make a provider search fail.
            return

    def _search_adzuna(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
    ) -> list[JobResult]:
        jobs: list[JobResult] = []
        locations = preferences.locations or [""]
        for query in queries[: self.config.max_search_queries]:
            params = {
                "app_id": self.config.adzuna_app_id,
                "app_key": self.config.adzuna_app_key,
                "results_per_page": min(self.config.results_per_source, 50),
                "what": query,
                "where": locations[0],
                "sort_by": "date",
                "content-type": "application/json",
            }
            url = f"https://api.adzuna.com/v1/api/jobs/{self.config.adzuna_country}/search/1?{urlencode(params)}"
            payload = self._fetch("adzuna", url)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            for item in payload.get("results", []):
                job = _adzuna_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return _unique_jobs(jobs)

    def _search_serpapi_multiboard(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
        rotation_bucket: int,
    ) -> list[JobResult]:
        """Discover credible Australian job listings with one SerpApi search.

        Combining roles, locations, and sites into one exact query preserves the
        free-plan quota. JobForge consumes only Google's structured result fields;
        it never fetches or parses pages from the indexed job boards.
        """
        location = (preferences.locations or ["Australia"])[0]
        search_query = _multiboard_query(
            queries[: self.config.max_search_queries],
            preferences.locations,
            rotation_bucket=rotation_bucket,
        )
        params = {
            "engine": "google",
            "q": search_query,
            "location": location,
            "google_domain": "google.com.au",
            "gl": "au",
            "hl": self.config.serpapi_language,
            "num": min(self.config.results_per_source, 100),
            "tbs": "qdr:m",
            "api_key": self.config.serpapi_api_key,
        }
        payload = self._fetch("serpapi-multiboard", f"https://serpapi.com/search.json?{urlencode(params)}")
        if not isinstance(payload, dict):
            raise LiveSearchError("unexpected response shape")
        if payload.get("error"):
            raise LiveSearchError(_clean(payload["error"]))
        jobs = []
        for item in payload.get("organic_results", []):
            job = _serpapi_indexed_job(item, fallback_location=location)
            if job and _is_relevant_to_preferences(job, preferences):
                jobs.append(job)
        return _unique_jobs(jobs)[: self.config.results_per_source]

    def _search_serpapi_jobs(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
    ) -> list[JobResult]:
        jobs: list[JobResult] = []
        location = (preferences.locations or [""])[0]
        for query in queries[: self.config.max_search_queries]:
            params = {
                "engine": "google_jobs",
                "q": query,
                "location": location,
                "gl": self.config.serpapi_country,
                "hl": self.config.serpapi_language,
                "api_key": self.config.serpapi_api_key,
            }
            payload = self._fetch("serpapi-google-jobs", f"https://serpapi.com/search.json?{urlencode(params)}")
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            if payload.get("error"):
                raise LiveSearchError(_clean(payload["error"]))
            for item in payload.get("jobs_results", []):
                job = _serpapi_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return _unique_jobs(jobs)[: self.config.results_per_source]

    def _search_remotive(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
    ) -> list[JobResult]:
        jobs: list[JobResult] = []
        for query in queries[:3]:
            url = f"https://remotive.com/api/remote-jobs?{urlencode({'search': query, 'limit': self.config.results_per_source})}"
            payload = self._fetch("remotive", url)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            for item in payload.get("jobs", []):
                job = _remotive_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return _unique_jobs(jobs)

    def _search_greenhouse(self, board: CompanyBoard, profile: CandidateProfile) -> list[JobResult]:
        source = f"greenhouse:{board.token}"

        def load() -> list[JobResult]:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board.token}/jobs?content=true"
            payload = self._fetch(source, url)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            return [job for item in payload.get("jobs", []) if (job := _greenhouse_job(item, board))]

        jobs = self._cached_ats_inventory(source, load)
        return [job for job in jobs if job and _is_relevant_to_profile(job, profile)][: self.config.results_per_source]

    def _search_lever(self, board: CompanyBoard, profile: CandidateProfile) -> list[JobResult]:
        source = f"lever:{board.token}"

        def load() -> list[JobResult]:
            url = f"https://api.lever.co/v0/postings/{board.token}?mode=json&limit={self.config.results_per_source}"
            payload = self._fetch(source, url)
            if not isinstance(payload, list):
                raise LiveSearchError("unexpected response shape")
            return [job for item in payload if (job := _lever_job(item, board))]

        jobs = self._cached_ats_inventory(source, load)
        return [job for job in jobs if job and _is_relevant_to_profile(job, profile)][: self.config.results_per_source]

    def _search_ashby(
        self,
        board: CompanyBoard,
        profile: CandidateProfile,
    ) -> list[JobResult]:
        source = f"ashby:{board.token}"

        def load() -> list[JobResult]:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board.token}"
            payload = self._fetch(source, url)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            return [job for item in payload.get("jobs", []) if (job := _ashby_job(item, board))]

        jobs = self._cached_ats_inventory(source, load)
        return [job for job in jobs if job and _is_relevant_to_profile(job, profile)][: self.config.results_per_source]


def _request_json(url: str, timeout: float) -> Any:
    try:
        response = _HTTP_CLIENT.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise LiveSearchError(f"HTTP {exc.response.status_code}") from exc
    except httpx.TimeoutException as exc:
        raise LiveSearchError("network error: timeout") from exc
    except httpx.RequestError as exc:
        raise LiveSearchError(f"network error: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LiveSearchError("invalid JSON response") from exc


def _adzuna_job(item: Any) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    created = _date_only(item.get("created"))
    return _build_job(
        job_id=f"adzuna-{item.get('id', '')}",
        title=item.get("title"),
        company=_nested_text(item, "company", "display_name") or "Unknown company",
        location=_nested_text(item, "location", "display_name") or "Unspecified",
        employment_type=_employment_type(item.get("contract_time") or item.get("contract_type")),
        description=item.get("description"),
        source="adzuna",
        application_url=item.get("redirect_url"),
        date_posted=created,
    )


def _remotive_job(item: Any) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    return _build_job(
        job_id=f"remotive-{item.get('id', '')}",
        title=item.get("title"),
        company=item.get("company_name") or "Unknown company",
        location=item.get("candidate_required_location") or "Remote",
        employment_type=_employment_type(item.get("job_type")),
        description=_plain_text(item.get("description")),
        source="remotive",
        application_url=item.get("url"),
        date_posted=_date_only(item.get("publication_date")),
        preferred_skills=item.get("tags") if isinstance(item.get("tags"), list) else [],
    )


def _serpapi_job(item: Any) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    publisher = _clean(item.get("via")) or "Google Jobs"
    application_url = _serpapi_application_url(item, publisher)
    raw_id = _clean(item.get("job_id")) or "|".join(
        [_clean(item.get("title")), _clean(item.get("company_name")), _clean(item.get("location"))]
    )
    stable_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:20]
    extensions = item.get("detected_extensions")
    detected = extensions if isinstance(extensions, dict) else {}
    return _build_job(
        job_id=f"serpapi-{stable_id}",
        title=item.get("title"),
        company=item.get("company_name") or "Unknown company",
        location=item.get("location") or ("Remote" if detected.get("work_from_home") else "Unspecified"),
        employment_type=_employment_type(detected.get("schedule_type")),
        description=item.get("description"),
        source=f"serpapi:{_source_slug(publisher)}",
        application_url=application_url,
        date_posted=_relative_date(detected.get("posted_at")),
    )


def _serpapi_indexed_job(item: Any, fallback_location: str) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    application_url = _clean(item.get("link"))
    match = _indexed_job_match(application_url)
    if not match:
        return None
    source, stable_id = match
    title, company = _indexed_title_and_company(item.get("title"), source)
    description = item.get("snippet") or item.get("title")
    relative_date = item.get("date") or _nested_text(item, "rich_snippet", "date")
    return _build_job(
        job_id=f"{source}-{stable_id}",
        title=title,
        company=item.get("company_name") or company or f"{source.replace('-', ' ').title()} listing",
        location=item.get("location") or fallback_location or "Australia",
        employment_type=_employment_type(description),
        description=description,
        source=source,
        application_url=application_url,
        date_posted=_relative_date(relative_date),
    )


def _greenhouse_job(item: Any, board: CompanyBoard) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    return _build_job(
        job_id=f"greenhouse-{board.token}-{item.get('id', '')}",
        title=item.get("title"),
        company=board.company,
        location=_nested_text(item, "location", "name") or "Unspecified",
        employment_type="Full-time",
        description=_plain_text(item.get("content")),
        source=f"greenhouse:{board.token}",
        application_url=item.get("absolute_url"),
        date_posted=_date_only(item.get("first_published") or item.get("updated_at")),
    )


def _lever_job(item: Any, board: CompanyBoard) -> JobResult | None:
    if not isinstance(item, dict):
        return None
    categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
    lists = item.get("lists") if isinstance(item.get("lists"), list) else []
    list_text = " ".join(_plain_text(part.get("content")) for part in lists if isinstance(part, dict))
    description = " ".join(
        value for value in [_plain_text(item.get("descriptionPlain")), list_text, _plain_text(item.get("additionalPlain"))] if value
    )
    return _build_job(
        job_id=f"lever-{board.token}-{item.get('id', '')}",
        title=item.get("text"),
        company=board.company,
        location=categories.get("location") or "Unspecified",
        employment_type=_employment_type(categories.get("commitment")),
        description=description,
        source=f"lever:{board.token}",
        application_url=item.get("hostedUrl") or item.get("applyUrl"),
        date_posted=_milliseconds_date(item.get("createdAt")),
    )


def _ashby_job(item: Any, board: CompanyBoard) -> JobResult | None:
    if not isinstance(item, dict) or item.get("isListed") is False:
        return None
    identifier = _clean(item.get("id"))
    if not identifier:
        return None
    return _build_job(
        job_id=f"ashby-{board.token}-{identifier}",
        title=item.get("title"),
        company=board.company,
        location=item.get("location"),
        employment_type=_employment_type(item.get("employmentType")),
        description=item.get("descriptionPlain") or _plain_text(item.get("descriptionHtml")),
        source=f"ashby:{board.token}",
        application_url=item.get("jobUrl") or item.get("applyUrl"),
        date_posted=_date_only(item.get("publishedAt")),
    )


def _build_job(
    *,
    job_id: str,
    title: Any,
    company: Any,
    location: Any,
    employment_type: str,
    description: Any,
    source: str,
    application_url: Any,
    date_posted: str | None,
    preferred_skills: Iterable[str] = (),
) -> JobResult | None:
    title_text = _clean(title)
    url_text = _clean(application_url)
    description_text = _clean(description)
    if not title_text or not url_text or not description_text:
        return None
    today = date.today().isoformat()
    return normalize_job(JobResult(
        job_id=job_id,
        title=title_text,
        company=_clean(company) or "Unknown company",
        location=_clean(location) or "Unspecified",
        employment_type=employment_type,
        description=description_text,
        source=source,
        application_url=url_text,
        date_found=today,
        date_posted=date_posted,
        preferred_skills=[_clean(value) for value in preferred_skills if _clean(value)],
    ))


def _is_relevant_to_profile(job: JobResult, profile: CandidateProfile) -> bool:
    plan = plan_for_profile(profile)
    roles = plan.for_provider("ats", 12)
    if roles:
        return any(_role_matches_title(role, job.title) for role in roles)
    skills = profile.supported_skill_names()
    title_tokens = set(re.findall(r"[a-z0-9+#.]{2,}", job.title.lower()))
    return not skills or bool(skills & title_tokens)


def _is_relevant_to_preferences(job: JobResult, preferences: CandidatePreferences) -> bool:
    values = preferences.target_roles or preferences.career_interests
    return not values or any(_role_matches_title(value, job.title) for value in values)


def _role_matches_title(role: str, title: str) -> bool:
    return role_matches(role, title)


def _parse_company_boards(value: str) -> list[CompanyBoard]:
    boards: list[CompanyBoard] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        company, separator, token = item.partition("=")
        token = token.strip() if separator else company.strip()
        company = company.strip() if separator else token.replace("-", " ").replace("_", " ").title()
        if re.fullmatch(r"[A-Za-z0-9_-]+", token):
            boards.append(CompanyBoard(company=company, token=token))
    return boards


def _registry_boards(provider: str) -> list[CompanyBoard]:
    return [
        CompanyBoard(company=entry.company, token=entry.token)
        for entry in default_public_boards(provider)  # type: ignore[arg-type]
    ]


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _nested_text(item: dict[str, Any], outer: str, inner: str) -> str:
    value = item.get(outer)
    return _clean(value.get(inner)) if isinstance(value, dict) else ""


def _employment_type(value: Any) -> str:
    lowered = _clean(value).lower().replace("_", "-")
    if any(term in lowered for term in ["part-time", "part time", "parttime"]):
        return "Part-time"
    if any(term in lowered for term in ["intern", "internship"]):
        return "Internship"
    if any(term in lowered for term in ["contract", "temporary", "freelance"]):
        return "Contract"
    return "Full-time"


def _date_only(value: Any) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", cleaned)
    return match.group(1) if match else None


def _milliseconds_date(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _relative_date(value: Any) -> str | None:
    cleaned = _clean(value).lower()
    if not cleaned:
        return None
    if cleaned in {"today", "just posted"}:
        return date.today().isoformat()
    match = re.match(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", cleaned)
    if not match:
        return _date_only(cleaned)
    amount = int(match.group(1))
    unit = match.group(2)
    days = amount if unit == "day" else amount * 7 if unit == "week" else amount * 30 if unit == "month" else 0
    return date.fromordinal(date.today().toordinal() - days).isoformat()


def _serpapi_application_url(item: dict[str, Any], publisher: str) -> str:
    options = item.get("apply_options")
    if isinstance(options, list):
        valid = [option for option in options if isinstance(option, dict) and _is_http_url(option.get("link"))]
        preferred = next(
            (option for option in valid if _clean(option.get("title")).lower() == publisher.lower()),
            None,
        )
        if preferred:
            return _clean(preferred.get("link"))
        if valid:
            return _clean(valid[0].get("link"))
    return _clean(item.get("share_link"))


def _indexed_job_match(value: Any) -> tuple[str, str] | None:
    url = _clean(value)
    if not _is_http_url(url):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for site in INDEXED_JOB_SITES:
        if not any(host == domain or host.endswith(f".{domain}") for domain in site.domains):
            continue
        if not re.search(site.path_pattern, parsed.path, flags=re.IGNORECASE):
            return None
        query = parse_qs(parsed.query)
        raw_id = query.get(site.id_query_parameter, [""])[0] if site.id_query_parameter else ""
        if not raw_id:
            path_ids = re.findall(r"[a-z0-9][a-z0-9_-]{5,}", parsed.path.lower())
            raw_id = path_ids[-1] if path_ids else ""
        if not raw_id:
            raw_id = hashlib.sha256(f"{host}{parsed.path}".encode("utf-8")).hexdigest()[:20]
        stable_id = re.sub(r"[^a-z0-9_-]+", "-", raw_id.lower()).strip("-")[:80]
        return (site.source, stable_id)
    return None


def _indexed_title_and_company(value: Any, source: str) -> tuple[str, str]:
    title = re.sub(
        rf"\s*(?:[-|]\s*)?(?:{re.escape(source.replace('-', ' '))}|Indeed\.com|LinkedIn|Glassdoor|SEEK)\s*$",
        "",
        _clean(value),
        flags=re.IGNORECASE,
    )
    hiring = re.match(r"(?P<company>.+?)\s+hiring\s+(?P<role>.+?)(?:\s+Job)?\s+in\s+.+$", title, flags=re.IGNORECASE)
    if hiring:
        return hiring.group("role").strip(), hiring.group("company").strip()
    role, separator, company = title.partition(" at ")
    if separator and role.strip() and company.strip():
        return role.strip(), company.strip()
    return title, ""


def _multiboard_query(
    queries: Iterable[str],
    locations: Iterable[str],
    *,
    rotation_bucket: int = 0,
) -> str:
    roles = _or_terms(queries, fallback="software engineer")
    places = _or_terms(locations, fallback="Australia")
    sites = " OR ".join(f"site:{scope}" for scope in _indexed_scopes(rotation_bucket))
    return f"({roles}) ({places}) ({sites})"


def _indexed_scopes(rotation_bucket: int) -> list[str]:
    core_sources = {"seek", "indeed", "linkedin", "glassdoor", "workforce-australia"}
    core = [site.search_scope for site in INDEXED_JOB_SITES if site.source in core_sources]
    rotating = [site.search_scope for site in INDEXED_JOB_SITES if site.source not in core_sources]
    rotating.extend(indexed_workday_scopes())
    rotating = _unique_text(rotating)
    if not rotating:
        return core
    window_size = min(7, len(rotating))
    offset = rotation_bucket % len(rotating)
    selected = [rotating[(offset + index) % len(rotating)] for index in range(window_size)]
    return [*core, *selected]


def _or_terms(values: Iterable[str], fallback: str) -> str:
    cleaned = _unique_text(values) or [fallback]
    return " OR ".join(f'"{value}"' for value in cleaned)


def _is_http_url(value: Any) -> bool:
    return _clean(value).lower().startswith(("https://", "http://"))


def _source_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "google-jobs"


def _unique_text(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def _unique_jobs(jobs: Iterable[JobResult]) -> list[JobResult]:
    unique: list[JobResult] = []
    seen: set[str] = set()
    for job in jobs:
        key = f"{job.source}:{job.job_id}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def _stable_cache_key(source: str, payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{source}:{digest}"


def _timed_source(operation: Callable[[], list[JobResult]]) -> tuple[list[JobResult], int]:
    started = perf_counter()
    try:
        jobs = operation()
    except LiveSearchError as exc:
        exc.duration_ms = max(0, round((perf_counter() - started) * 1000))
        raise
    return jobs, max(0, round((perf_counter() - started) * 1000))


def _error_category(message: str) -> str:
    lowered = message.lower()
    if not lowered:
        return ""
    if "timeout" in lowered or "deadline" in lowered:
        return "timeout"
    if "network" in lowered:
        return "network"
    if lowered.startswith("http "):
        return "http"
    if "shape" in lowered or "json" in lowered:
        return "invalid_response"
    if "quota" in lowered or "rate" in lowered:
        return "quota"
    return "provider"


def _is_retryable_error(exc: Exception) -> bool:
    if not isinstance(exc, LiveSearchError):
        return False
    message = str(exc).lower()
    if "invalid json" in message or "unexpected response" in message or "circuit open" in message:
        return False
    if message.startswith("http "):
        try:
            status = int(message.split()[1])
        except (IndexError, ValueError):
            return False
        return status == 429 or status >= 500
    return "network" in message or "timeout" in message or "rate" in message or "quota" in message


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))
