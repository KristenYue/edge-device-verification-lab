# System Validation Test Plan

## Objective

Demonstrate that the virtual device enforces its functional and safety contracts, exposes diagnosable failures, and can be rebuilt and retested on supported platforms.

## Test levels

| Level | Scope | Entry condition | Exit condition |
|---|---|---|---|
| C++ unit | State guards, ranges, safety flags, CRC/parser | CMake configure succeeds | CTest passes |
| Python unit | Schemas, client errors, diagnostics, release reporting | Package installs | Unit suite passes |
| Interface | JSON Lines, CRC, required fields, response schema | Simulator executable available | Contract cases pass |
| System | Complete run and negative workflows | Unit and interface tests pass | Critical requirements pass |
| Recovery | Interlock, actuator, drift and delay injection | Fault API available | Safe failure and documented recovery pass |
| Stability | Repeated runs and unique IDs | Core system tests pass | No duplicate IDs in configured run |
| DeviceRuntime communication | Online/local/remote, remote command, variables and alarms | Simulator and Host facade available | control-protocol requirements pass |
| Transport resilience | Half/sticky packets, timeout, retry and duplicates | TCP endpoint available | No framing loss or repeated effect |

## Selection strategy

- Pull request: all C++ tests plus Python unit and integration tests.
- Local smoke: C++ CTest and the normal end-to-end run test.
- Stability: tests marked `stability`; current checked-in test performs 50 deterministic cycles. A two-hour run is an extension and must not be claimed until executed.

## Severity

- Critical: unsafe transition, E_STOP bypass, data corruption or false successful run.
- High: valid workflow cannot complete, fault is misclassified, correlation evidence is missing.
- Medium: diagnostic summary or non-critical report error.
- Low: documentation, wording or cosmetic CLI issue.

## Release decision

- NO-GO for any failed critical/high test.
- CONDITIONAL when required external evidence is blocked and explicitly documented.
- GO only when all in-scope requirements pass and the known limitations are accepted.

## Evidence

- CTest console output.
- Pytest JUnit XML.
- Branch coverage XML.
- JSONL device event log.
- Diagnostic JSON or console summary.
- Requirement traceability matrix.
- Release qualification report generated from verified results.
- Duplicate-message response sequence and run-count evidence.



