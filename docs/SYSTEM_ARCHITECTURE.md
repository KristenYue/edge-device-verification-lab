# System Architecture

## Design objective

The architecture separates the device under test from the validation system. The C++ process owns device state and safety behavior. Python acts as an external client and must not reach into simulator internals, so system tests observe the same public behavior that production diagnostic software would observe.

## Components

### C++ device simulator

- `DeviceRuntime`: deterministic state machine, TaskProfile ownership, safety flags and event recording.
- `protocol`: request parsing, CRC32 verification and response/event serialization.
- TCP server: loopback-only command transport and JSONL log persistence.
- Completed-response cache: request fingerprinting, duplicate replay and ID-conflict rejection.

The simulator uses transient HOMING, CALIBRATING and RUNNING events but returns after the operation reaches a stable state. This keeps the MVP deterministic. Asynchronous completion is a documented extension rather than a hidden claim.

### Python validation package

- `client`: connection deadlines, request correlation, CRC generation and response contract validation.
- `models`: strict TaskProfile, response and event schemas.
- `diagnostics`: event loading, correlation and failure summaries.
- `reporting`: requirement result ingestion and release qualification output.
- `cli`: status, demonstration workflow and diagnostic report entry points.
- `control_protocol`: simplified Host-side communications/control facade, stable-ID retry and Alarm/Variable models.

### Test layers

1. C++ core tests exercise the state machine and protocol parser without sockets.
2. Python unit tests exercise validation contracts, timeout/error classification, diagnostics and reporting.
3. Python integration tests launch the compiled executable and validate behavior over TCP.
4. The stability marker repeats runs and checks identifier uniqueness.
5. Device-control tests exercise communication ownership, remote commands and raw TCP framing.

## Trust boundaries

- The server binds to `127.0.0.1`; it is not remotely exposed.
- Input is treated as untrusted and checked for required fields, TaskProfile ranges and optional CRC.
- The JSON parser is deliberately limited to this protocol. Production use requires a maintained JSON library and full escaping support.
- No secrets or cloud credentials are required.

## Failure behavior

- Contract or checksum errors are explicit negative responses.
- Safety faults transition the device into ERROR or E_STOP rather than reporting success.
- Transport timeout is a distinct Python exception and cannot be confused with a device rejection.
- Structured events retain the request ID so diagnosis can rebuild the sequence that led to failure.
- Timed-out requests can be retried with the same request ID; the response cache prevents duplicate state-changing behavior.

## Protocol boundary

The transport is the project-specific JSON Lines protocol documented in `INTERFACE_PROTOCOL.md`.
It models common communication, control-mode, alarm and variable-reporting behavior but
does not claim compatibility with a third-party or industry protocol.




