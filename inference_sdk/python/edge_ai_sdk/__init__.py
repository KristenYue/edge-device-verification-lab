"""Native CPU inference; import fails explicitly when native dependencies are absent."""
import os
from pathlib import Path

_dll_handle = os.add_dll_directory(str(Path(__file__).parent)) if os.name == "nt" else None
from ._native import InferenceSession

__all__ = ["InferenceSession"]
