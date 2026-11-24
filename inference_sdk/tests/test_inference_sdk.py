from __future__ import annotations

import threading
import time

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper

from edge_ai_sdk import InferenceSession
from edge_ai_sdk.async_session import (
    AsyncInferenceSession,
    InferenceTimeoutError,
    QueueFullError,
)


def _write_multi_io_model(path):
    graph = helper.make_graph(
        [
            helper.make_node("Add", ["left", "right"], ["sum"]),
            helper.make_node(
                "ArgMax", ["sum"], ["argmax"], axis=1, keepdims=0
            ),
        ],
        "dynamic_multi_io",
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


def test_dynamic_multi_input_multi_output_and_metadata(tmp_path):
    model_path = tmp_path / "multi_io.onnx"
    _write_multi_io_model(model_path)
    session = InferenceSession(str(model_path))

    info = session.model_info()
    assert [item["name"] for item in info["inputs"]] == ["left", "right"]
    assert [item["shape"] for item in info["inputs"]] == [[-1, 4], [-1, 4]]
    assert [item["name"] for item in info["outputs"]] == ["sum", "argmax"]
    assert [item["onnx_dtype"] for item in info["outputs"]] == [1, 7]

    left = np.arange(12, dtype=np.float32).reshape(3, 4)
    right = np.ones((3, 4), dtype=np.float32)
    outputs = session.run({"left": left, "right": right})
    np.testing.assert_array_equal(outputs["sum"], left + right)
    np.testing.assert_array_equal(outputs["argmax"], np.array([3, 3, 3]))
    assert outputs["sum"].dtype == np.float32
    assert outputs["argmax"].dtype == np.int64

    profiled = session.run_profiled({"left": left, "right": right})
    np.testing.assert_array_equal(profiled["outputs"]["sum"], left + right)
    assert set(profiled["trace"]) == {
        "input_binding_us",
        "ort_run_us",
        "output_copy_us",
        "total_us",
    }
    assert all(value >= 0 for value in profiled["trace"].values())
    phase_total = sum(
        profiled["trace"][name]
        for name in ("input_binding_us", "ort_run_us", "output_copy_us")
    )
    assert profiled["trace"]["total_us"] == pytest.approx(phase_total)

    with pytest.raises(ValueError, match="names/count"):
        session.run({"left": left})
    with pytest.raises(ValueError, match="dimension"):
        session.run(
            {
                "left": np.ones((3, 3), dtype=np.float32),
                "right": np.ones((3, 3), dtype=np.float32),
            }
        )


class _BlockingSession:
    """Deterministic unit-test double for queue and ownership semantics."""

    entered = threading.Event()
    release = threading.Event()

    def __init__(self, _):
        type(self).entered.clear()
        type(self).release.clear()

    def model_info(self):
        return {"inputs": [], "outputs": [], "provider": "test"}

    def run(self, feed):
        type(self).entered.set()
        assert type(self).release.wait(timeout=2)
        return {"output": feed["input"].copy()}


def test_async_queue_is_bounded_and_owns_inputs(monkeypatch):
    import edge_ai_sdk.async_session as async_module

    monkeypatch.setattr(async_module, "InferenceSession", _BlockingSession)
    session = async_module.AsyncInferenceSession("unused", max_workers=1, max_queue=1)
    first_input = np.array([1.0], dtype=np.float32)
    first = session.submit({"input": first_input})
    assert _BlockingSession.entered.wait(timeout=1)
    second_input = np.array([2.0], dtype=np.float32)
    second = session.submit({"input": second_input})
    first_input[0] = 99
    second_input[0] = 99

    with pytest.raises(QueueFullError):
        session.submit({"input": np.array([3.0], dtype=np.float32)})

    assert second.cancel()
    _BlockingSession.release.set()
    np.testing.assert_array_equal(first.result(timeout=1)["output"], [1.0])
    assert second.cancelled()
    session.close()


class _SlowSession:
    def __init__(self, _):
        pass

    def model_info(self):
        return {"inputs": [], "outputs": [], "provider": "test"}

    def run(self, feed):
        time.sleep(0.03)
        return {"output": feed["input"]}


def test_async_deadline_discards_late_result(monkeypatch):
    import edge_ai_sdk.async_session as async_module

    monkeypatch.setattr(async_module, "InferenceSession", _SlowSession)
    with AsyncInferenceSession("unused", max_workers=1, max_queue=0) as session:
        request = session.submit(
            {"input": np.array([1.0], dtype=np.float32)}, deadline_ms=5
        )
        with pytest.raises(InferenceTimeoutError, match="during inference"):
            request.result(timeout=1)
        assert request.metrics is not None
        assert request.metrics.execution_ms >= 5
