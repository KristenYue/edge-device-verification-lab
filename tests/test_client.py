from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator

import pytest

from edge_validation.client import (
    DeviceClient,
    DeviceProtocolError,
    RequestEnvelope,
    checksum,
)


@pytest.mark.parametrize(
    ("request_id", "command", "expected"),
    [
        ("r-1", "status", "CAE57524"),
        ("abc", "power_on", "943F1436"),
        ("中文", "home", "D2035A3D"),
    ],
)
def test_checksum_is_deterministic(request_id: str, command: str, expected: str) -> None:
    assert checksum(request_id, command) == expected


def test_request_envelope_is_single_line_json() -> None:
    envelope = RequestEnvelope("r-1", "status", {}, checksum("r-1", "status"))
    payload = envelope.to_bytes()
    assert payload.endswith(b"\n")
    decoded = json.loads(payload)
    assert decoded["command"] == "status"


@pytest.mark.parametrize(("port", "timeout"), [(0, 1.0), (65536, 1.0), (1000, 0.0), (1000, -1.0)])
def test_client_rejects_invalid_configuration(port: int, timeout: float) -> None:
    with pytest.raises(ValueError):
        DeviceClient(port=port, timeout=timeout)


def _one_shot_server(response: bytes) -> Iterator[int]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = int(server.getsockname()[1])

    def worker() -> None:
        with server:
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(response)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield port
    thread.join(timeout=1)


@pytest.mark.parametrize("response", [b"not-json\n", b"{}\n", b"\xff\n", b"unterminated"])
def test_client_rejects_malformed_response(response: bytes) -> None:
    generator = _one_shot_server(response)
    port = next(generator)
    try:
        with pytest.raises(DeviceProtocolError):
            DeviceClient(port=port).status()
    finally:
        with pytest.raises(StopIteration):
            next(generator)

