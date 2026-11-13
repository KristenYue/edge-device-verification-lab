from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import RequirementResult, TestRunSummary


def load_requirement_results(path: Path) -> list[RequirementResult]:
    results: list[RequirementResult] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            results.append(
                RequirementResult(
                    requirement_id=row["requirement_id"],
                    status=row.get("status", "NOT_RUN"),
                    test_ids=tuple(
                        item.strip() for item in row.get("test_ids", "").split(";") if item.strip()
                    ),
                    evidence=row.get("evidence", ""),
                )
            )
    return results


def render_markdown(summary: TestRunSummary) -> str:
    lines = [
        "# Release Qualification Report",
        "",
        f"- Run ID: `{summary.run_id}`",
        f"- Started: {summary.started_at}",
        f"- Duration: {summary.duration_seconds:.2f} seconds",
        f"- Result: **{summary.release_recommendation}**",
        (
            f"- Tests: {summary.passed} passed, {summary.failed} failed, "
            f"{summary.skipped} skipped, {summary.total} total"
        ),
        f"- Pass rate: {summary.pass_rate:.1%}",
        "",
        "## Requirement Status",
        "",
        "| Requirement | Status | Tests | Evidence |",
        "|---|---|---|---|",
    ]
    for item in summary.requirement_results:
        tests = ", ".join(item.test_ids) or "-"
        evidence = item.evidence or "-"
        lines.append(f"| {item.requirement_id} | {item.status} | {tests} | {evidence} |")
    lines.extend(
        ["", "## Metrics", "", "```json", json.dumps(summary.metrics, indent=2), "```", ""]
    )
    return "\n".join(lines)


def write_markdown(summary: TestRunSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(summary), encoding="utf-8")
