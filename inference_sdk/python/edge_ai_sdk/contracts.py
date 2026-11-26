"""Typed model I/O contracts shared by SDK backends.

The native binding remains the final safety boundary.  These Python objects
make the same boundary inspectable before scheduling work, and provide errors
that identify the offending tensor rather than a generic inference failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


_ONNX_TO_NUMPY = {
    1: np.dtype(np.float32),
    2: np.dtype(np.uint8),
    3: np.dtype(np.int8),
    6: np.dtype(np.int32),
    7: np.dtype(np.int64),
    9: np.dtype(np.bool_),
    11: np.dtype(np.float64),
}


@dataclass(frozen=True)
class TensorSpec:
    """One named tensor boundary declared by an ONNX model."""

    name: str
    shape: tuple[int, ...]
    onnx_dtype: int

    @property
    def numpy_dtype(self) -> np.dtype:
        try:
            return _ONNX_TO_NUMPY[self.onnx_dtype]
        except KeyError as exc:
            raise TypeError(
                f"tensor {self.name!r} uses unsupported ONNX dtype {self.onnx_dtype}"
            ) from exc

    @property
    def dynamic_axes(self) -> tuple[int, ...]:
        return tuple(index for index, size in enumerate(self.shape) if size < 0)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TensorSpec":
        return cls(
            name=str(value["name"]),
            shape=tuple(int(size) for size in value["shape"]),
            onnx_dtype=int(value["onnx_dtype"]),
        )

    def validate(self, value: np.ndarray) -> None:
        if not isinstance(value, np.ndarray):
            raise TypeError(f"input {self.name!r} must be a NumPy array")
        if value.dtype != self.numpy_dtype:
            raise TypeError(
                f"input {self.name!r} dtype mismatch: expected "
                f"{self.numpy_dtype}, got {value.dtype}"
            )
        if value.ndim != len(self.shape):
            raise ValueError(
                f"input {self.name!r} rank mismatch: expected "
                f"{len(self.shape)}, got {value.ndim}"
            )
        for axis, (expected, actual) in enumerate(zip(self.shape, value.shape)):
            if expected >= 0 and expected != actual:
                raise ValueError(
                    f"input {self.name!r} dimension {axis} mismatch: "
                    f"expected {expected}, got {actual}"
                )
        if not value.flags.c_contiguous:
            raise ValueError(f"input {self.name!r} must be C contiguous")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "shape": list(self.shape),
            "onnx_dtype": self.onnx_dtype,
            "numpy_dtype": str(self.numpy_dtype),
            "dynamic_axes": list(self.dynamic_axes),
        }


@dataclass(frozen=True)
class ModelContract:
    """Stable SDK view of model inputs, outputs, and runtime metadata."""

    inputs: tuple[TensorSpec, ...]
    outputs: tuple[TensorSpec, ...]
    provider: str
    runtime_version: str

    @classmethod
    def from_model_info(cls, info: Mapping[str, Any]) -> "ModelContract":
        return cls(
            inputs=tuple(TensorSpec.from_dict(item) for item in info["inputs"]),
            outputs=tuple(TensorSpec.from_dict(item) for item in info["outputs"]),
            provider=str(info.get("provider", "unknown")),
            runtime_version=str(info.get("onnxruntime_version", "unknown")),
        )

    def validate_feed(self, feed: Mapping[str, np.ndarray]) -> None:
        if not isinstance(feed, Mapping):
            raise TypeError("feed must be a mapping of input names to NumPy arrays")
        expected = {spec.name for spec in self.inputs}
        actual = {str(name) for name in feed}
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing={missing}")
            if unexpected:
                details.append(f"unexpected={unexpected}")
            raise ValueError("input names mismatch: " + ", ".join(details))
        by_name = {spec.name: spec for spec in self.inputs}
        for name, value in feed.items():
            by_name[str(name)].validate(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "provider": self.provider,
            "runtime_version": self.runtime_version,
        }
