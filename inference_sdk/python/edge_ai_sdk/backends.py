"""Backend interface and the native ONNX Runtime implementation."""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from ._native import InferenceSession
from .contracts import ModelContract


@runtime_checkable
class InferenceBackend(Protocol):
    """Minimal execution boundary required by synchronous and async clients."""

    @property
    def contract(self) -> ModelContract: ...

    def model_info(self) -> dict: ...

    def run(self, feed: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]: ...

    def run_profiled(self, feed: Mapping[str, np.ndarray]) -> dict: ...


class NativeOrtBackend:
    """Checked adapter over the C++/pybind11 ONNX Runtime session."""

    name = "native-onnxruntime"

    def __init__(self, model_path):
        self._session = InferenceSession(str(model_path))
        self._model_info = dict(self._session.model_info())
        self._contract = ModelContract.from_model_info(self._model_info)

    @property
    def contract(self) -> ModelContract:
        return self._contract

    def model_info(self) -> dict:
        result = dict(self._model_info)
        result["backend"] = self.name
        result["contract"] = self._contract.to_dict()
        return result

    def run(self, feed: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
        self._contract.validate_feed(feed)
        return self._session.run(dict(feed))

    def run_profiled(self, feed: Mapping[str, np.ndarray]) -> dict:
        self._contract.validate_feed(feed)
        return self._session.run_profiled(dict(feed))
