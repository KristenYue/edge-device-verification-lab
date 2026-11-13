from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceState(StrEnum):
    BOOT = "BOOT"
    IDLE = "IDLE"
    HOMING = "HOMING"
    HOMED = "HOMED"
    CALIBRATING = "CALIBRATING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    E_STOP = "E_STOP"
    RECOVERING = "RECOVERING"


class TaskProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    sample_count: int = Field(ge=10, le=100_000)
    noise_sigma: float = Field(ge=0.0, le=1.0)
    drift_limit: float = Field(gt=0.0, le=5.0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot contain only whitespace")
        return value


class DeviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    sequence: int = Field(ge=1)
    timestamp_ms: int = Field(gt=0)
    ok: bool
    code: str
    message: str
    state: DeviceState
    data: dict[str, str] = Field(default_factory=dict)


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    timestamp_ms: int = Field(gt=0)
    correlation_id: str
    event: str
    from_state: str
    to_state: str
    detail: str


@dataclass(frozen=True)
class RequirementResult:
    requirement_id: str
    status: str
    test_ids: tuple[str, ...]
    evidence: str


@dataclass
class TestRunSummary:
    __test__ = False

    run_id: str
    started_at: str
    duration_seconds: float
    total: int
    passed: int
    failed: int
    skipped: int
    requirement_results: list[RequirementResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def release_recommendation(self) -> str:
        if self.failed:
            return "NO-GO"
        if any(item.status.upper() == "BLOCKED" for item in self.requirement_results):
            return "CONDITIONAL"
        return "GO"


