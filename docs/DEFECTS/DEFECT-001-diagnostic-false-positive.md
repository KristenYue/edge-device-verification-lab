# DEFECT 001 Diagnostic false positive after fault clear

- Severity: Medium
- Status: Fixed and regressed
- Found by: final demonstration run

## Reproduction

1. Inject `actuator_stuck`.
2. Run homing so the device enters ERROR.
3. Clear injected faults while the device remains in ERROR.
4. Generate the diagnostic summary.

## Expected

`ACTUATOR_STUCK` is counted as a failure. `FAULTS_CLEARED` is a recovery action and is not counted as a failure.

## Actual

The first implementation classified every event whose resulting state was ERROR as an error code. Because clearing the fault did not itself move the device out of ERROR, `FAULTS_CLEARED` appeared in `error_codes`.

## Root cause and correction

The diagnostic rule inferred failure only from the resulting state and ignored event semantics. Recovery/control events are now excluded explicitly, and `test_diagnose_does_not_count_fault_clear_as_an_error` prevents recurrence.



