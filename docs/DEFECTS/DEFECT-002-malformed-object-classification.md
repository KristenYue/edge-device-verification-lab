# DEFECT 002 Malformed object classified as a schema error

- Severity: Medium
- Status: Fixed and regressed
- Found by: protocol boundary review

## Reproduction

Send `{garbage}` or a request object with a trailing comma.

## Expected

The protocol returns `MALFORMED_JSON` because the message is not valid JSON object syntax.

## Actual

The original lightweight parser checked only the opening and closing braces, then returned `SCHEMA_ERROR` when it could not find required keys.

## Root cause and correction

The parser confused envelope syntax validation with field validation. It now rejects obvious object-syntax failures before checking required fields. C++ regression tests cover brace-wrapped garbage and trailing commas.

## Boundary

The parser remains intentionally limited and is not a replacement for a maintained JSON library. Full JSON conformance is documented as a production hardening requirement.

