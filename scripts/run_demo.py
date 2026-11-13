from __future__ import annotations

import argparse
import os
import socket
import subprocess
import time
from pathlib import Path

from edge_validation.client import DeviceClient
from edge_validation.diagnostics import diagnose, load_events
from edge_validation.models import TaskProfile


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--simulator",
        type=Path,
        default=Path(os.environ.get("EDGE_SIMULATOR_BIN", "build/edge_device_simulator.exe")),
    )
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    if not args.simulator.exists():
        parser.error(f"simulator not found: {args.simulator}")

    args.artifacts.mkdir(parents=True, exist_ok=True)
    event_log = args.artifacts / "demo-events.jsonl"
    if event_log.exists():
        event_log.unlink()
    port = free_port()
    process = subprocess.Popen(
        [str(args.simulator), "--port", str(port), "--log", str(event_log)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        client = DeviceClient(port=port, timeout=1.0)
        for _ in range(50):
            try:
                client.status()
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("simulator did not become ready")

        print("1. Normal run workflow")
        for response in (
            client.power_on(),
            client.home(),
            client.calibrate(),
            client.load_profile(
                TaskProfile(name="batch-demo", sample_count=128, noise_sigma=0.02, drift_limit=0.2)
            ),
            client.start_run(),
        ):
            print(f"   {response.code:<24} state={response.state}")

        print("2. Reset and inject an actuator fault")
        print(f"   {client.command('reset').code}")
        print(f"   {client.inject_fault('actuator_stuck').code}")
        fault = client.home()
        print(f"   {fault.code:<24} state={fault.state}")
        print("3. Clear the fault and recover")
        client.inject_fault("clear")
        recovered = client.home()
        print(f"   {recovered.code:<24} state={recovered.state}")
    finally:
        process.terminate()
        process.wait(timeout=3)

    report = diagnose(load_events(event_log))
    print("4. Diagnostic summary")
    for key, value in report.items():
        print(f"   {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


