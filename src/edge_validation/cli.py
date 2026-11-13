from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import DeviceClient
from .diagnostics import diagnose, load_events, write_diagnostic_report
from .models import TaskProfile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and diagnose the virtual edge-device runtime"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("status")
    demo = subparsers.add_parser("demo")
    demo.add_argument("--profile", default="batch-demo")
    demo.add_argument("--samples", type=int, default=128)

    diag = subparsers.add_parser("diagnose")
    diag.add_argument("event_log", type=Path)
    diag.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.action == "diagnose":
        events = load_events(args.event_log)
        if args.output:
            write_diagnostic_report(events, args.output)
        print(json.dumps(diagnose(events), indent=2))
        return 0

    client = DeviceClient(args.host, args.port)
    if args.action == "status":
        print(client.status().model_dump_json(indent=2))
        return 0

    responses = [
        client.power_on(),
        client.home(),
        client.calibrate(),
        client.load_profile(
            TaskProfile(
                name=args.profile,
                sample_count=args.samples,
                noise_sigma=0.02,
                drift_limit=0.2,
            )
        ),
        client.start_run(),
    ]
    for response in responses:
        print(response.model_dump_json())
    return 0 if all(response.ok for response in responses) else 1


if __name__ == "__main__":
    raise SystemExit(main())

