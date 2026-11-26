"""Reference graph verifies the SDK ABI; not a pretrained semantic model."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper, numpy_helper
from edge_ai_sdk import NativeOrtBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output).parent
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "reference.onnx"
    weights = np.arange(12, dtype=np.float32).reshape(4, 3)/12
    graph = helper.make_graph(
        [helper.make_node("MatMul", ["input", "weights"], ["output"])],
        "reference_projection",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["batch", 4])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, ["batch", 3])],
        [numpy_helper.from_array(weights, "weights")])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    onnx.checker.check_model(model)
    onnx.save(model, model_path)
    native = NativeOrtBackend(model_path)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    reference = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
    feed = {"input": np.arange(8, dtype=np.float32).reshape(2, 4)}
    expected = reference.run(None, feed)[0]
    result = native.run(feed)["output"]
    np.testing.assert_allclose(result, expected, rtol=1e-5, atol=1e-6)
    failures = []
    for label, value in [("dtype", feed["input"].astype(np.float64)),
                         ("shape", np.ones((2, 5), dtype=np.float32)),
                         ("stride", np.ones((2, 8), dtype=np.float32)[:, ::2])]:
        try:
            native.run({"input": value})
        except (TypeError, ValueError):
            failures.append(label)
        else:
            raise AssertionError(f"invalid {label} accepted")
    for _ in range(10):
        native.run(feed)
    timings = []
    for _ in range(100):
        start = time.perf_counter_ns()
        native.run(feed)
        timings.append((time.perf_counter_ns()-start)/1e6)
    backend_name = native.name
    contract = native.contract.to_dict()
    del native
    assert np.isfinite(result).all()  # Python output owns memory independently.
    report = {"schema_version": 2, "sdk_version": "0.3.0",
              "platform": platform.platform(),
              "model_kind": "generated_reference_graph_not_pretrained",
              "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
              "max_abs_error": float(np.max(np.abs(result-expected))), "rejected": failures,
              "runs": 100, "warmup": 10, "batch": 2,
              "native_p50_ms": float(np.percentile(timings, 50)),
              "native_p95_ms": float(np.percentile(timings, 95)),
              "python_ort_version": ort.__version__,
              "backend": backend_name, "contract": contract}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
