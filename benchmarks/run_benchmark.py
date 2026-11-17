"""Fixed-request TCP status baseline against an already running simulator."""

import argparse
import json
import math
import platform
import socket
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4


def request(port, request_id, command, params=None):
    started = time.perf_counter()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
            message = json.dumps({
                "command": command, "request_id": request_id, "params": params or {},
            })
            client.sendall((message + "\n").encode())
            with client.makefile("rb") as stream:
                response = json.loads(stream.readline())
        outcome = "ok" if response.get("ok") else response.get("code", "unknown")
    except (OSError, ValueError):
        outcome = "transport_error"
    return outcome, (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--command", choices=("status", "start_run"), default="status")
    parser.add_argument("--warmup", type=int, default=0)
    args = parser.parse_args()
    if args.clients < 1 or args.requests < 1 or args.warmup < 0:
        parser.error("clients and requests must be positive and warmup nonnegative")
    run_id = uuid4().hex
    if args.command == "start_run":
        for command, params in (
            ("power_on", {}), ("home", {}), ("calibrate", {}),
            ("load_profile", {"name": "benchmark", "sample_count": 100}),
        ):
            outcome, _ = request(args.port, f"{run_id}-{command}", command, params)
            if outcome != "ok":
                parser.error(f"setup {command} failed ({outcome}); start a fresh simulator")
    for index in range(args.warmup):
        outcome, _ = request(args.port, f"{run_id}-warmup-{index}", args.command)
        if outcome != "ok":
            parser.error(f"warmup failed ({outcome})")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        results = list(pool.map(
            lambda i: request(args.port, f"{run_id}-{i}", args.command), range(args.requests),
        ))
    elapsed = time.perf_counter() - started
    counts = Counter(code for code, _ in results)
    latencies = sorted(ms for code, ms in results if code == "ok")
    print(json.dumps({
        "platform": platform.platform(), "clients": args.clients,
        "command": args.command, "warmup": args.warmup,
        "requested": args.requests, "elapsed_seconds": elapsed,
        "successful_requests_per_second": counts["ok"] / elapsed,
        "outcomes": counts,
        "successful_latency_ms": {
            str(p): latencies[math.ceil(len(latencies) * p / 100) - 1] if latencies else None
            for p in (50, 95, 99)
        },
    }, indent=2))
    return 0 if latencies else 1


if __name__ == "__main__":
    raise SystemExit(main())
