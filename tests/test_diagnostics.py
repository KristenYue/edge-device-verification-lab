from __future__ import annotations

import json
from pathlib import Path

import pytest

from edge_validation.diagnostics import (
    correlate,
    diagnose,
    load_events,
    write_diagnostic_report,
)
from edge_validation.models import EventRecord


def _event(sequence: int, correlation: str, event: str, target: str) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        timestamp_ms=1_700_000_000_000 + sequence,
        correlation_id=correlation,
        event=event,
        from_state="IDLE",
        to_state=target,
        detail="test",
    )


def test_correlate_sorts_and_filters() -> None:
    events = [
        _event(3, "a", "THREE", "READY"),
        _event(1, "a", "ONE", "IDLE"),
        _event(2, "b", "TWO", "ERROR"),
    ]
    assert [event.sequence for event in correlate(events, "a")] == [1, 3]


def test_diagnose_counts_errors_and_duplicate_sequences() -> None:
    events = [_event(1, "a", "OK", "READY"), _event(1, "b", "ACTUATOR_STUCK", "ERROR")]
    result = diagnose(events)
    assert result["event_count"] == 2
    assert result["duplicate_sequences"] == 1
    assert result["error_codes"] == {"ACTUATOR_STUCK": 1}


def test_diagnose_does_not_count_fault_clear_as_an_error() -> None:
    events = [
        _event(1, "a", "ACTUATOR_STUCK", "ERROR"),
        _event(2, "b", "FAULTS_CLEARED", "ERROR"),
    ]
    assert diagnose(events)["error_codes"] == {"ACTUATOR_STUCK": 1}


def test_load_events_and_write_report(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(_event(1, "a", "OK", "READY").model_dump_json() + "\n", encoding="utf-8")
    events = load_events(source)
    target = tmp_path / "report.json"
    write_diagnostic_report(events, target)
    assert json.loads(target.read_text(encoding="utf-8"))["event_count"] == 1


def test_load_events_empty_missing_file(tmp_path: Path) -> None:
    assert load_events(tmp_path / "missing.jsonl") == []


def test_load_events_reports_line_number(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text("\n{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        load_events(source)


