# Fault Injection Plan

| Fault | Injection | Expected behavior | Recovery evidence |
|---|---|---|---|
| Open interlock | `inject_fault(type=interlock_open)` | Motion enters E_STOP; normal commands are blocked | Clear E_STOP returns IDLE; homing is required |
| Stuck actuator | `inject_fault(type=actuator_stuck)` | Homing ends in ERROR with `ACTUATOR_STUCK` | Clear fault, home again, observe HOMED |
| Sensor drift | `inject_fault(type=sensor_drift)` | Calibration fails closed with `CALIBRATION_FAILED` | Clear fault, reset/home/calibrate as required |
| Delayed response | `inject_fault(type=response_delay, delay_ms=N)` | Client deadline produces `DeviceTimeoutError` | Clear delay using a client with sufficient timeout |
| Corrupt checksum | Send request with wrong CRC32 | Request is rejected with `CRC_ERROR`; state unchanged | Retry with correct checksum |
| Malformed message | Send invalid JSON Line | Request is rejected with `MALFORMED_JSON` | Send a valid request on a new connection |
| Missing request field | Omit request ID or command | Request is rejected with `SCHEMA_ERROR` | Correct the request schema |
| Invalid TaskProfile | Send out-of-range field | Request is rejected with `PROFILE_INVALID` | Load a valid TaskProfile |

## Deferred injections

Process crash at persistence boundaries, disk-full behavior, out-of-order message reordering and sensor data stream corruption are deliberately deferred. Duplicate-command idempotency and response-timeout retry are now covered by the in-memory response cache; durable replay after process restart is not claimed.


