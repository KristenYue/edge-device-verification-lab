"""Reproducible FP32 vs dynamic-INT8 CPU experiment for the local BGE model.

This is framework-provided weight quantization through ONNX Runtime, not a
custom quantizer or kernel.  The frozen retrieval set is a smoke metric for
regression detection, not a substitute for a production evaluation corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


DOCUMENTS = [
    "车辆轮胎压力异常需要检查传感器",
    "模型量化可以减少模型文件大小",
    "进程心跳超时后执行受控重启",
    "通信系统需要分析带宽时延和可靠性",
    "嵌入式系统通过串口连接外部设备",
    "推理服务使用队列限制并发请求",
    "编码交织能够抵抗连续突发错误",
    "日志追踪用于定位性能瓶颈",
]
QUERIES = [
    "如何处理轮胎压力故障",
    "如何减小推理模型体积",
    "进程失去心跳应该怎么办",
    "怎样定位系统性能问题",
]
RELEVANT_DOCUMENT = np.array([0, 1, 2, 7], dtype=np.int64)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_memory_bytes() -> tuple[int | None, int | None]:
    """Return current RSS and peak RSS without an extra runtime dependency."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if not ok:
            return None, None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)

    status = Path("/proc/self/status")
    if status.exists():
        values = {}
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, value, _unit = line.split()
                values[key.rstrip(":")] = int(value) * 1024
        return values.get("VmRSS"), values.get("VmHWM")
    return None, None


def encode_frozen_texts(vocab_path: Path, max_length: int = 48) -> dict[str, np.ndarray]:
    vocab = {
        token: index
        for index, token in enumerate(vocab_path.read_text(encoding="utf-8").splitlines())
    }
    required = ("[PAD]", "[UNK]", "[CLS]", "[SEP]")
    if not all(token in vocab for token in required):
        raise ValueError("tokenizer vocabulary lacks required BERT special tokens")

    rows = []
    masks = []
    for text in DOCUMENTS + QUERIES:
        tokens = ["[CLS]"] + [char for char in text if not char.isspace()] + ["[SEP]"]
        ids = [vocab.get(token, vocab["[UNK]"]) for token in tokens[:max_length]]
        mask = [1] * len(ids)
        padding = max_length - len(ids)
        rows.append(ids + [vocab["[PAD]"]] * padding)
        masks.append(mask + [0] * padding)
    input_ids = np.asarray(rows, dtype=np.int64)
    return {
        "input_ids": input_ids,
        "attention_mask": np.asarray(masks, dtype=np.int64),
        "token_type_ids": np.zeros_like(input_ids),
    }


def retrieval_recall(embeddings: np.ndarray) -> tuple[float, list[int]]:
    documents = embeddings[: len(DOCUMENTS)]
    queries = embeddings[len(DOCUMENTS) :]
    documents = documents / np.maximum(np.linalg.norm(documents, axis=1, keepdims=True), 1e-12)
    queries = queries / np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
    selected = np.argmax(queries @ documents.T, axis=1)
    return float(np.mean(selected == RELEVANT_DOCUMENT)), selected.astype(int).tolist()


def worker(args) -> int:
    from edge_ai_sdk import InferenceSession

    feed = encode_frozen_texts(args.vocab)
    rss_before, _ = process_memory_bytes()
    session = InferenceSession(str(args.worker_model))
    for _ in range(args.warmup):
        session.run(feed)
    timings = []
    output = None
    for _ in range(args.runs):
        start = time.perf_counter_ns()
        output = session.run(feed)["embeddings"]
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    assert output is not None
    rss_after, peak_rss = process_memory_bytes()
    recall, selected = retrieval_recall(output)
    np.save(args.worker_embeddings, output)
    report = {
        "model_file": args.worker_model.name,
        "model_sha256": sha256(args.worker_model),
        "model_bytes": args.worker_model.stat().st_size,
        "batch": len(DOCUMENTS) + len(QUERIES),
        "sequence_length": int(feed["input_ids"].shape[1]),
        "warmup": args.warmup,
        "runs": args.runs,
        "latency_ms": {
            "p50": float(np.percentile(timings, 50)),
            "p95": float(np.percentile(timings, 95)),
            "p99": float(np.percentile(timings, 99)),
        },
        "throughput_items_per_second": float(
            len(DOCUMENTS + QUERIES) * 1000 / np.percentile(timings, 50)
        ),
        "rss_before_session_bytes": rss_before,
        "rss_after_benchmark_bytes": rss_after,
        "peak_rss_bytes": peak_rss,
        "retrieval_smoke_recall_at_1": recall,
        "retrieval_selected_documents": selected,
    }
    args.worker_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path)
    parser.add_argument("--vocab", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quantized-model", type=Path)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--worker-model", type=Path)
    parser.add_argument("--worker-output", type=Path)
    parser.add_argument("--worker-embeddings", type=Path)
    args = parser.parse_args()

    if args.worker_model is not None:
        return worker(args)
    if not all((args.model, args.vocab, args.output, args.quantized_model)):
        parser.error("--model, --vocab, --output and --quantized-model are required")
    if args.warmup < 0 or args.runs < 1:
        parser.error("warmup must be >= 0 and runs must be >= 1")

    from onnxruntime.quantization import QuantType, quantize_dynamic

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.quantized_model.parent.mkdir(parents=True, exist_ok=True)
    quantize_dynamic(
        args.model,
        args.quantized_model,
        weight_type=QuantType.QInt8,
    )

    reports = {}
    embeddings = {}
    for label, model in (("fp32", args.model), ("dynamic_int8", args.quantized_model)):
        report_path = args.output.parent / f".{args.output.stem}-{label}.json"
        embeddings_path = args.output.parent / f".{args.output.stem}-{label}.npy"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker-model", str(model.resolve()),
            "--worker-output", str(report_path.resolve()),
            "--worker-embeddings", str(embeddings_path.resolve()),
            "--vocab", str(args.vocab.resolve()),
            "--warmup", str(args.warmup),
            "--runs", str(args.runs),
        ]
        subprocess.run(command, check=True)
        reports[label] = json.loads(report_path.read_text(encoding="utf-8"))
        embeddings[label] = np.load(embeddings_path)
        report_path.unlink()
        embeddings_path.unlink()

    fp32 = embeddings["fp32"]
    int8 = embeddings["dynamic_int8"]
    cosine = np.sum(fp32 * int8, axis=1) / np.maximum(
        np.linalg.norm(fp32, axis=1) * np.linalg.norm(int8, axis=1), 1e-12
    )
    result = {
        "schema_version": 1,
        "experiment": "onnxruntime_dynamic_int8_weight_quantization",
        "scope": "CPUExecutionProvider; framework quantization, not custom kernels",
        "static_quantization": {
            "performed": False,
            "reason": "activation calibration requires a representative task corpus; this milestone uses weight-only dynamic quantization for the Transformer encoder",
        },
        "dataset": {
            "kind": "frozen_small_retrieval_smoke_set",
            "documents": len(DOCUMENTS),
            "queries": len(QUERIES),
            "limitation": "regression smoke metric, not production retrieval accuracy",
        },
        "fp32": reports["fp32"],
        "dynamic_int8": reports["dynamic_int8"],
        "comparison": {
            "model_size_reduction_ratio": 1
            - reports["dynamic_int8"]["model_bytes"] / reports["fp32"]["model_bytes"],
            "p50_speedup_ratio": reports["fp32"]["latency_ms"]["p50"]
            / reports["dynamic_int8"]["latency_ms"]["p50"],
            "throughput_ratio": reports["dynamic_int8"]["throughput_items_per_second"]
            / reports["fp32"]["throughput_items_per_second"],
            "max_abs_error": float(np.max(np.abs(fp32 - int8))),
            "mean_abs_error": float(np.mean(np.abs(fp32 - int8))),
            "mean_cosine_similarity": float(np.mean(cosine)),
            "min_cosine_similarity": float(np.min(cosine)),
        },
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["comparison"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
