from __future__ import annotations

import os
from pathlib import Path

from app.schemas.application import ValidationCheck, WorkflowResult
from app.tools.live_job_search import LiveSearchConfig


REQUIRED_FILES = [
    "railway.toml",
    "requirements.txt",
    "runtime.txt",
    "dashboard/streamlit_app.py",
    "sample_data/cvs/aman_sharma_cv.txt",
    "sample_data/jobs/jobs.json",
    "sample_data/preferences.json",
]

REQUIRED_REQUIREMENTS = [
    "openai",
    "pydantic",
    "streamlit",
    "typer",
    "rich",
    "pypdf",
    "python-docx",
]


def deployment_readiness_checks(
    root: str | Path = ".",
    output_path: str | Path = "sample_data/expected_outputs/latest_run.json",
    require_openai: bool = False,
) -> list[ValidationCheck]:
    base = Path(root)
    checks = [
        _check_required_files(base),
        _check_requirements(base / "requirements.txt"),
        _check_runtime(base / "runtime.txt"),
        _check_railway_config(base / "railway.toml"),
        _check_saved_payload(base / output_path),
        _check_openai_env(require_openai),
        _check_live_search_config(),
    ]
    return checks


def _check_required_files(root: Path) -> ValidationCheck:
    missing = [path for path in REQUIRED_FILES if not (root / path).exists()]
    return ValidationCheck(
        part="deployment_files",
        passed=not missing,
        issues=[f"Missing required file: {path}" for path in missing],
    )


def _check_requirements(path: Path) -> ValidationCheck:
    if not path.exists():
        return ValidationCheck(part="requirements", passed=False, issues=["requirements.txt is missing."])
    text = path.read_text(encoding="utf-8").lower()
    missing = [package for package in REQUIRED_REQUIREMENTS if package.lower() not in text]
    return ValidationCheck(
        part="requirements",
        passed=not missing,
        issues=[f"Missing dependency: {package}" for package in missing],
    )


def _check_runtime(path: Path) -> ValidationCheck:
    if not path.exists():
        return ValidationCheck(part="runtime", passed=False, issues=["runtime.txt is missing."])
    runtime = path.read_text(encoding="utf-8").strip()
    issues = []
    if not runtime.startswith("python-3."):
        issues.append("runtime.txt should pin a Python 3 runtime.")
    return ValidationCheck(part="runtime", passed=not issues, issues=issues)


def _check_railway_config(path: Path) -> ValidationCheck:
    if not path.exists():
        return ValidationCheck(part="railway_config", passed=False, issues=["railway.toml is missing."])
    text = path.read_text(encoding="utf-8")
    issues = []
    if "streamlit run dashboard/streamlit_app.py" not in text:
        issues.append("Railway start command does not run the Streamlit dashboard.")
    if "${PORT:-8501}" not in text and "$PORT" not in text:
        issues.append("Railway start command does not bind to Railway's PORT.")
    if "/_stcore/health" not in text:
        issues.append("Railway health check is not configured for Streamlit.")
    return ValidationCheck(part="railway_config", passed=not issues, issues=issues)


def _check_saved_payload(path: Path) -> ValidationCheck:
    if not path.exists():
        return ValidationCheck(part="sample_payload", passed=False, issues=["Run `uv run python main.py run` to create latest_run.json."])
    try:
        result = WorkflowResult.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ValidationCheck(part="sample_payload", passed=False, issues=[f"Payload is invalid: {exc}"])
    failed = [check.part for check in result.validation_checks if not check.passed]
    return ValidationCheck(
        part="sample_payload",
        passed=not failed,
        issues=[f"Payload contains failing validation check: {part}" for part in failed],
    )


def _check_openai_env(require_openai: bool) -> ValidationCheck:
    issues = []
    if require_openai and not os.getenv("OPENAI_API_KEY"):
        issues.append("OPENAI_API_KEY is required but not set.")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    if model != "gpt-5-mini":
        issues.append(f"OPENAI_MODEL is {model}; expected gpt-5-mini for the planned cheap deployment.")
    return ValidationCheck(
        part="openai_env",
        passed=not issues,
        issues=issues,
    )


def _check_live_search_config() -> ValidationCheck:
    config = LiveSearchConfig.from_env()
    sources = []
    if config.adzuna_app_id and config.adzuna_app_key:
        sources.append("Adzuna")
    if config.serpapi_api_key:
        sources.append("SerpApi Google Jobs")
    if config.greenhouse_boards:
        sources.append("Greenhouse")
    if config.lever_sites:
        sources.append("Lever")
    if config.enable_remotive:
        sources.append("Remotive")
    issues = [] if sources else ["No live job source is configured."]
    return ValidationCheck(
        part="live_search_config",
        passed=not issues,
        issues=issues,
    )
