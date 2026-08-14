# Test Plan — 1.0.0-rc.2

The frozen plan requires separate evidence layers. Passing one layer never substitutes for another.

## Local/source gates (`make audit`)

- Draft 2020-12 schemas and runtime-shipped schema identity.
- Runtime-shaped Transaction examples and recovery decision fixtures.
- Companion v2 evidence/context/reward fixtures.
- Baseline-relative Health fixtures.
- Profile inheritance plus required/recommended/conditional package/capability/target checks.
- Benchmark state/persistence ordering and rollback-before-reward invariants.
- Ownership-safe uninstall/runtime-lease and sysupgrade keep semantics.
- Security source guards: fixed argv Core, Rill no command execution, Shadow-only protocol.
- LuCI JavaScript syntax, JSON/YAML, shell syntax and complete current zh_Hans literal coverage.
- Machine-computed Phase 0–12 **source-only** gates.

Rust unit tests additionally exercise strict envelope parsing, bounded reads, UTF-8/JSON escapes, validated-only outcomes, bounded state and positive-evidence recommendation behavior. They run in CI because the current assembly environment has no local Rust toolchain.

## CI gates

1. `make audit` on Linux.
2. Native `cargo test --locked` + `cargo check --locked` for Rill.
3. Official OpenWrt **25.12.5 x86/64** rootfs ucode bytecode compile with required modules.
4. Official OpenWrt 25.12.5 x86/64 SDK build of Core, LuCI and Rill packages.

## Booted-target gates

`scripts/openwrt-target-gate.sh` produces machine-readable target evidence. It checks OpenWrt/x86_64 identity, Core startup/ubus, Analyzer/Topology/Packet Steering, Core survival with Rill stopped and stale locks. `PM_ALLOW_MUTATION=1` explicitly enables the conservative Hyper-V ring apply/manual-rollback and ownership-cleanup tests when a legal candidate exists.

`scripts/openwrt-resource-soak.sh` defaults to the frozen 24h gate and reports maximum Core RSS, approximate mean CPU and Core/Rill logical persistent writes per day. A shortened duration is development evidence only.

## Testbed-only gates

- Hyper-V and KVM hotplug/TargetRef/replay/rollback fixtures.
- LAN client → Router → WAN server forwarding controlled A/B.
- Router-local endpoint controlled A/B where semantically appropriate.
- Sysupgrade preservation/upgrade behavior.

No source gate or passive observation is allowed to impersonate these target/testbed results.
