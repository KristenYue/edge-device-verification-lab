"""Native CPU inference; import fails explicitly when native dependencies are absent."""
import os
from pathlib import Path

_dll_handle = os.add_dll_directory(str(Path(__file__).parent)) if os.name == "nt" else None
from ._native import InferenceSession

__all__ = ["InferenceSession"]


def __getattr__(name):
    # Import lazily so async_session can import the native class without a
    # circular dependency during package initialization.
    if name in {
        "AsyncInferenceSession",
        "InferenceRequest",
        "InferenceTimeoutError",
        "QueueFullError",
        "RequestMetrics",
    }:
        from . import async_session

        return getattr(async_session, name)
    raise AttributeError(name)


__all__ += [
    "AsyncInferenceSession",
    "InferenceRequest",
    "InferenceTimeoutError",
    "QueueFullError",
    "RequestMetrics",
]
