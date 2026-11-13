# DEFECT-003 — Duplicate Host Command Could Execute Twice

- Severity: High
- Status: Fixed and regression protected
- Area: TCP request handling / remote-command idempotency
- Found during: simplified device-control duplicate-message testing

## Problem

Before the device-control extension, the simulator correlated responses with `request_id` but did not remember completed requests. If a Host timed out after the device completed a state-changing command, resending the same message could execute it again.

For `START`, this could increment the run counter twice even though the Host intended one logical command.

## Reproduction

1. Prepare the device to `READY`, establish communications and select `REMOTE`.
2. Load a valid TaskProfile.
3. Send `START` with `request_id=duplicate-start-1`.
4. Resend identical content with the same request ID.
5. Observe two executions and two run IDs in the pre-fix behavior.

## Root cause

The server generated a response sequence and returned it immediately but had no request fingerprint or completed-response cache. Request IDs were used for observability only, not idempotency.

## Fix

The TCP server now stores `request_id → (content fingerprint, encoded response)`:

- identical replay returns the original encoded response without invoking the device state machine;
- the response sequence and run ID remain unchanged;
- the same ID with different content returns `REQUEST_ID_CONFLICT`.

## Regression evidence

- `test_duplicate_start_is_idempotent`
- `test_reused_request_id_with_different_content_is_rejected`
- `test_timeout_retry_replays_cached_response`

The qualified run passed all three tests and reported one run after the duplicate `START` replay.




