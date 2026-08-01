from __future__ import annotations

import json
from pathlib import Path

from app.schemas.application import WorkflowResult


class DashboardAgent:
    name = "dashboard_generator"

    def write_payload(self, result: WorkflowResult, output_path: str) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    def summary_table(self, result: WorkflowResult) -> list[dict[str, str | int]]:
        return [
            {
                "job": application.job.title,
                "company": application.job.company,
                "score": application.relevance_score,
                "recommendation": application.recommendation.value,
            }
            for application in result.applications
        ]

