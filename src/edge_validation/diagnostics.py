from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .models import EventRecord


def load_events(path: Path) -> list[EventRecord]:
    events: list[EventRecord] = []
    if not path.exists():
        return events
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(EventRecord.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"invalid event at line {line_number}: {exc}") from exc
    return events


def correlate(events: Iterable[EventRecord], correlation_id: str) -> list[EventRecord]:
    return sorted(
        (event for event in events if event.correlation_id == correlation_id),
        key=lambda event: (event.timestamp_ms, event.sequence),
    )


def diagnose(events: Iterable[EventRecord]) -> dict[str, object]:
    records = list(events)
    non_failure_events = {"FAULT_INJECTED", "FAULTS_CLEARED"}
    error_codes = Counter(
        event.event
        for event in records
        if event.event not in non_failure_events
        and (event.to_state in {"ERROR", "E_STOP"} or "FAILED" in event.event)
    )
    transitions = Counter(f"{event.from_state}->{event.to_state}" for event in records)
    correlations = Counter(event.correlation_id for event in records)
    return {
        "event_count": len(records),
        "error_codes": dict(sorted(error_codes.items())),
        "state_transitions": dict(sorted(transitions.items())),
        "correlation_count": len(correlations),
        "duplicate_sequences": len(records) - len({event.sequence for event in records}),
    }


def write_diagnostic_report(events: Iterable[EventRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(diagnose(events), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
