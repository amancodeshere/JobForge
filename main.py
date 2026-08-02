from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.agents.orchestrator_agent import OrchestratorAgent
from app.evaluation.deployment_readiness import deployment_readiness_checks
from app.evaluation.search_quality import evaluate_benchmark, load_benchmark
from app.schemas.application import WorkflowResult
from app.schemas.candidate import CandidatePreferences
from app.services.latex_resume import LatexCompileError, compile_resume_pdf
from app.tools.job_search import load_jobs_from_json


app = typer.Typer(help="JobForge: grounded multi-agent job application assistant.")
console = Console()


@app.command()
def run(
    cv: str = typer.Option("sample_data/cvs/aman_sharma_cv.txt", "--cv", help="Path to a PDF, DOCX, TXT, or MD CV."),
    preferences: str = typer.Option("sample_data/preferences.json", "--preferences", help="Path to preferences JSON."),
    jobs: str = typer.Option("sample_data/jobs/jobs.json", "--jobs", help="Path to sample/fallback jobs JSON."),
    output: str = typer.Option("sample_data/expected_outputs/latest_run.json", "--output", help="Where to write dashboard payload JSON."),
    top_n: int = typer.Option(5, "--top-n", help="Number of application packages to produce."),
    live: bool = typer.Option(False, "--live/--sample", help="Search live providers instead of only the sample dataset."),
    sample_fallback: bool = typer.Option(True, "--sample-fallback/--no-sample-fallback", help="Use sample jobs if every live source returns no jobs."),
) -> None:
    prefs = CandidatePreferences.model_validate(json.loads(Path(preferences).read_text(encoding="utf-8")))
    result = OrchestratorAgent(sample_jobs_path=jobs).run(
        cv_path=cv,
        preferences=prefs,
        output_path=output,
        top_n=top_n,
        use_live_search=live,
        sample_fallback=sample_fallback,
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


@app.command("benchmark-search")
def benchmark_search(
    benchmark: str = typer.Option(
        "tests/fixtures/search_benchmark.json",
        "--benchmark",
        help="Labelled search benchmark JSON.",
    ),
    jobs: str = typer.Option(
        "sample_data/jobs/jobs.json",
        "--jobs",
        help="Normalized job corpus to rank.",
    ),
    output: str = typer.Option(
        "output/evaluation/search_baseline.json",
        "--output",
        help="Where to write the metrics and per-case rankings.",
    ),
    evaluation_date: str = typer.Option(
        "2026-08-02",
        "--date",
        help="Stable YYYY-MM-DD date used for freshness and validation.",
    ),
    confidence_floor: int = typer.Option(
        42,
        "--confidence-floor",
        min=0,
        max=100,
        help="First-stage score required to enter the full reranker.",
    ),
    result_floor: int = typer.Option(
        62,
        "--result-floor",
        min=0,
        max=100,
        help="Full relevance score required to enter the shortlist.",
    ),
) -> None:
    try:
        measured_on = date.fromisoformat(evaluation_date)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format.") from exc
    report = evaluate_benchmark(
        load_benchmark(benchmark),
        load_jobs_from_json(jobs),
        today=measured_on,
        confidence_floor=confidence_floor,
        result_floor=result_floor,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    metrics = report.metrics
    table = Table(title="Search Quality Baseline")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for label, value in (
        ("Cases", metrics.case_count),
        ("Precision@5", f"{metrics.precision_at_5:.1%}"),
        ("Precision@10", f"{metrics.precision_at_10:.1%}"),
        ("NDCG@10", f"{metrics.ndcg_at_10:.1%}"),
        ("Relevant recall", f"{metrics.relevant_recall:.1%}"),
        ("Duplicate rate", f"{metrics.duplicate_rate:.1%}"),
        ("Invalid link rate", f"{metrics.invalid_link_rate:.1%}"),
    ):
        table.add_row(label, str(value))
    console.print(table)
    console.print(f"Baseline written to [bold]{output_path}[/bold]")


@app.command("export-cv")
def export_cv(
    payload: str = typer.Option("sample_data/expected_outputs/latest_run.json", "--payload", help="Workflow JSON payload."),
    job_index: int = typer.Option(0, "--job-index", min=0, help="Zero-based recommended job index."),
    output: str = typer.Option("output/pdf/tailored_cv.pdf", "--output", help="Destination PDF path."),
) -> None:
    result = WorkflowResult.model_validate_json(Path(payload).read_text(encoding="utf-8"))
    if job_index >= len(result.applications):
        console.print(f"[red]Job index {job_index} is outside the {len(result.applications)} recommendations.[/red]")
        raise typer.Exit(code=2)
    application = result.applications[job_index]
    if not application.tailored_cv_latex:
        console.print("[red]This payload has no LaTeX CV. Run a fresh workflow first.[/red]")
        raise typer.Exit(code=2)
    try:
        compiled = compile_resume_pdf(
            application.tailored_cv_latex,
            expected_name=result.candidate_profile.candidate_name,
        )
    except LatexCompileError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(compiled.pdf_bytes)
    console.print(
        f"Tailored CV written to [bold]{output_path}[/bold] "
        f"({compiled.page_count} page{'s' if compiled.page_count != 1 else ''}, {compiled.engine})"
    )


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
        f"\nSearch: [bold]{result.search_mode}[/bold] ({', '.join(result.search_sources) or 'none'}) | "
        f"[bold]{result.discovered_count}[/bold] roles discovered | "
        f"[bold]{result.validated_count}[/bold] roles passed validation | "
        f"[bold]{result.recommended_count}[/bold] recommended applications\n"
    )
    for warning in result.search_warnings:
        console.print(f"[yellow]Search warning:[/yellow] {warning}")
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
