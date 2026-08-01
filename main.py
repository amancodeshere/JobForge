from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.agents.orchestrator_agent import OrchestratorAgent
from app.evaluation.deployment_readiness import deployment_readiness_checks
from app.schemas.application import WorkflowResult
from app.schemas.candidate import CandidatePreferences


app = typer.Typer(help="JobForge: grounded multi-agent job application assistant.")
console = Console()


@app.command()
def run(
    cv: str = typer.Option("sample_data/cvs/aman_sharma_cv.txt", "--cv", help="Path to a PDF, DOCX, TXT, or MD CV."),
    preferences: str = typer.Option("sample_data/preferences.json", "--preferences", help="Path to preferences JSON."),
    jobs: str = typer.Option("sample_data/jobs/jobs.json", "--jobs", help="Path to sample/fallback jobs JSON."),
    output: str = typer.Option("sample_data/expected_outputs/latest_run.json", "--output", help="Where to write dashboard payload JSON."),
    top_n: int = typer.Option(5, "--top-n", help="Number of application packages to produce."),
) -> None:
    prefs = CandidatePreferences.model_validate(json.loads(Path(preferences).read_text(encoding="utf-8")))
    result = OrchestratorAgent(sample_jobs_path=jobs).run(
        cv_path=cv,
        preferences=prefs,
        output_path=output,
        top_n=top_n,
    )
    _print_result(result, output)


@app.command()
def validate(
    output: str = typer.Option("sample_data/expected_outputs/latest_run.json", "--output", help="Workflow JSON payload to validate."),
) -> None:
    result = WorkflowResult.model_validate_json(Path(output).read_text(encoding="utf-8"))
    failed = [check for check in result.validation_checks if not check.passed]
    _print_checks(result)
    if failed:
        raise typer.Exit(code=1)


@app.command()
def doctor(
    output: str = typer.Option("sample_data/expected_outputs/latest_run.json", "--output", help="Workflow JSON payload to inspect."),
    require_openai: bool = typer.Option(False, "--require-openai", help="Fail if OPENAI_API_KEY is not set."),
) -> None:
    checks = deployment_readiness_checks(output_path=output, require_openai=require_openai)
    table = Table(title="Deployment Readiness")
    table.add_column("Part")
    table.add_column("Status")
    table.add_column("Issues")
    for check in checks:
        table.add_row(
            check.part,
            "passed" if check.passed else "failed",
            "; ".join(check.issues) if check.issues else "-",
        )
    console.print(table)
    if any(not check.passed for check in checks):
        raise typer.Exit(code=1)


def _print_result(result: WorkflowResult, output: str) -> None:
    console.print(
        f"\n[bold]{result.discovered_count}[/bold] roles discovered | "
        f"[bold]{result.validated_count}[/bold] roles passed validation | "
        f"[bold]{result.recommended_count}[/bold] recommended applications\n"
    )
    table = Table(title="Recommended Jobs")
    table.add_column("Job")
    table.add_column("Company")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    for application in result.applications:
        table.add_row(
            application.job.title,
            application.job.company,
            str(application.relevance_score),
            application.recommendation.value,
        )
    console.print(table)
    _print_checks(result)
    console.print(f"\nDashboard payload written to [bold]{output}[/bold]")


def _print_checks(result: WorkflowResult) -> None:
    table = Table(title="Validation Checks")
    table.add_column("Part")
    table.add_column("Status")
    table.add_column("Issues")
    for check in result.validation_checks:
        table.add_row(
            check.part,
            "passed" if check.passed else "failed",
            "; ".join(check.issues) if check.issues else "-",
        )
    console.print(table)


if __name__ == "__main__":
    app()
