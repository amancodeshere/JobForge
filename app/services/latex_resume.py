from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
from tempfile import TemporaryDirectory

from pypdf import PdfReader

from app.schemas.application import TailoredStatement
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobResult


class LatexCompileError(RuntimeError):
    """A safe, user-facing failure while compiling a generated resume."""


@dataclass(frozen=True)
class CompiledResume:
    pdf_bytes: bytes
    engine: str
    page_count: int
    extracted_text: str


def build_resume_latex(
    profile: CandidateProfile,
    job: JobResult,
    statements: list[TailoredStatement],
) -> str:
    """Build trusted LaTeX from CV-backed fields; model-authored LaTeX is never executed."""
    supported_skills = [skill.name for skill in profile.skills if skill.name]
    education = [
        item.original_text
        for item in profile.verified_evidence
        if item.cv_section == "Education"
    ]
    highlights = [statement.tailored_bullet for statement in statements if statement.tailored_bullet]
    if not highlights:
        highlights = [project.description for project in profile.projects[:4] if project.description]
    highlighted = {_content_key(item) for item in highlights}
    projects = [
        project.description
        for project in profile.projects
        if project.description and _content_key(project.description) not in highlighted
    ][:5]
    locations = ", ".join(profile.locations)
    summary = (
        f"{profile.experience_level.title()} candidate targeting {job.title} opportunities at "
        f"{job.company}, with evidence-backed strengths in "
        f"{', '.join(supported_skills[:8]) or 'relevant technical projects'}."
    )

    return _TEMPLATE.substitute(
        name=_tex_escape(profile.candidate_name),
        target=_tex_escape(f"Target role: {job.title} - {job.company}"),
        location=_tex_escape(locations),
        summary=_tex_escape(summary),
        skills=_tex_escape(" | ".join(supported_skills[:18]) or "CV-backed skills available on request"),
        highlights=_itemize(highlights[:5]),
        projects=_itemize(projects[:5]),
        education=_itemize(education[:3]),
    )


def compile_resume_pdf(
    latex_source: str,
    *,
    expected_name: str = "",
    timeout: float = 120.0,
) -> CompiledResume:
    _validate_generated_source(latex_source)
    engine = _find_engine()
    if not engine:
        raise LatexCompileError(
            "No LaTeX engine is available. Install Tectonic or pdflatex, then try again."
        )
    with TemporaryDirectory(prefix="jobforge-latex-") as temp:
        workdir = Path(temp)
        source_path = workdir / "resume.tex"
        source_path.write_text(latex_source, encoding="utf-8")
        command = _compile_command(engine, source_path, workdir)
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LatexCompileError("LaTeX compilation timed out.") from exc
        pdf_path = workdir / "resume.pdf"
        if completed.returncode != 0 or not pdf_path.exists():
            detail = _safe_compile_detail(completed.stdout, completed.stderr)
            raise LatexCompileError(f"LaTeX compilation failed{': ' + detail if detail else '.'}")
        pdf_bytes = pdf_path.read_bytes()
    return _verify_pdf(pdf_bytes, engine=Path(engine).name, expected_name=expected_name)


def latex_engine_available() -> bool:
    return _find_engine() is not None


def _find_engine() -> str | None:
    configured = os.getenv("JOBFORGE_LATEX_ENGINE", "").strip()
    if configured:
        resolved = shutil.which(configured)
        if not resolved:
            raise LatexCompileError(f"Configured LaTeX engine is unavailable: {configured}")
        return resolved
    return shutil.which("tectonic") or shutil.which("pdflatex")


def _compile_command(engine: str, source_path: Path, output_dir: Path) -> list[str]:
    if Path(engine).name == "tectonic":
        return [engine, "--keep-logs", "--outdir", str(output_dir), str(source_path)]
    return [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        f"-output-directory={output_dir}",
        str(source_path),
    ]


def _validate_generated_source(source: str) -> None:
    if not source.startswith("% JobForge trusted resume template"):
        raise LatexCompileError("Refusing to compile LaTeX outside the trusted JobForge template.")
    banned = [r"\write18", r"\input", r"\include", r"\openin", r"\openout", r"\immediate"]
    if any(command in source.lower() for command in banned):
        raise LatexCompileError("Refusing to compile a template containing unsafe LaTeX commands.")


def _verify_pdf(pdf_bytes: bytes, *, engine: str, expected_name: str) -> CompiledResume:
    if not pdf_bytes.startswith(b"%PDF"):
        raise LatexCompileError("The LaTeX engine did not produce a valid PDF.")
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise LatexCompileError("The generated PDF could not be reopened for verification.") from exc
    if page_count < 1 or page_count > 2:
        raise LatexCompileError(f"Generated resume must be one or two pages; received {page_count}.")
    if len(extracted) < 80:
        raise LatexCompileError("Generated resume PDF contains too little extractable text.")
    expected_tokens = [token.lower() for token in expected_name.split() if len(token) > 1]
    if expected_tokens and not all(token in extracted.lower() for token in expected_tokens):
        raise LatexCompileError("Generated resume PDF is missing the candidate name.")
    return CompiledResume(
        pdf_bytes=pdf_bytes,
        engine=engine,
        page_count=page_count,
        extracted_text=extracted,
    )


def _safe_compile_detail(stdout: str, stderr: str) -> str:
    lines = [line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
    safe = [line for line in lines if not re.search(r"[/\\].*(?:resume\.tex|jobforge-latex)", line)]
    return " ".join(safe[-2:])[:300]


def _itemize(items: list[str]) -> str:
    if not items:
        return r"\item CV-backed details available on request."
    return "\n".join(r"\item " + _tex_escape(item) for item in items)


def _tex_escape(value: str) -> str:
    text = str(value or "").replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _content_key(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


_TEMPLATE = Template(r"""% JobForge trusted resume template
\documentclass[10pt,a4paper]{article}
\usepackage[margin=0.65in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{xcolor}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{3pt}
\setlist[itemize]{leftmargin=1.2em,itemsep=2pt,topsep=3pt}
\definecolor{ink}{HTML}{162033}
\definecolor{accent}{HTML}{087F75}
\newcommand{\cvsection}[1]{\vspace{6pt}{\large\bfseries\color{accent} #1}\vspace{2pt}\par\hrule\vspace{4pt}}
\begin{document}
{\Huge\bfseries\color{ink} $name}\\[4pt]
{\small\color{accent} $target}\\
{\small $location}

\cvsection{Professional Profile}
$summary

\cvsection{Core Skills}
$skills

\cvsection{Selected Evidence-Based Highlights}
\begin{itemize}
$highlights
\end{itemize}

\cvsection{Technical Projects}
\begin{itemize}
$projects
\end{itemize}

\cvsection{Education}
\begin{itemize}
$education
\end{itemize}
\end{document}
""")
