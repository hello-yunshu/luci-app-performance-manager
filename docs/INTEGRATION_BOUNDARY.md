# Integration boundary

Performance Manager owns the business-specific `pm-rill-shadow` v1 adapter,
its OpenWrt service/package surface, state migration, and target qualification.
The adapter links exact crates.io `rill-ml` 1.5.1 and remains advisory-only.

RillML owns generic native crates, runtime IPC protocols, handler/model APIs,
generic persistence and conformance. The historical v1.5.1 `rill-pm-adapter`
Release asset remains readable as a compatibility fixture, but is not emitted
or selected by current PM provisioning.
