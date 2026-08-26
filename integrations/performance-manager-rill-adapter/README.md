# Performance Manager Rill adapter

This crate is owned and released by `hello-yunshu/luci-app-performance-manager`.
It implements the frozen `pm-rill-shadow` protocol v1 (`status`, `observe`, and
`outcome`) as an advisory-only Unix-domain service. It has no UCI, sysctl,
firewall, ethtool, or arbitrary host-command actuator surface.

The initial implementation was migrated from the immutable RillML `v1.5.1`
tag, commit `cba9b3d2fb2c6a71cb9d4a02b18852171ad05a1b`, paths
`crates/rill-pm-adapter/{Cargo.toml,src/lib.rs,src/main.rs}`. Future fixes are
maintained here. The crate uses exact crates.io dependency `rill-ml = 1.5.3`
with no git/path/vendored RillML source.

State is stored at `/etc/performance-manager/rill/adapter-state.json` with
schema version 1. Valid state produced by PM v1.0.0's Rill adapter remains
loadable; corrupt or incompatible state fails closed and is never silently
deleted or reset.
