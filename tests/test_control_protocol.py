from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from edge_validation.client import DeviceClient, RequestEnvelope, checksum
from edge_validation.control_protocol import DeviceControlHost
from edge_validation.models import DeviceState, TaskProfile

pytestmark = pytest.mark.integration


def _online_remote(client: DeviceClient) -> DeviceControlHost:
    host = DeviceControlHost(client)
    assert host.establish_communications().code == "COMMUNICATIONS_ESTABLISHED"
    assert host.set_remote().code == "REMOTE_MODE_ACK"
    return host


def _prepare_process(client: DeviceClient) -> None:
    assert client.power_on().state == DeviceState.IDLE
    assert client.home().state == DeviceState.HOMED
    assert client.calibrate().state == DeviceState.READY


def test_offline_local_remote_control_transitions(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    assert client.status().data["communication_state"] == "OFFLINE"
    assert client.command("protocol_set_remote").code == "PROTOCOL_OFFLINE"
    host = DeviceControlHost(client)
    assert host.establish_communications().data == {
        "communication_state": "ONLINE",
        "control_mode": "LOCAL",
    }
    assert host.set_remote().data["control_mode"] == "REMOTE"
    assert host.set_local().data["control_mode"] == "LOCAL"
    assert host.go_offline().data["communication_state"] == "OFFLINE"


def test_remote_profile_start_stop_and_variable_report(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    _prepare_process(client)
    host = _online_remote(client)
    profile = TaskProfile(name="CTRL-DEMO", sample_count=64, noise_sigma=0.01, drift_limit=0.2)
    assert host.select_profile(profile).data["protocol_message"] == "REMOTE_COMMAND_ACK"
    result = host.start()
    assert result.code == "RUN_COMPLETE"
    assert result.data["command_name"] == "START"
    variables = host.variables()
    assert variables["DEVICE_STATE"] == "COMPLETE"
    assert variables["RUN_COUNT"] == "1"
    assert host.stop().state == DeviceState.IDLE


def test_remote_command_is_rejected_in_local_mode(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    host = DeviceControlHost(client)
    host.establish_communications()
    assert host.host_command("START").code == "PROTOCOL_NOT_REMOTE"


def test_invalid_profile_is_rejected_by_device(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    _prepare_process(client)
    host = _online_remote(client)
    response = host.host_command(
        "PROFILE",
        {"name": "bad", "sample_count": 0, "noise_sigma": 0.1, "drift_limit": 0.2},
    )
    assert not response.ok
    assert response.code == "PROFILE_INVALID"


def test_alarm_report_and_clear(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    host = DeviceControlHost(client)
    host.establish_communications()
    client.inject_fault("interlock_open")
    report = host.alarms()
    assert report.count == 1
    assert report.alarms == ("ALARM-1001:INTERLOCK_OPEN",)
    client.inject_fault("clear")
    assert host.alarms().count == 0


def test_duplicate_start_is_idempotent(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    _prepare_process(client)
    host = _online_remote(client)
    host.select_profile(TaskProfile(name="dup", sample_count=32, noise_sigma=0, drift_limit=0.2))
    first = host.start(request_id="duplicate-start-1")
    second = host.start(request_id="duplicate-start-1")
    assert first.sequence == second.sequence
    assert first.data["run_id"] == second.data["run_id"] == "R-1"
    assert host.variables()["RUN_COUNT"] == "1"


def test_reused_request_id_with_different_content_is_rejected(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    assert client.command("status", request_id="same-id").ok
    conflict = client.command("power_on", request_id="same-id")
    assert conflict.code == "REQUEST_ID_CONFLICT"


def _receive_lines(sock: socket.socket, count: int) -> list[dict[str, object]]:
    buffer = bytearray()
    while buffer.count(b"\n") < count:
        buffer.extend(sock.recv(4096))
    return [json.loads(line) for line in bytes(buffer).splitlines()[:count]]


def test_tcp_half_packet_and_sticky_packet_framing(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    first = RequestEnvelope("half-1", "status", {}, checksum("half-1", "status")).to_bytes()
    second = RequestEnvelope("sticky-2", "status", {}, checksum("sticky-2", "status")).to_bytes()
    third = RequestEnvelope("sticky-3", "status", {}, checksum("sticky-3", "status")).to_bytes()
    with socket.create_connection((client.host, client.port), timeout=1) as sock:
        midpoint = len(first) // 2
        sock.sendall(first[:midpoint])
        sock.sendall(first[midpoint:])
        assert _receive_lines(sock, 1)[0]["request_id"] == "half-1"
        sock.sendall(second + third)
        responses = _receive_lines(sock, 2)
    assert [item["request_id"] for item in responses] == ["sticky-2", "sticky-3"]


def test_concurrent_status_requests_are_correlated(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator

    def request(index: int) -> str:
        response = DeviceClient(port=client.port).command(
            "status", request_id=f"parallel-{index}"
        )
        return response.request_id

    with ThreadPoolExecutor(max_workers=6) as pool:
        request_ids = list(pool.map(request, range(12)))
    assert request_ids == [f"parallel-{index}" for index in range(12)]


def test_timeout_retry_replays_cached_response(
    simulator: tuple[DeviceClient, Path],
) -> None:
    client, _ = simulator
    client.inject_fault("response_delay", delay_ms=80)
    impatient = DeviceClient(port=client.port, timeout=0.03)
    host = DeviceControlHost(impatient, max_retries=1, retry_delay=0.1)
    response = host._send("status", request_id="retry-status-1")
    assert response.ok
    assert response.request_id == "retry-status-1"





