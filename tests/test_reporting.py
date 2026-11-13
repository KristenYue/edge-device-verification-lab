from __future__ import annotations

from pathlib import Path

from edge_validation.models import RequirementResult, TestRunSummary
from edge_validation.reporting import load_requirement_results, render_markdown, write_markdown


def test_load_requirement_results(tmp_path: Path) -> None:
    source = tmp_path / "matrix.csv"
    source.write_text(
        "requirement_id,status,test_ids,evidence\nSYS-001,PASS,T-001;T-002,junit.xml\n",
        encoding="utf-8",
    )
    result = load_requirement_results(source)
    assert result[0].test_ids == ("T-001", "T-002")


def test_render_markdown_contains_release_decision() -> None:
    summary = TestRunSummary(
        "run-1",
        "2026-10-20T00:00:00Z",
        3.5,
        2,
        2,
        0,
        0,
        [RequirementResult("SYS-001", "PASS", ("T-001",), "report")],
        {"p95_ms": 12.5},
    )
    report = render_markdown(summary)
    assert "**GO**" in report
    assert "SYS-001" in report
    assert '"p95_ms": 12.5' in report


def test_write_markdown_creates_parent(tmp_path: Path) -> None:
    summary = TestRunSummary("run", "now", 0, 0, 0, 0, 0)
    target = tmp_path / "nested" / "report.md"
    write_markdown(summary, target)
    assert target.exists()

