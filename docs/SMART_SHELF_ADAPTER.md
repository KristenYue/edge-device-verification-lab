# Smart Shelf Adapter

## Source boundary

The adapter mirrors the public telemetry and command contract from the companion
`smart-supermarket-shelf` repository. It does not copy firmware behavior, connect to
AWS IoT, or claim physical-hardware validation. Versioned fixtures under
`tests/fixtures/smart_shelf/v1/` are local, synthetic examples of the documented fields.

## Covered evidence

- distinct telemetry schemas for `smart-shelf-01` and `smart-shelf-02`;
- sensor ranges, required fields and state enumeration;
- device-scoped ordering, duplicate detection and timestamp-conflict detection;
- thread-safe ingestion and cross-device state isolation;
- MQTT command topic validation;
- `ACK` authorization only for shelf 2;
- rejection of unknown device identities and unsafe command targets.

## Explicit non-claims

- no Arduino, sensor, Wi-Fi, TLS certificate or AWS IoT execution occurs here;
- a passing adapter test does not prove physical-device behavior;
- the adapter is a verification consumer of the public contract, not a second firmware implementation.
