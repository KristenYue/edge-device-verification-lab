from __future__ import annotations

import time
from pathlib import Path

import pytest

from edge_validation.client import DeviceClient, DeviceTimeoutError
from edge_validation.diagnostics import diagnose, load_events
from edge_validation.models import DeviceState, TaskProfile

pytestmark = pytest.mark.integration


def _prepare(client: DeviceClient) -> None:
    assert client.power_on().code == "SELF_TEST_PASSED"
    assert client.home().state == DeviceState.HOMED
    assert client.calibrate().state == DeviceState.READY


def test_e2e_run_and_trace(simulator: tuple[DeviceClient, Path]) -> None:
    client, event_log = simulator
    _prepare(client)
    profile = TaskProfile(name="batch-A", sample_count=128, noise_sigma=0.02, drift_limit=0.2)
    assert client.load_profile(profile).code == "PROFILE_LOADED"
    result = client.start_run()
    assert result.ok
    assert result.state == DeviceState.COMPLETE
    assert result.data["run_id"] == "R-1"
    time.sleep(0.05)
    report = diagnose(load_events(event_log))
    assert report["duplicate_sequences"] == 0
    assert report["event_count"] >= 7


@pytest.mark.parametrize(
    "command", ["home", "calibrate", "load_profile", "start_run", "reset"]
)
def test_commands_are_rejected_in_boot(simulator: tuple[DeviceClient, Path], command: str) -> None:
    client, _ = simulator
    params = (
        {"name": "x", "sample_count": 10, "noise_sigma": 0, "drift_limit": 0.2}
        if command == "load_profile"
        else None
    )
    result = client.command(command, params)
    assert not result.ok
    assert result.code == "INVALID_STATE"


def test_crc_corruption_is_detected(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    result = client.command("status", corrupt_crc=True)
    assert not result.ok
    assert result.code == "CRC_ERROR"


def test_interlock_forces_safe_state(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    client.power_on()
    client.inject_fault("interlock_open")
    result = client.home()
    assert result.state == DeviceState.E_STOP
    assert result.code == "INTERLOCK_OPEN"
    assert client.command("clear_emergency_stop").state == DeviceState.IDLE


def test_actuator_stuck_can_be_recovered(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    client.power_on()
    client.inject_fault("actuator_stuck")
    assert client.home().code == "ACTUATOR_STUCK"
    client.inject_fault("clear")
    assert client.home().state == DeviceState.HOMED


def test_sensor_drift_fails_calibration_closed(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    client.power_on()
    client.home()
    client.inject_fault("sensor_drift")
    result = client.calibrate()
    assert result.state == DeviceState.ERROR
    assert result.code == "CALIBRATION_FAILED"


def test_delayed_response_triggers_client_timeout(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    client.inject_fault("response_delay", delay_ms=500)
    impatient = DeviceClient(port=client.port, timeout=0.05)
    with pytest.raises(DeviceTimeoutError):
        impatient.status()


@pytest.mark.stability
def test_repeated_runs_are_unique(simulator: tuple[DeviceClient, Path]) -> None:
    client, _ = simulator
    _prepare(client)
    profile = TaskProfile(name="repeat", sample_count=32, noise_sigma=0.01, drift_limit=0.2)
    ids: set[str] = set()
    for _ in range(50):
        client.load_profile(profile)
        result = client.start_run()
        assert result.ok
        ids.add(result.data["run_id"])
    assert len(ids) == 50



