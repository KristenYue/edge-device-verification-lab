from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from edge_validation.smart_shelf import (
    IngestResult,
    SmartShelfContractError,
    SmartShelfGateway,
    validate_command,
    validate_telemetry,
)

FIXTURES = Path(__file__).parent / "fixtures" / "smart_shelf" / "v1"


@pytest.fixture
def shelf1() -> dict[str, object]:
    return json.loads((FIXTURES / "shelf1_telemetry.json").read_text(encoding="utf-8"))


@pytest.fixture
def shelf2() -> dict[str, object]:
    return json.loads((FIXTURES / "shelf2_telemetry.json").read_text(encoding="utf-8"))


def test_versioned_fixtures_match_public_contract(
    shelf1: dict[str, object], shelf2: dict[str, object]
) -> None:
    assert validate_telemetry(shelf1) == shelf1
    assert validate_telemetry(shelf2) == shelf2


@pytest.mark.parametrize("device_id", ["smart-shelf-03", "../../admin", "", None])
def test_unknown_device_is_rejected(shelf1: dict[str, object], device_id: object) -> None:
    shelf1["deviceID"] = device_id
    with pytest.raises(SmartShelfContractError, match="allowed"):
        validate_telemetry(shelf1)


def test_duplicate_out_of_order_and_conflict_are_distinct(shelf1: dict[str, object]) -> None:
    gateway = SmartShelfGateway()
    assert gateway.ingest(shelf1) == IngestResult.ACCEPTED
    assert gateway.ingest(deepcopy(shelf1)) == IngestResult.DUPLICATE

    conflict = deepcopy(shelf1)
    conflict["temperatureC"] = 6.0
    assert gateway.ingest(conflict) == IngestResult.TIMESTAMP_CONFLICT

    older = deepcopy(shelf1)
    older["timestamp"] = int(shelf1["timestamp"]) - 1
    assert gateway.ingest(older) == IngestResult.OUT_OF_ORDER
    assert gateway.record_count == 1


def test_device_ordering_state_is_isolated(
    shelf1: dict[str, object], shelf2: dict[str, object]
) -> None:
    gateway = SmartShelfGateway()
    shelf1["timestamp"] = 200
    shelf2["timestamp"] = 100
    assert gateway.ingest(shelf1) == IngestResult.ACCEPTED
    assert gateway.ingest(shelf2) == IngestResult.ACCEPTED
    assert gateway.latest("smart-shelf-01") == shelf1
    assert gateway.latest("smart-shelf-02") == shelf2


def test_concurrent_duplicates_create_one_record(shelf1: dict[str, object]) -> None:
    gateway = SmartShelfGateway()
    payloads = [deepcopy(shelf1) for _ in range(32)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(gateway.ingest, payloads))
    assert results.count(IngestResult.ACCEPTED) == 1
    assert results.count(IngestResult.DUPLICATE) == 31
    assert gateway.record_count == 1


@pytest.mark.parametrize("command", ["ON", "off", "FLASH", "AUTO"])
def test_shared_commands_are_authorized_for_both_devices(command: str) -> None:
    assert validate_command("smartshelf/cmd/smart-shelf-01", command)[1] == command.upper()
    assert validate_command("smartshelf/cmd/smart-shelf-02", command)[1] == command.upper()


def test_ack_is_authorized_only_for_shelf2() -> None:
    assert validate_command("smartshelf/cmd/smart-shelf-02", "ACK") == (
        "smart-shelf-02",
        "ACK",
    )
    with pytest.raises(SmartShelfContractError, match="not allowed"):
        validate_command("smartshelf/cmd/smart-shelf-01", "ACK")


@pytest.mark.parametrize(
    "topic", ["smartshelf/cmd/smart-shelf-03", "smartshelf/cmd/../../admin", "bad/topic"]
)
def test_unknown_command_target_is_rejected(topic: str) -> None:
    with pytest.raises(SmartShelfContractError, match="unknown"):
        validate_command(topic, "ON")
