"""Bounded asynchronous requests around the native inference session.

The native ``run`` call releases the GIL.  This layer owns submitted input
buffers, limits queued work, and gives queue/deadline failures distinct types.
It deliberately does not claim to interrupt an ONNX Runtime call already in
progress: an expired in-flight result is computed and then discarded.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import threading
import time
from typing import Mapping

import numpy as np

from .backends import InferenceBackend, NativeOrtBackend


class QueueFullError(RuntimeError):
    """The configured worker and queue capacity is exhausted."""


class InferenceTimeoutError(TimeoutError):
    """The request deadline expired before a result could be returned."""


@dataclass(frozen=True)
class RequestMetrics:
    submitted_ns: int
    started_ns: int
    completed_ns: int

    @property
    def queue_ms(self) -> float:
        return (self.started_ns - self.submitted_ns) / 1_000_000

    @property
    def execution_ms(self) -> float:
        return (self.completed_ns - self.started_ns) / 1_000_000

    @property
    def end_to_end_ms(self) -> float:
        return (self.completed_ns - self.submitted_ns) / 1_000_000


@dataclass(frozen=True)
class SessionStats:
    """Point-in-time request counters for admission and terminal outcomes."""

    admitted: int
    rejected: int
    completed: int
    cancelled: int
    timed_out: int
    failed: int

    @property
    def in_flight(self) -> int:
        terminal = self.completed + self.cancelled + self.timed_out + self.failed
        return self.admitted - terminal


class InferenceRequest:
    """Handle for one request, including timing once execution completes."""

    def __init__(self, future: Future, timing: dict[str, int]):
        self._future = future
        self._timing = timing

    def cancel(self) -> bool:
        """Cancel only if the request has not begun native execution."""
        return self._future.cancel()

    def cancelled(self) -> bool:
        return self._future.cancelled()

    def done(self) -> bool:
        return self._future.done()

    def result(self, timeout: float | None = None):
        return self._future.result(timeout=timeout)

    @property
    def metrics(self) -> RequestMetrics | None:
        required = ("submitted_ns", "started_ns", "completed_ns")
        if not all(name in self._timing for name in required):
            return None
        return RequestMetrics(*(self._timing[name] for name in required))


class AsyncInferenceSession:
    """A bounded thread-pool facade over :class:`InferenceSession`.

    ``max_queue`` counts requests waiting behind active workers.  Inputs are
    copied at submission so callers may safely reuse or mutate their arrays.
    A deadline covers queueing and execution.  ONNX Runtime calls already in
    progress cannot be preempted; if the deadline expires, their output is
    discarded and ``InferenceTimeoutError`` is reported.
    """

    def __init__(
        self,
        model_path=None,
        *,
        backend: InferenceBackend | None = None,
        max_workers: int = 1,
        max_queue: int = 8,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if max_queue < 0:
            raise ValueError("max_queue must be >= 0")
        if backend is not None and model_path is not None:
            raise ValueError("provide model_path or backend, not both")
        if backend is None:
            if model_path is None:
                raise ValueError("model_path is required when backend is not provided")
            backend = NativeOrtBackend(model_path)
        self._backend = backend
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="edge-ai-inference"
        )
        self._capacity = threading.BoundedSemaphore(max_workers + max_queue)
        self._closed = False
        self._state_lock = threading.Lock()
        self._stats = {
            "admitted": 0,
            "rejected": 0,
            "completed": 0,
            "cancelled": 0,
            "timed_out": 0,
            "failed": 0,
        }

    def model_info(self):
        return self._backend.model_info()

    @property
    def contract(self):
        return self._backend.contract

    def stats(self) -> SessionStats:
        with self._state_lock:
            return SessionStats(**self._stats)

    def submit(
        self,
        feed: Mapping[str, np.ndarray],
        *,
        deadline_ms: float | None = None,
        enqueue_timeout_ms: float = 0,
    ) -> InferenceRequest:
        if deadline_ms is not None and deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")
        if enqueue_timeout_ms < 0:
            raise ValueError("enqueue_timeout_ms must be >= 0")
        with self._state_lock:
            if self._closed:
                raise RuntimeError("session is closed")

        timing = {"submitted_ns": time.perf_counter_ns()}
        deadline_ns = (
            timing["submitted_ns"] + int(deadline_ms * 1_000_000)
            if deadline_ms is not None
            else None
        )
        admission_timeout = enqueue_timeout_ms / 1000
        if deadline_ns is not None:
            admission_timeout = min(admission_timeout, deadline_ms / 1000)
        acquired = self._capacity.acquire(timeout=admission_timeout)
        if not acquired:
            with self._state_lock:
                self._stats["rejected"] += 1
            raise QueueFullError("inference queue capacity exhausted")

        try:
            owned_feed = {}
            for name, value in feed.items():
                if not isinstance(value, np.ndarray):
                    raise TypeError("feed values must be NumPy arrays")
                owned_feed[str(name)] = np.ascontiguousarray(value).copy()
            self._backend.contract.validate_feed(owned_feed)
        except Exception:
            self._capacity.release()
            raise

        with self._state_lock:
            self._stats["admitted"] += 1

        def execute():
            timing["started_ns"] = time.perf_counter_ns()
            if deadline_ns is not None and timing["started_ns"] >= deadline_ns:
                timing["completed_ns"] = timing["started_ns"]
                raise InferenceTimeoutError("deadline expired while queued")
            result = self._backend.run(owned_feed)
            timing["completed_ns"] = time.perf_counter_ns()
            if deadline_ns is not None and timing["completed_ns"] >= deadline_ns:
                raise InferenceTimeoutError(
                    "deadline expired during inference; result discarded"
                )
            return result

        try:
            future = self._executor.submit(execute)
        except Exception:
            self._capacity.release()
            with self._state_lock:
                self._stats["failed"] += 1
            raise

        def on_done(done: Future):
            self._capacity.release()
            if done.cancelled():
                outcome = "cancelled"
            else:
                exception = done.exception()
                if isinstance(exception, InferenceTimeoutError):
                    outcome = "timed_out"
                elif exception is not None:
                    outcome = "failed"
                else:
                    outcome = "completed"
            with self._state_lock:
                self._stats[outcome] += 1

        future.add_done_callback(on_done)
        return InferenceRequest(future, timing)

    def close(self, *, wait: bool = True, cancel_pending: bool = False):
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
