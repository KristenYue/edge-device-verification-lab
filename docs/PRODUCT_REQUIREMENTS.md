# Product Requirements

## Purpose

The system provides a deterministic, locally reproducible environment for validating software used to control a simulated edge device. It supports requirement-based testing, safe state transitions, fault injection, trace collection and release evidence without proprietary hardware.

## Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| SYS-001 | The simulator shall start in BOOT. | First status response reports BOOT. |
| SYS-002 | Power-on shall run a self-test and enter IDLE. | `power_on` returns `SELF_TEST_PASSED` and IDLE. |
| SYS-003 | Homing shall only be accepted from IDLE or ERROR. | Other states return `INVALID_STATE`. |
| SYS-004 | Successful homing shall end in HOMED. | Response and event trace show HOMED. |
| SYS-005 | Calibration shall only be accepted from HOMED. | Other states return `INVALID_STATE`. |
| SYS-006 | Successful calibration shall end in READY. | Response and event trace show READY. |
| SYS-007 | A valid TaskProfile shall be required before run. | Run without TaskProfile returns `PROFILE_REQUIRED`. |
| SYS-008 | TaskProfile names shall contain 1 to 64 non-whitespace characters. | Invalid names are rejected before transmission or by the simulator. |
| SYS-009 | TaskProfile sample count shall be between 10 and 100000 inclusive. | Boundary tests pass and out-of-range values fail. |
| SYS-010 | TaskProfile noise sigma shall be between 0 and 1 inclusive. | Boundary tests pass and out-of-range values fail. |
| SYS-011 | TaskProfile drift limit shall be greater than 0 and at most 5. | Boundary tests pass and out-of-range values fail. |
| SYS-012 | A successful run shall return a unique run ID. | Repeated run IDs do not collide. |
| SYS-013 | Reset from COMPLETE, ERROR, or WARNING shall return to IDLE. | Reset response reports IDLE and clears the TaskProfile. |
| SYS-014 | Unsupported commands shall be rejected explicitly. | Response code is `UNKNOWN_COMMAND`. |

## Safety and recovery requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| SAFE-001 | An open interlock shall block motion. | Homing enters E_STOP with `INTERLOCK_OPEN`. |
| SAFE-002 | Emergency stop shall block non-safety commands. | Only status and clear are accepted in E_STOP. |
| SAFE-003 | Clearing emergency stop shall return to IDLE and require re-homing. | Clear response reports IDLE. |
| SAFE-004 | A stuck actuator shall fail homing closed. | State becomes ERROR with `ACTUATOR_STUCK`. |
| SAFE-005 | Excess sensor drift shall fail calibration closed. | State becomes ERROR with `CALIBRATION_FAILED`. |
| SAFE-006 | Injected faults shall be clearable without restarting the process. | A previously failing action succeeds after clear and required setup. |
| SAFE-007 | A delayed response shall be surfaced as a client timeout. | Client raises `DeviceTimeoutError`. |

## Interface and traceability requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| INT-001 | Requests shall contain request ID and command. | Missing fields return `SCHEMA_ERROR`. |
| INT-002 | Responses shall echo the request ID. | Correlation is verified in integration tests. |
| INT-003 | Responses shall contain monotonic sequence and timestamp fields. | Contract validation rejects missing or invalid fields. |
| INT-004 | Optional CRC32 shall detect corrupted command envelopes. | Invalid CRC returns `CRC_ERROR`. |
| INT-005 | Each state-changing command shall emit a structured event. | JSONL log contains the correlation ID and transition. |
| INT-006 | Event sequence numbers shall not be duplicated. | Diagnostic report reports zero duplicates. |
| INT-007 | The diagnostic tool shall group error events and transitions. | Generated JSON includes error and transition counters. |

## Quality requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| QUAL-001 | C++ shall build on Windows and Linux using CMake. | CI matrix builds both operating systems. |
| QUAL-002 | C++ core tests shall run through CTest without network downloads. | `ctest` passes in a clean checkout. |
| QUAL-003 | Python shall support versions 3.11 and 3.12. | CI matrix passes both versions. |
| QUAL-004 | Test results shall be exportable as JUnit XML. | CI artifact contains `junit.xml`. |
| QUAL-005 | Python branch coverage shall be measured. | CI produces `coverage.xml`; no unverified percentage is claimed. |
| QUAL-006 | A new contributor shall be able to reproduce the demo from documented commands. | README steps work in a clean environment. |

## Device-control protocol requirements

These requirements describe the project-specific JSON Lines control protocol.

| ID | Requirement | Acceptance criterion |
|---|---|---|
| CTRL-001 | DeviceRuntime shall start OFFLINE and LOCAL. | First status response reports both values. |
| CTRL-002 | A communication handshake shall enter ONLINE/LOCAL. | Response is `COMMUNICATIONS_ESTABLISHED`. |
| CTRL-003 | REMOTE selection shall be rejected while OFFLINE. | Response is `PROTOCOL_OFFLINE`. |
| CTRL-004 | Remote commands shall require ONLINE/REMOTE. | Command in LOCAL returns `PROTOCOL_NOT_REMOTE`. |
| CTRL-005 | The host shall select a valid TaskProfile through a remote command. | Valid `PROFILE` returns success; invalid ranges fail. |
| CTRL-006 | The host shall issue START and STOP remote commands. | START completes one run; STOP returns to IDLE. |
| CTRL-007 | DeviceRuntime shall expose observable variables. | Response includes state, mode, count and TaskProfile flag. |
| CTRL-008 | DeviceRuntime shall expose and clear active alarms. | Injected alarm is listed once and absent after clear. |
| CTRL-009 | Duplicate identical messages shall be idempotent. | Same ID/content returns cached sequence and no repeated effect. |
| CTRL-010 | Reused IDs with different content shall be rejected. | Response is `REQUEST_ID_CONFLICT`. |
| CTRL-011 | Transport shall tolerate split and coalesced TCP frames. | Half-packet and sticky-packet integration cases pass. |
| CTRL-012 | Timed-out requests shall be retryable with a stable ID. | Retry returns cached response without duplicate execution. |
| CTRL-013 | Connection concurrency shall be bounded. | A full connection queue returns `SERVER_BUSY` instead of growing without limit. |
| CTRL-014 | Concurrent duplicate commands shall execute once. | All identical concurrent IDs receive one cached sequence and run count remains one. |

## Smart Shelf adapter requirements

These requirements apply only to the documented Smart Shelf v1 JSON/MQTT contract and synthetic fixtures; they do not claim physical-device validation.

| ID | Requirement | Acceptance criterion |
|---|---|---|
| IOT-001 | Only known device identities and valid telemetry fields shall be accepted. | Invalid IDs, types and ranges raise a contract error. |
| IOT-002 | Duplicate, out-of-order and same-timestamp conflicting telemetry shall be classified separately. | Adapter tests observe each distinct result. |
| IOT-003 | Ordering state shall be isolated per device. | A newer sample on one shelf does not reject a valid sample on another. |
| IOT-004 | Concurrent identical telemetry shall create one accepted record. | 32 submissions produce one accepted record and 31 duplicates. |
| IOT-005 | Command authorization shall follow the device/topic contract. | Shared commands work for both shelves; ACK is restricted to shelf 2. |



