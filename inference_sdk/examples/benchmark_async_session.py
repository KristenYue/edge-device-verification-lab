"""Benchmark bounded asynchronous inference and export request-level traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import time

import numpy as np

from edge_ai_sdk import (
    AsyncInferenceSession,
    InferenceSession,
    InferenceTimeoutError,
    QueueFullError,
)

from benchmark_dynamic_int8 import encode_frozen_texts


def percentile(values, quantile):
    return float(np.percentile(np.asarray(values, dtype=np.float64), quantile))


def latency_summary(values):
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def model_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def synchronous_baseline(model: Path, feed, warmup: int, runs: int):
    session = InferenceSession(str(model))
    for _ in range(warmup):
        session.run(feed)
    timings = []
    expected = None
    started = time.perf_counter_ns()
    for _ in range(runs):
        request_started = time.perf_counter_ns()
        expected = session.run(feed)["embeddings"]
        timings.append((time.perf_counter_ns() - request_started) / 1_000_000)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {
        "latency_ms": latency_summary(timings),
        "throughput_requests_per_second": runs * 1000 / elapsed_ms,
        "runs": runs,
    }, expected


def asynchronous_run(model: Path, feed, expected, workers: int, runs: int):
    # Keep every request admissible so this section measures queueing rather
    # than rejection.  Rejection is exercised separately below.
    with AsyncInferenceSession(
        model, max_workers=workers, max_queue=max(0, runs - workers)
    ) as session:
        wall_start = time.perf_counter_ns()
        requests = [session.submit(feed) for _ in range(runs)]
        results = [request.result() for request in requests]
        wall_end = time.perf_counter_ns()

    queue_ms = []
    execution_ms = []
    end_to_end_ms = []
    trace = []
    for request_id, (request, result) in enumerate(zip(requests, results)):
        np.testing.assert_allclose(result["embeddings"], expected, rtol=1e-5, atol=1e-6)
        metrics = request.metrics
        if metrics is None:
            raise AssertionError("completed request lacks timing metrics")
        queue_ms.append(metrics.queue_ms)
        execution_ms.append(metrics.execution_ms)
        end_to_end_ms.append(metrics.queue_ms + metrics.execution_ms)
        trace.extend(
            [
                {
                    "request_id": request_id,
                    "event": "submitted",
                    "at_ms": (metrics.submitted_ns - wall_start) / 1_000_000,
                },
                {
                    "request_id": request_id,
                    "event": "started",
                    "at_ms": (metrics.started_ns - wall_start) / 1_000_000,
                },
                {
                    "request_id": request_id,
                    "event": "completed",
                    "at_ms": (metrics.completed_ns - wall_start) / 1_000_000,
                },
            ]
        )
    elapsed_ms = (wall_end - wall_start) / 1_000_000
    return {
        "workers": workers,
        "runs": runs,
        "wall_time_ms": elapsed_ms,
        "throughput_requests_per_second": runs * 1000 / elapsed_ms,
        "queue_ms": latency_summary(queue_ms),
        "execution_ms": latency_summary(execution_ms),
        "end_to_end_ms": latency_summary(end_to_end_ms),
        "trace": trace,
    }


def bounded_failure_evidence(model: Path, feed):
    evidence = {
        "queue_full": False,
        "queued_cancellation": False,
        "deadline_timeout": False,
        "deadline_message": None,
    }
    with AsyncInferenceSession(model, max_workers=1, max_queue=1) as session:
        first = session.submit(feed)
        second = session.submit(feed)
        try:
            session.submit(feed)
        except QueueFullError:
            evidence["queue_full"] = True
        evidence["queued_cancellation"] = second.cancel()
        first.result()

        timed = session.submit(feed, deadline_ms=0.1)
        try:
            timed.result()
        except InferenceTimeoutError as exc:
            evidence["deadline_timeout"] = True
            evidence["deadline_message"] = str(exc)
    if not all(
        evidence[name]
        for name in ("queue_full", "queued_cancellation", "deadline_timeout")
    ):
        raise AssertionError(f"bounded failure evidence incomplete: {evidence}")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", default="1,2,4")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=24)
    args = parser.parse_args()
    workers = [int(item) for item in args.workers.split(",")]
    if any(item < 1 for item in workers) or args.warmup < 0 or args.runs < 3:
        parser.error("workers must be >=1, warmup >=0, and runs >=3")

    feed = encode_frozen_texts(args.vocab)
    baseline, expected = synchronous_baseline(
        args.model, feed, args.warmup, args.runs
    )
    configurations = [
        asynchronous_run(args.model, feed, expected, count, args.runs)
        for count in workers
    ]
    result = {
        "schema_version": 1,
        "experiment": "bounded_async_inference",
        "platform": platform.platform(),
        "provider": "CPUExecutionProvider",
        "model_file": args.model.name,
        "model_sha256": model_sha256(args.model),
        "batch": int(feed["input_ids"].shape[0]),
        "sequence_length": int(feed["input_ids"].shape[1]),
        "input_ownership": "copied_at_submit",
        "timing_scope": {
            "queue_ms": "submit API entry through native execution start; includes input copy",
            "execution_ms": "native session run",
            "throughput": "submit calls, queueing, native execution and result collection",
        },
        "synchronous_baseline": baseline,
        "async_configurations": configurations,
        "bounded_failure_evidence": bounded_failure_evidence(args.model, feed),
        "limitations": [
            "single process and one shared ONNX Runtime session",
            "CPU only; no GPU stream or device overlap claim",
            "identical frozen requests; not a production traffic distribution",
            "deadline cannot preempt an in-flight ONNX Runtime call",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "baseline_rps": baseline["throughput_requests_per_second"],
                "async": [
                    {
                        "workers": item["workers"],
                        "rps": item["throughput_requests_per_second"],
                        "p95_ms": item["end_to_end_ms"]["p95"],
                    }
                    for item in configurations
                ],
                "failures": result["bounded_failure_evidence"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
