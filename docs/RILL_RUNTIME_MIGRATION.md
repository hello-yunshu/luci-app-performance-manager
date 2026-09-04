# PM generic Rill Runtime migration

The Runtime v3 cutover is complete. Performance Manager consumes the
package-owned generic `rill-runtime` at `/usr/bin/rill-runtime` through the
exact contract in `contracts/rill-runtime.json` (currently version 1.5.6 and
the pinned qualified upstream commit recorded there).

The all-in-one package contains Core, LuCI, ACL/menu, translations, integration
glue, keep rules, notices, and the exact qualified Runtime executable. The
`performance-manager-rill` package is the retained split integration path: it depends on
`performance-manager` and the external `rill-runtime` package from
`hello-yunshu/rill-openwrt-packages`. This repository does not contain or
restore a PM-owned adapter, a legacy shadow protocol, or a second Runtime
implementation.

The cutover remains fail-closed. Core validates Runtime identity, protocol,
state compatibility, candidate binding, transaction safety and outcome
feedback; a missing, incompatible or unreadable Runtime cannot silently reset
learned state or acquire execution authority. PM-specific governance, apply,
verify, rollback and reward mapping remain owned by Core in this repository.

Historical adapter/state fixtures are retained only as explicitly labelled
audit history and are not package, protocol, migration, or release inputs.
