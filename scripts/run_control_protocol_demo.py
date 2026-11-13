from __future__ import annotations

import argparse
import os
import socket
import subprocess
import time
from pathlib import Path

from edge_validation.client import DeviceClient
from edge_validation.control_protocol import DeviceControlHost
from edge_validation.models import TaskProfile


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the device-control demo")
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
    event_log = args.artifacts / "control-protocol-demo-events.jsonl"
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

        host = DeviceControlHost(client)
        print("[1/6] DeviceRuntime status       OFFLINE / LOCAL")
        online = host.establish_communications()
        print(f"[2/6] CONNECT -> {online.code:<24} ONLINE / LOCAL")
        remote = host.set_remote()
        print(f"[3/6] Control -> {remote.code:<24} ONLINE / REMOTE")

        client.power_on()
        client.home()
        client.calibrate()
        profile = TaskProfile(name="DEMO-01", sample_count=64, noise_sigma=0.01, drift_limit=0.2)
        selected = host.select_profile(profile)
        print(f"[4/6] REMOTE_COMMAND PROFILE -> {selected.code:<18} profile=DEMO-01")
        first = host.start(request_id="demo-start-1")
        duplicate = host.start(request_id="demo-start-1")
        print(
            f"[5/6] REMOTE_COMMAND START  -> {first.code:<18} "
            f"run={first.data['run_id']}"
        )
        print(
            "      duplicate replay -> "
            f"same_sequence={first.sequence == duplicate.sequence}, run_count=1"
        )

        client.inject_fault("interlock_open")
        alarms = host.alarms()
        print(f"[6/6] alarm report       count={alarms.count} {', '.join(alarms.alarms)}")
        print("      evidence              artifacts/control-protocol-demo-events.jsonl")
    finally:
        process.terminate()
        process.wait(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





