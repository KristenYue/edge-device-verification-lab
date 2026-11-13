"""Versioned Smart Shelf contract adapter used by local verification scenarios."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

DEVICE_IDS = frozenset({"smart-shelf-01", "smart-shelf-02"})
SHELF2_STATES = frozenset(
    {"NORMAL", "ALERT_LIGHT", "ALERT_SOUND", "LOW_STOCK", "OUT_OF_STOCK", "MANUAL_ALARM"}
)


class SmartShelfContractError(ValueError):
    """Raised when a Smart Shelf topic or payload violates the v1 contract."""


class IngestResult(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    TIMESTAMP_CONFLICT = "timestamp_conflict"


def _require_mapping(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise SmartShelfContractError("payload must be a JSON object")
    return payload


def _require_fields(payload: Mapping[str, Any], fields: set[str]) -> None:
    missing = sorted(fields - payload.keys())
    if missing:
        raise SmartShelfContractError(f"missing required fields: {', '.join(missing)}")


def _number(payload: Mapping[str, Any], name: str, low: float, high: float) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SmartShelfContractError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise SmartShelfContractError(f"{name} must be between {low} and {high}")
    return number


def _integer(payload: Mapping[str, Any], name: str, low: int, high: int) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SmartShelfContractError(f"{name} must be an integer")
    if not low <= value <= high:
        raise SmartShelfContractError(f"{name} must be between {low} and {high}")
    return value


def _boolean(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise SmartShelfContractError(f"{name} must be a boolean")
    return value


def validate_telemetry(payload: Any) -> dict[str, Any]:
    """Validate a v1 Smart Shelf telemetry payload and return a defensive copy."""

    data = _require_mapping(payload)
    _require_fields(data, {"deviceID", "timestamp"})
    device_id = data["deviceID"]
    if not isinstance(device_id, str) or device_id not in DEVICE_IDS:
        raise SmartShelfContractError("deviceID is not an allowed Smart Shelf device")
    _integer(data, "timestamp", 1, 4_102_444_800)

    if device_id == "smart-shelf-01":
        _require_fields(
            data,
            {
                "temperatureC",
                "humidityPct",
                "pressureKPa",
                "distanceCm",
                "lightRaw",
                "customerPresent",
                "visitorCount",
                "interactionCount",
                "environmentAlert",
            },
        )
        _number(data, "temperatureC", -40, 85)
        _number(data, "humidityPct", 0, 100)
        _number(data, "pressureKPa", 30, 120)
        _number(data, "distanceCm", 0, 500)
        _integer(data, "lightRaw", 0, 1023)
        _integer(data, "visitorCount", 0, 2_147_483_647)
        _integer(data, "interactionCount", 0, 2_147_483_647)
        _boolean(data, "customerPresent")
        _boolean(data, "environmentAlert")
    else:
        _require_fields(
            data,
            {
                "weightG",
                "soundRaw",
                "lightRaw",
                "buttonPressed",
                "state",
                "uptimeMs",
                "scaleHealthy",
            },
        )
        _number(data, "weightG", -1, 100_000)
        _integer(data, "soundRaw", 0, 1023)
        _integer(data, "lightRaw", 0, 1023)
        _integer(data, "uptimeMs", 0, 4_294_967_295)
        _boolean(data, "buttonPressed")
        _boolean(data, "scaleHealthy")
        if data["state"] not in SHELF2_STATES:
            raise SmartShelfContractError("state is not supported")

    return dict(data)


def validate_command(topic: str, command: str) -> tuple[str, str]:
    """Validate device identity and command authorization for a control topic."""

    if not isinstance(topic, str) or not isinstance(command, str):
        raise SmartShelfContractError("topic and command must be strings")
    match = re.fullmatch(r"smartshelf/cmd/(smart-shelf-\d{2})", topic)
    if not match or match.group(1) not in DEVICE_IDS:
        raise SmartShelfContractError("command topic targets an unknown device")
    device_id = match.group(1)
    if len(command) > 16 or any(ord(character) < 32 for character in command):
        raise SmartShelfContractError("command contains unsafe characters")
    normalized = command.strip().upper()
    allowed = {"ON", "OFF", "FLASH", "AUTO"}
    if device_id == "smart-shelf-02":
        allowed.add("ACK")
    if normalized not in allowed:
        raise SmartShelfContractError("command is not allowed for this device")
    return device_id, normalized


@dataclass(frozen=True)
class StoredTelemetry:
    device_id: str
    timestamp: int
    fingerprint: str
    payload: dict[str, Any]


class SmartShelfGateway:
    """Thread-safe in-memory gateway for ordering and isolation verification."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_timestamp: dict[str, int] = {}
        self._fingerprints: dict[tuple[str, int], str] = {}
        self._records: list[StoredTelemetry] = []

    def ingest(self, payload: dict[str, Any]) -> IngestResult:
        validated = validate_telemetry(payload)
        device_id = str(validated["deviceID"])
        timestamp = int(validated["timestamp"])
        canonical = json.dumps(validated, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        identity = (device_id, timestamp)

        with self._lock:
            if identity in self._fingerprints:
                if self._fingerprints[identity] == fingerprint:
                    return IngestResult.DUPLICATE
                return IngestResult.TIMESTAMP_CONFLICT
            if timestamp < self._latest_timestamp.get(device_id, 0):
                return IngestResult.OUT_OF_ORDER
            self._fingerprints[identity] = fingerprint
            self._latest_timestamp[device_id] = timestamp
            self._records.append(
                StoredTelemetry(device_id, timestamp, fingerprint, dict(validated))
            )
        return IngestResult.ACCEPTED

    def latest(self, device_id: str) -> dict[str, Any] | None:
        if device_id not in DEVICE_IDS:
            raise SmartShelfContractError("unknown device")
        with self._lock:
            for record in reversed(self._records):
                if record.device_id == device_id:
                    return dict(record.payload)
        return None

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)
