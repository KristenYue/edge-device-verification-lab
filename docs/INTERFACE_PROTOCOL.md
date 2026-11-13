# Interface Protocol

## Transport

- TCP over loopback.
- UTF-8 JSON Lines: one JSON object followed by `LF` per request and response.
- Default port: 8765.
- One response per request.

## Request

```json
{"request_id":"r-1","command":"status","params":{},"crc32":"CAE57524"}
```

`crc32` is optional. In this MVP it covers the UTF-8 bytes of `request_id|command`. This demonstrates corruption detection but is not a production canonical-message scheme.

Supported commands:

| Command | Parameters | Stable success state |
|---|---|---|
| `status` | none | unchanged |
| `power_on` | none | IDLE |
| `home` | none | HOMED |
| `calibrate` | none | READY |
| `load_profile` | name, sample_count, noise_sigma, drift_limit | unchanged |
| `start_run` | none | COMPLETE |
| `reset` | none | IDLE |
| `emergency_stop` | none | E_STOP |
| `clear_emergency_stop` | none | IDLE |
| `inject_fault` | type and optional delay_ms | unchanged or fault-specific |
| `protocol_establish_communications` | none | ONLINE / LOCAL |
| `protocol_go_offline` | none | OFFLINE / LOCAL |
| `protocol_set_remote` | none | ONLINE / REMOTE |
| `protocol_set_local` | none | ONLINE / LOCAL |
| `protocol_get_variables` | none | unchanged |
| `protocol_get_alarms` | none | unchanged |
| `protocol_host_command` | command_name plus command parameters | command-specific |

The `protocol_*` commands belong to this project's JSON Lines control contract. They do
not implement a third-party or industry protocol. See `CONTROL_PROTOCOL_SCOPE.md`.

## Framing and duplicate handling

- The receive buffer waits for `LF`, so one logical request may arrive in multiple TCP packets.
- Multiple newline-delimited requests may arrive in one TCP packet and are processed in order.
- An identical `request_id` and content replays the cached response without repeating device behavior.
- Reusing a `request_id` with different content returns `REQUEST_ID_CONFLICT`.

## Response

```json
{
  "request_id": "r-001",
  "sequence": 1,
  "timestamp_ms": 1792470000000,
  "ok": true,
  "code": "STATUS",
  "message": "device status",
  "state": "BOOT",
  "data": {"run_count":"0","profile_loaded":"false"}
}
```

## Error codes

| Code | Meaning |
|---|---|
| `MALFORMED_JSON` | Message is not a single JSON object. |
| `SCHEMA_ERROR` | Required request field is missing. |
| `CRC_ERROR` | Provided checksum does not match. |
| `INVALID_STATE` | Command is not legal in the current state. |
| `PROFILE_INVALID` | TaskProfile field or range is invalid. |
| `PROFILE_REQUIRED` | Run requested without a TaskProfile. |
| `SAFETY_INTERLOCK` | Command blocked while E_STOP is active. |
| `INTERLOCK_OPEN` | Motion or run blocked by open interlock. |
| `ACTUATOR_STUCK` | Homing could not complete. |
| `CALIBRATION_FAILED` | Sensor drift prevents calibration. |
| `SENSOR_DRIFT` | Run became invalid due to drift. |
| `UNKNOWN_COMMAND` | Command is unsupported. |
| `PROTOCOL_OFFLINE` | The control command requires ONLINE communications. |
| `PROTOCOL_NOT_REMOTE` | A Host command was attempted in LOCAL mode. |
| `INVALID_REMOTE_COMMAND` | The simplified remote command is missing or unsupported. |
| `REQUEST_ID_CONFLICT` | A previous request used the same ID with different content. |






