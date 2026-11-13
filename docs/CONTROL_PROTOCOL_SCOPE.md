# Device-Control Protocol Scope

## Purpose

The project uses a small JSON Lines protocol to exercise common control-plane behavior:
communication establishment, local/remote ownership, status variables, alarms, remote
commands, retries and idempotency. It is intentionally project-specific and does not
claim compatibility with an industry or vendor protocol.

## Commands

| Behavior | Command | Success code |
|---|---|---|
| Establish communications | `protocol_establish_communications` | `COMMUNICATIONS_ESTABLISHED` |
| Go offline | `protocol_go_offline` | `OFFLINE_ACK` |
| Select remote/local mode | `protocol_set_remote`, `protocol_set_local` | `REMOTE_MODE_ACK`, `LOCAL_MODE_ACK` |
| Read variables | `protocol_get_variables` | `VARIABLE_REPORT` |
| Execute remote command | `protocol_host_command` with `PROFILE`, `START`, `STOP` | `REMOTE_COMMAND_ACK` in response data |
| Read alarms | `protocol_get_alarms` | `ALARM_REPORT` |

## Control rules

1. The runtime starts `OFFLINE / LOCAL`.
2. Establishing communications moves it to `ONLINE / LOCAL`.
3. Remote commands are rejected until the runtime is `ONLINE / REMOTE`.
4. Going offline returns control ownership to `LOCAL`.
5. Profile validation and lifecycle state guards remain active in remote mode.

## Reliability rules

- Every request carries a `request_id`.
- Retrying identical content with the same ID returns the cached response.
- Reusing an ID with different content returns `REQUEST_ID_CONFLICT`.
- The TCP buffer accepts split frames and multiple newline-delimited requests in one packet.
- The Python control host retries transport failures with a stable request ID.

## Explicit non-goals

- hardware transport or hardware-in-the-loop validation;
- protocol discovery or compatibility with third-party equipment;
- authentication, encryption or remote network exposure;
- persistent response caching, hard real-time control or throughput guarantees.
