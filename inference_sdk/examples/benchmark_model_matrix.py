"""Cross-workload native SDK benchmark with Python ORT correctness baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper

from edge_ai_sdk import InferenceSession
from benchmark_dynamic_int8 import encode_frozen_texts


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def latency(values):
    return {
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }


def median(values):
    return float(np.median(np.asarray(values, dtype=np.float64)))


def aggregate_trials(trials):
    report = dict(trials[0])
    report["trial_count"] = len(trials)
    report["native_latency_ms"] = {
        quantile: median([item["native_latency_ms"][quantile] for item in trials])
        for quantile in ("p50", "p95", "p99")
    }
    report["python_ort_latency_ms"] = {
        quantile: median([item["python_ort_latency_ms"][quantile] for item in trials])
        for quantile in ("p50", "p95", "p99")
    }
    report["native_throughput_items_per_second"] = median(
        [item["native_throughput_items_per_second"] for item in trials]
    )
    report["native_phase_us"] = {
        phase: {
            quantile: median(
                [item["native_phase_us"][phase][quantile] for item in trials]
            )
            for quantile in ("p50", "p95", "p99")
        }
        for phase in ("input_binding", "ort_run", "output_copy", "total")
    }
    report["trials"] = [
        {
            "native_latency_ms": item["native_latency_ms"],
            "python_ort_latency_ms": item["python_ort_latency_ms"],
            "native_throughput_items_per_second": item[
                "native_throughput_items_per_second"
            ],
            "native_phase_us": item["native_phase_us"],
        }
        for item in trials
    ]
    return report


def create_reference_model(path: Path):
    graph = helper.make_graph(
        [
            helper.make_node("Add", ["left", "right"], ["sum"]),
            helper.make_node("ArgMax", ["sum"], ["argmax"], axis=1, keepdims=0),
        ],
        "dynamic_multi_io_reference",
        [
            helper.make_tensor_value_info("left", TensorProto.FLOAT, ["batch", 4]),
            helper.make_tensor_value_info("right", TensorProto.FLOAT, ["batch", 4]),
        ],
        [
            helper.make_tensor_value_info("sum", TensorProto.FLOAT, ["batch", 4]),
            helper.make_tensor_value_info("argmax", TensorProto.INT64, ["batch"]),
        ],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9
    )
    onnx.checker.check_model(model)
    onnx.save(model, path)


def make_feed(kind: str, batch: int, vocab: Path | None):
    if kind == "bge":
        if vocab is None:
            raise ValueError("BGE workload requires --vocab")
        frozen = encode_frozen_texts(vocab)
        repeats = (batch + frozen["input_ids"].shape[0] - 1) // frozen["input_ids"].shape[0]
        return {
            name: np.tile(value, (repeats, 1))[:batch].copy()
            for name, value in frozen.items()
        }
    if kind == "mobilenet":
        rng = np.random.default_rng(20261124 + batch)
        return {
            "input": rng.normal(0, 1, size=(batch, 3, 224, 224)).astype(np.float32)
        }
    if kind == "reference":
        left = np.arange(batch * 4, dtype=np.float32).reshape(batch, 4)
        return {"left": left, "right": np.ones_like(left)}
    raise ValueError(f"unknown workload kind: {kind}")


def run_worker(args) -> int:
    feed = make_feed(args.kind, args.batch, args.vocab)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    reference = ort.InferenceSession(
        str(args.worker_model), options, providers=["CPUExecutionProvider"]
    )
    expected_values = reference.run(None, feed)
    expected = {
        item.name: value for item, value in zip(reference.get_outputs(), expected_values)
    }

    native = InferenceSession(str(args.worker_model))
    for _ in range(args.warmup):
        native.run(feed)
        reference.run(None, feed)

    native_times = []
    python_times = []
    phase_times = {
        "input_binding": [],
        "ort_run": [],
        "output_copy": [],
        "total": [],
    }
    actual = None
    for _ in range(args.runs):
        start = time.perf_counter_ns()
        profiled = native.run_profiled(feed)
        actual = profiled["outputs"]
        native_times.append((time.perf_counter_ns() - start) / 1_000_000)
        phase_times["input_binding"].append(profiled["trace"]["input_binding_us"])
        phase_times["ort_run"].append(profiled["trace"]["ort_run_us"])
        phase_times["output_copy"].append(profiled["trace"]["output_copy_us"])
        phase_times["total"].append(profiled["trace"]["total_us"])
        start = time.perf_counter_ns()
        reference.run(None, feed)
        python_times.append((time.perf_counter_ns() - start) / 1_000_000)
    assert actual is not None

    comparisons = {}
    for name, expected_value in expected.items():
        actual_value = actual[name]
        if np.issubdtype(expected_value.dtype, np.floating):
            difference = np.abs(actual_value - expected_value)
            comparisons[name] = {
                "max_abs_error": float(np.max(difference)),
                "mean_abs_error": float(np.mean(difference)),
                "allclose": bool(
                    np.allclose(actual_value, expected_value, rtol=1e-5, atol=1e-6)
                ),
            }
        else:
            comparisons[name] = {
                "exact_match": bool(np.array_equal(actual_value, expected_value))
            }
        comparisons[name]["shape"] = list(actual_value.shape)
        comparisons[name]["dtype"] = str(actual_value.dtype)

    native_p50 = float(np.percentile(native_times, 50))
    report = {
        "workload": args.kind,
        "model_file": args.worker_model.name,
        "model_sha256": digest(args.worker_model),
        "model_bytes": args.worker_model.stat().st_size,
        "batch": args.batch,
        "runs": args.runs,
        "warmup": args.warmup,
        "native_latency_ms": latency(native_times),
        "python_ort_latency_ms": latency(python_times),
        "python_ort_version": ort.__version__,
        "native_throughput_items_per_second": args.batch * 1000 / native_p50,
        "native_phase_us": {
            name: latency(values) for name, values in phase_times.items()
        },
        "outputs": comparisons,
        "model_info": native.model_info(),
    }
    args.worker_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bge-model", type=Path)
    parser.add_argument("--mobilenet-model", type=Path)
    parser.add_argument("--vocab", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--worker-model", type=Path)
    parser.add_argument("--worker-output", type=Path)
    parser.add_argument("--kind", choices=("bge", "mobilenet", "reference"))
    parser.add_argument("--batch", type=int)
    args = parser.parse_args()

    if args.worker_model is not None:
        return run_worker(args)
    if not all((args.bge_model, args.mobilenet_model, args.vocab, args.output)):
        parser.error("BGE, MobileNet, vocab and output paths are required")
    if args.warmup < 0 or args.runs < 1 or args.trials < 1:
        parser.error("warmup must be >=0; runs and trials must be >=1")

    configurations = [
        ("bge", args.bge_model, 1),
        ("bge", args.bge_model, 4),
        ("bge", args.bge_model, 12),
        ("mobilenet", args.mobilenet_model, 1),
        ("mobilenet", args.mobilenet_model, 4),
    ]
    reports = []
    with tempfile.TemporaryDirectory(prefix="edge-ai-matrix-") as directory:
        temporary = Path(directory)
        reference_model = temporary / "dynamic-multi-io.onnx"
        create_reference_model(reference_model)
        configurations.append(("reference", reference_model, 3))
        for index, (kind, model, batch) in enumerate(configurations):
            trial_reports = []
            for trial in range(args.trials):
                worker_output = temporary / f"report-{index}-{trial}.json"
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker-model", str(model.resolve()),
                    "--worker-output", str(worker_output.resolve()),
                    "--kind", kind,
                    "--batch", str(batch),
                    "--warmup", str(args.warmup),
                    "--runs", str(args.runs),
                ]
                if kind == "bge":
                    command.extend(["--vocab", str(args.vocab.resolve())])
                subprocess.run(command, check=True)
                trial_reports.append(
                    json.loads(worker_output.read_text(encoding="utf-8"))
                )
            report = aggregate_trials(trial_reports)
            if kind == "reference":
                report["model_file"] = "generated_dynamic_multi_io_reference.onnx"
                report["performance_interpretation"] = "interface correctness only"
            reports.append(report)

    result = {
        "schema_version": 1,
        "experiment": "native_sdk_cross_workload_matrix",
        "provider": "CPUExecutionProvider",
        "threads": {"intra_op": 1, "inter_op": 1},
        "timing_scope": "model execution only; excludes tokenization and input generation",
        "workloads": reports,
        "interpretation": [
            "BGE and MobileNet are pretrained real models",
            "the generated multi-input/output graph validates SDK contracts only",
            "latencies are local Windows CPU evidence, not target-device claims",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            [
                {
                    "workload": item["workload"],
                    "batch": item["batch"],
                    "p50_ms": item["native_latency_ms"]["p50"],
                    "throughput": item["native_throughput_items_per_second"],
                }
                for item in reports
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
