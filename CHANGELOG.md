# Changelog

All notable changes to this portfolio project are documented here.

## [0.3.0] - 2026-11-26

### Added

- `InferenceBackend` protocol and checked `NativeOrtBackend` adapter.
- Serializable `ModelContract` and `TensorSpec` with named dtype, rank,
  dimension, contiguity and dynamic-axis validation.
- Async session counters for admission, rejection, completion, cancellation,
  timeout and backend failure outcomes.
- SDK 0.3.0 acceptance artifact containing the runtime contract and backend.

### Verified

- Native Windows Wheel builds and installs with ONNX Runtime 1.22.0.
- Four SDK tests cover native multi-I/O, queue ownership, deadlines, statistics
  and named contract failures.
- Generated reference graph remains numerically identical to Python ORT and
  rejects invalid dtype, shape and stride inputs.

## [0.2.0] - 2026-11-13

### Added

- Bounded C++ worker pool with configurable worker and queue limits.
- Explicit `SERVER_BUSY` overload response and connection saturation tests.
- Concurrent duplicate-command idempotency verification.
- Linux AddressSanitizer and UndefinedBehaviorSanitizer CI configuration.
- Smart Shelf v1 telemetry adapter, versioned fixtures and command authorization tests.
- Requirement-to-test mappings for concurrency and IoT verification behavior.

### Verified

- Windows Release build and CTest pass.
- 98 Python tests pass; one POSIX signal test is skipped on Windows.
- 83.30% statement and branch coverage.
- Ruff and strict mypy checks pass.

## [0.1.0] - 2026-11-13

### Added

- C++17 virtual edge-device runtime and JSON Lines TCP service.
- Python validation host, fault injection, diagnostics and release evidence.
- State, safety, framing, retry, idempotency and recovery test coverage.
