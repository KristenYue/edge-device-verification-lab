# Release Qualification Report

- Run ID: `LOCAL-WIN-2026-11-13-EDGE-01`
- Build revision: `1aae43c63af27f5764fd06acccac23588afffaed`
- Environment: Windows 11, Visual Studio Build Tools 2022 17.13.2 / MSVC 14.43, Python 3.12.14
- Simulator SHA-256: not frozen; record after the first clean release build
- Result: **GO**

## Test results

| Suite | Passed | Failed | Skipped | Evidence |
|---|---:|---:|---:|---|
| C++ CTest | 1 test executable | 0 | 0 | local Release build plus Windows/Linux Actions matrix |
| Python automated suite | 98 | 0 | 1 | local pytest output; POSIX signal case skipped on Windows |
| Coverage gate | 83.30% total | 0 | 0 | `coverage.xml` (branch coverage enabled; gate 80%) |
| Static checks | Ruff PASS; mypy PASS | 0 | 0 | local command output |
| Recovery demonstration | 1 complete scenario | 0 | 0 | `artifacts/demo-events.jsonl` and console summary |
| Device-control demo | 1 complete scenario | 0 | 0 | `artifacts/control-protocol-demo-events.jsonl` |

The Python total combines unit, boundary, protocol-negative, integration, recovery,
repeated-run and device-control cases. The C++ executable contains the state-machine,
profile, fault, protocol and bounded-queue checks registered by CTest. The suite also
includes Smart Shelf v1 contract, ordering, isolation and authorization cases.

## Demonstration evidence

The qualified demonstration completed a normal run flow, reset the simulator, injected a actuator-stuck failure and recovered to `HOMED` after clearing the fault.

- Event count: 14
- Correlated requests: 10
- Duplicate response sequences: 0
- Reported device errors: `ACTUATOR_STUCK` (1, deliberately injected)
- Final recovery state: `HOMED`

The additional communications demonstration established ONLINE/REMOTE control, selected a TaskProfile, completed one run, replayed the same `START` request without a duplicate effect, and reported one injected interlock alarm.

- Device-control event count: 11
- Duplicate `START` response sequence unchanged: PASS
- Run count after duplicate replay: 1
- Active alarm report: `ALARM-1001:INTERLOCK_OPEN`

## Requirement status

The detailed result is recorded in `REQUIREMENTS_TRACEABILITY_MATRIX.csv`.

- Local functional, safety, interface and evidence requirements: PASS
- `QUAL-001` cross-platform C++ CI matrix: PASS
- `QUAL-003` Python-version CI matrix: PASS

GitHub Actions run [`43424447863`](https://github.com/KristenYue/edge-device-verification-lab/actions/runs/43424447863) passed all four Windows/Linux and Python 3.11/3.12 matrix jobs. Linux CTest and Python-driven simulator tests ran with ASan/UBSan enabled.

## Failures and defects

Three defects were found during qualification, corrected and protected by regression tests:

1. `DEFECT-001`: the diagnostic summary counted the recovery-control event `FAULTS_CLEARED` as an device error. The classifier now excludes control and recovery events; the final demonstration reports only `ACTUATOR_STUCK`.
2. `DEFECT-002`: brace-wrapped garbage and trailing-comma input could be classified as a schema error instead of malformed JSON. Lightweight syntax guards and C++ regression cases were added.
3. `DEFECT-003`: a timed-out Host could replay a state-changing command with the same request ID and execute it twice. A request fingerprint and completed-response cache now provide idempotent replay and conflict rejection.

Neither defect is open in this qualification snapshot. Details and reproduction evidence are in `docs/DEFECTS/`.

## Known limitations

- No real batch, optics, motion controller, vacuum system or hardware-in-the-loop setup is used.
- Run values are deterministic software-test data, not a physical edge device model.
- The TCP simulator uses a bounded worker pool and an explicit overload response, but shared device-state changes remain serialized and no real-time guarantee is made.
- The parser intentionally supports only this project's flat JSON command schema; it is not a general-purpose JSON implementation.
- The device-control layer is a project-specific JSON Lines contract, not an industry protocol or certification target.
- No GUI, database or multi-hour endurance run is included.
- C++ coverage is not collected by the current workflow; sanitizer and behavioral evidence are not a substitute for C++ line coverage.

See `KNOWN_LIMITATIONS.md` for the complete evidence boundary.

## Recommendation

**GO for the documented cross-platform portfolio scope.** The Windows/Linux build matrix, Python 3.11/3.12 tests, Linux sanitizers, automated functional suite, safety/fault recovery flow, trace diagnostics and static checks pass. This result does not extend to physical hardware, real-time guarantees or production deployment.





