from __future__ import annotations

import html
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from app.schemas.candidate import CandidatePreferences, CandidateProfile
from app.schemas.job import JobResult


USER_AGENT = "JobForge/0.2 (+https://github.com/)"


class LiveSearchError(RuntimeError):
    """A recoverable failure from an external job source."""


@dataclass(frozen=True)
class CompanyBoard:
    company: str
    token: str


DEFAULT_GREENHOUSE_BOARDS = (CompanyBoard("Canonical", "canonical"),)


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
    request_timeout: float = 12.0
    results_per_source: int = 50
    max_search_queries: int = 4
    max_workers: int = 6

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
                else DEFAULT_GREENHOUSE_BOARDS
            ),
            lever_sites=tuple(_parse_company_boards(os.getenv("JOBFORGE_LEVER_SITES", ""))),
            request_timeout=_env_float("JOBFORGE_SEARCH_TIMEOUT", 12.0, minimum=1.0, maximum=30.0),
            results_per_source=_env_int("JOBFORGE_RESULTS_PER_SOURCE", 50, minimum=1, maximum=100),
            max_search_queries=_env_int("JOBFORGE_MAX_SEARCH_QUERIES", 4, minimum=1, maximum=8),
            max_workers=_env_int("JOBFORGE_SEARCH_WORKERS", 6, minimum=1, maximum=12),
        )


@dataclass
class SearchOutcome:
    jobs: list[JobResult] = field(default_factory=list)
    sources_attempted: list[str] = field(default_factory=list)
    source_errors: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)


JsonFetcher = Callable[[str, float], Any]


class LiveJobSearch:
    """Fetch and normalize jobs from live, documented job endpoints."""

    def __init__(
        self,
        config: LiveSearchConfig | None = None,
        fetch_json: JsonFetcher | None = None,
    ) -> None:
        self.config = config or LiveSearchConfig.from_env()
        self.fetch_json = fetch_json or _request_json

    def broad_search(self, preferences: CandidatePreferences) -> SearchOutcome:
        queries = _preferred_queries(preferences)
        operations: list[tuple[str, Callable[[], list[JobResult]]]] = []
        if self.config.adzuna_app_id and self.config.adzuna_app_key:
            operations.append(("adzuna", lambda: self._search_adzuna(preferences, queries)))
        if self.config.enable_remotive:
            operations.append(("remotive", lambda: self._search_remotive(preferences, queries)))
        if self.config.serpapi_api_key:
            if self.config.serpapi_country == "au":
                operations.append(("serpapi-multiboard", lambda: self._search_serpapi_multiboard(preferences, queries)))
            else:
                operations.append(("serpapi-google-jobs", lambda: self._search_serpapi_jobs(preferences, queries)))
        return self._run_sources(operations)

    def targeted_search(self, profile: CandidateProfile) -> SearchOutcome:
        operations: list[tuple[str, Callable[[], list[JobResult]]]] = []
        for board in self.config.greenhouse_boards:
            source = f"greenhouse:{board.token}"
            operations.append((source, lambda board=board: self._search_greenhouse(board, profile)))
        for board in self.config.lever_sites:
            source = f"lever:{board.token}"
            operations.append((source, lambda board=board: self._search_lever(board, profile)))
        return self._run_sources(operations)

    def _run_sources(
        self,
        operations: list[tuple[str, Callable[[], list[JobResult]]]],
    ) -> SearchOutcome:
        outcome = SearchOutcome(sources_attempted=[source for source, _ in operations])
        if not operations:
            return outcome
        results: dict[str, list[JobResult]] = {}
        errors: dict[str, str] = {}
        workers = min(self.config.max_workers, len(operations))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job-source") as executor:
            futures = {executor.submit(operation): source for source, operation in operations}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    results[source] = future.result()
                except LiveSearchError as exc:
                    errors[source] = str(exc)
        for source, _ in operations:
            jobs = results.get(source, [])
            outcome.jobs.extend(jobs)
            outcome.source_counts[source] = len(jobs)
            if source in errors:
                outcome.source_errors.append(f"{source}: {errors[source]}")
        outcome.jobs = _unique_jobs(outcome.jobs)
        return outcome

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
            payload = self.fetch_json(url, self.config.request_timeout)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            for item in payload.get("results", []):
                job = _adzuna_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return jobs

    def _search_serpapi_multiboard(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
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
        payload = self.fetch_json(
            f"https://serpapi.com/search.json?{urlencode(params)}",
            self.config.request_timeout,
        )
        if not isinstance(payload, dict):
            raise LiveSearchError("unexpected response shape")
        if payload.get("error"):
            raise LiveSearchError(_clean(payload["error"]))
        jobs = []
        for item in payload.get("organic_results", []):
            job = _serpapi_indexed_job(item, fallback_location=location)
            if job and _is_relevant_to_preferences(job, preferences):
                jobs.append(job)
        return jobs[: self.config.results_per_source]

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
            payload = self.fetch_json(
                f"https://serpapi.com/search.json?{urlencode(params)}",
                self.config.request_timeout,
            )
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            if payload.get("error"):
                raise LiveSearchError(_clean(payload["error"]))
            for item in payload.get("jobs_results", []):
                job = _serpapi_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return jobs[: self.config.results_per_source]

    def _search_remotive(
        self,
        preferences: CandidatePreferences,
        queries: list[str],
    ) -> list[JobResult]:
        jobs: list[JobResult] = []
        for query in queries[:3]:
            url = f"https://remotive.com/api/remote-jobs?{urlencode({'search': query, 'limit': self.config.results_per_source})}"
            payload = self.fetch_json(url, self.config.request_timeout)
            if not isinstance(payload, dict):
                raise LiveSearchError("unexpected response shape")
            for item in payload.get("jobs", []):
                job = _remotive_job(item)
                if job and _is_relevant_to_preferences(job, preferences):
                    jobs.append(job)
        return jobs

    def _search_greenhouse(self, board: CompanyBoard, profile: CandidateProfile) -> list[JobResult]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board.token}/jobs?content=true"
        payload = self.fetch_json(url, self.config.request_timeout)
        if not isinstance(payload, dict):
            raise LiveSearchError("unexpected response shape")
        jobs = [_greenhouse_job(item, board) for item in payload.get("jobs", [])]
        return [job for job in jobs if job and _is_relevant_to_profile(job, profile)][: self.config.results_per_source]

    def _search_lever(self, board: CompanyBoard, profile: CandidateProfile) -> list[JobResult]:
        url = f"https://api.lever.co/v0/postings/{board.token}?mode=json&limit={self.config.results_per_source}"
        payload = self.fetch_json(url, self.config.request_timeout)
        if not isinstance(payload, list):
            raise LiveSearchError("unexpected response shape")
        jobs = [_lever_job(item, board) for item in payload]
        return [job for job in jobs if job and _is_relevant_to_profile(job, profile)][: self.config.results_per_source]


def _request_json(url: str, timeout: float) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise LiveSearchError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise LiveSearchError(f"network error: {exc.reason if isinstance(exc, URLError) else exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveSearchError("invalid JSON response") from exc


def _preferred_queries(preferences: CandidatePreferences) -> list[str]:
    values = preferences.target_roles or preferences.career_interests or ["software engineer"]
    return _unique_text(values)[:5]


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
    return JobResult(
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
    )


def _is_relevant_to_profile(job: JobResult, profile: CandidateProfile) -> bool:
    roles = [*profile.target_roles, *profile.career_themes]
    if roles:
        return any(_role_matches_title(role, job.title) for role in roles)
    skills = profile.supported_skill_names()
    title_tokens = set(re.findall(r"[a-z0-9+#.]{2,}", job.title.lower()))
    return not skills or bool(skills & title_tokens)


def _is_relevant_to_preferences(job: JobResult, preferences: CandidatePreferences) -> bool:
    values = preferences.target_roles or preferences.career_interests
    return not values or any(_role_matches_title(value, job.title) for value in values)


def _role_matches_title(role: str, title: str) -> bool:
    role_tokens = {_normalize_role_token(token) for token in re.findall(r"[a-z0-9+#.]{2,}", role.lower())}
    title_tokens = {_normalize_role_token(token) for token in re.findall(r"[a-z0-9+#.]{2,}", title.lower())}
    levels = {"graduate", "junior", "entry", "level", "intern", "internship", "associate", "senior"}
    occupations = {"engineer", "science", "analyst"}
    distinctive = role_tokens - levels - occupations
    if not distinctive or not distinctive.issubset(title_tokens):
        return False
    requested_occupation = bool(role_tokens & occupations)
    return not requested_occupation or bool(title_tokens & occupations)


def _normalize_role_token(token: str) -> str:
    aliases = {
        "engineering": "engineer",
        "developer": "engineer",
        "development": "engineer",
        "scientist": "science",
        "analytics": "analyst",
    }
    return aliases.get(token, token)


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


def _multiboard_query(queries: Iterable[str], locations: Iterable[str]) -> str:
    roles = _or_terms(queries, fallback="software engineer")
    places = _or_terms(locations, fallback="Australia")
    sites = " OR ".join(f"site:{site.search_scope}" for site in INDEXED_JOB_SITES)
    return f"({roles}) ({places}) ({sites})"


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
