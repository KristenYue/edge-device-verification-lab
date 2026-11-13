# Project Status

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




