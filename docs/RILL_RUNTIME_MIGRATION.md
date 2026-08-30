# PM generic Rill Runtime migration

Performance Manager is being moved from the repository-owned native
`performance-manager-rill-adapter` to the package-owned generic
`rill-runtime` at `/usr/bin/rill-runtime`.

The current `performance-manager-rill-adapter` is explicitly a temporary
compatibility bridge. It still owns the Stable `pm-rill-shadow` v1 wire shape
and the existing online-learning behavior, so it must not be deleted until the
generic stateful Runtime v3 contract is qualified on the supported OpenWrt
branches.

The all-in-one package contains Core, LuCI, ACL/menu and translations only.
The optional `performance-manager-rill` package owns service glue and depends
on `performance-manager` plus the target-specific
`performance-manager-rill-adapter`. The independent `rill-runtime` package is
not part of this bridge path and is provisioned from
`hello-yunshu/rill-openwrt-packages` during the separate Runtime v3 cutover.

The cutover gate is fail-closed: back up the old
`/etc/performance-manager/rill/adapter-state.json`, record a deterministic
migration result, and retain the PM-specific governance, apply, verify,
rollback and reward mapping in this repository. A missing, incompatible or
unreadable generic Runtime must never silently reset learned state.
