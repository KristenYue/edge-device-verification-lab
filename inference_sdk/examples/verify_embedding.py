"""Compare pretrained encoder Python ORT/native outputs and record measured latency."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
from edge_ai_sdk import InferenceSession


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    reference = ort.InferenceSession(args.model, options, providers=["CPUExecutionProvider"])
    native = InferenceSession(args.model)
    texts = ["设备急停联锁触发，无法启动", "机器人巡检任务取消", "库存低于安全阈值"]
    batch = tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors="np")
    feed = {x.name: np.ascontiguousarray(batch[x.name], dtype=np.int64) for x in reference.get_inputs()}
    expected = reference.run(None, feed)[0]
    actual = native.run(feed)["embeddings"]
    np.testing.assert_allclose(actual, expected, atol=1e-5, rtol=1e-4)
    latency = {}
    for name, call in [("native", lambda: native.run(feed)), ("python_ort", lambda: reference.run(None, feed))]:
        for _ in range(5):
            call()
        timings = []
        for _ in range(30):
            start = time.perf_counter_ns()
            call()
            timings.append((time.perf_counter_ns()-start)/1e6)
        latency[name] = {"p50_ms": float(np.percentile(timings,50)), "p95_ms": float(np.percentile(timings,95))}
    report = {"platform": platform.platform(), "model": "BAAI/bge-small-zh-v1.5",
              "model_sha256": hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
              "input_shape": list(feed["input_ids"].shape), "output_shape": list(actual.shape),
              "max_abs_error": float(np.max(np.abs(actual-expected))), "latency": latency,
              "warmup": 5, "runs": 30, "threads": 1, "includes_tokenization": False,
              "provider": "CPUExecutionProvider", "python_ort_version": ort.__version__,
              "native_ort_version": "1.22.0"}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
