# Project Status

## 2026-11-26 SDK product-boundary milestone

SDK `0.3.0` adds an execution-backend protocol, structured model/tensor
contracts and session-level terminal outcome counters without replacing the
existing native `InferenceSession` API. The checked Windows acceptance run is
stored in `inference_sdk/benchmarks/windows-sdk-v030.json`; four SDK tests pass.

This interface makes a later CUDA EP or device backend an explicit adapter
task. It does not claim that a GPU/NPU backend has already been implemented.

## 2026-11-24 native inference SDK milestone

The device runtime status below remains unchanged. A separate `inference_sdk/` vertical slice now has local Windows evidence for:

- C++17/pybind11/ONNX Runtime CPU Wheel build and installation;
- dynamic-shape multi-input/multi-output contracts and common numeric output dtypes;
- explicit input/output ownership, GIL release around native execution, and ORT exception mapping;
- bounded asynchronous requests with copied inputs, cancellation, queue rejection and deadline semantics;
- request-level queue/execution traces plus native input-binding/ORT-run/output-copy phase traces;
- real BGE and MobileNetV2 cross-workload benchmarks with Python ORT numerical comparison;
- BGE dynamic-INT8 experiment preserving both performance gains and retrieval-smoke quality regression.

Local acceptance: SDK Wheel `0.2.0` builds and installs, three SDK tests pass, and the existing C++ core CTest passes. The updated Ubuntu SDK workflow is configured but must not be described as passed until its corresponding GitHub Actions run succeeds.

Still deferred: CUDA/NPU providers, static quantization with representative calibration data, physical edge hardware, and native C++ scheduling. Dynamic INT8 is framework-provided ONNX Runtime quantization, not a custom quantizer or kernel.

Status as of 2026-11-13: **domain-neutral refactor complete and cross-platform qualified**.

## Completed

- C++17 virtual device runtime and state machine
- TCP JSON-line command interface with request correlation, sequence numbers and CRC32
- Safety interlock, profile guards and four fault-injection modes
- Python validation client, schema validation, diagnostics and reporting
- Unit, boundary, negative, integration, recovery and repetition tests
- Structured JSONL evidence and release-qualification artifacts
- Requirements, architecture, protocol, test-plan, fault-plan and traceability documentation
- Project-specific control model: Offline/Online, Local/Remote, remote TaskProfile/Start/Stop
- Alarm, event and variable reporting with explicit protocol boundaries
- TCP half/sticky packet validation, concurrent correlation and duplicate-message idempotency
- Stable-ID timeout retry and request-ID conflict detection
- Bounded C++ worker pool, explicit `SERVER_BUSY` backpressure and signal-aware shutdown
- Concurrent duplicate-command execution protected by request fingerprinting and response caching
- Smart Shelf v1 contract adapter with two-device ordering, isolation and authorization checks
- Windows Release build, CTest, Ruff, mypy and 98-test Python regression run
- Python branch coverage 83.30% with an 80% CI gate
- Normal-flow plus injected-fault recovery demonstration
- Professional README, traceability update, defect reports and walkthrough GIF
- GitHub Actions PASS on Windows/Linux with Python 3.11/3.12; Linux ASan/UBSan PASS

## Intentionally deferred

- Physical hardware or hardware-in-the-loop integration
- Third-party industry-protocol compatibility or certification
- GUI and persistent database
- Parallel state mutation and real-time guarantees
- Long-duration endurance and performance qualification

Deferred items are extensions, not prerequisites for explaining the current MVP. Do not present them as completed in a resume or interview.

## Recommended next action

Preserve the passing cross-platform workflow as release evidence, then add measured endurance or throughput results only after a repeatable benchmark protocol exists.




