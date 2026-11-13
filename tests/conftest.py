from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from edge_validation.client import DeviceClient


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def simulator(tmp_path: Path) -> Iterator[tuple[DeviceClient, Path]]:
    binary_value = os.environ.get("EDGE_SIMULATOR_BIN")
    if not binary_value:
        pytest.skip("EDGE_SIMULATOR_BIN is not configured")
    binary = Path(binary_value)
    if not binary.exists():
        pytest.skip(f"simulator binary does not exist: {binary}")
    port = _free_port()
    event_log = tmp_path / "events.jsonl"
    process = subprocess.Popen(
        [str(binary), "--port", str(port), "--log", str(event_log)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(f"simulator exited early\nstdout={stdout}\nstderr={stderr}")
            try:
                client = DeviceClient(port=port, timeout=0.5)
                client.status()
                yield client, event_log
                return
            except Exception:
                time.sleep(0.05)
        pytest.fail("simulator did not become ready within five seconds")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

