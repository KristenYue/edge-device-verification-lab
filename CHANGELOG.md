# Changelog

All notable changes to this portfolio project are documented here.

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
