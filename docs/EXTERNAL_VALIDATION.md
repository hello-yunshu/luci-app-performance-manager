# External Validation Profiles for 1.0.3

`1.0.3` keeps the official OpenWrt SDK build compiling and verifying every split package, the physical arch-independent all-in-one APK, the arch-independent `performance-manager-rill` glue APK, and one target-specific PM-owned adapter APK for each qualified target. The package matrix is OpenWrt 25.12.5 x86_64, armsr/armv8 (`aarch64_generic`), and mediatek/filogic (`aarch64_cortex-a53`); the real adapter runtime and target behavior evidence remain x86_64-scoped until an arm64 runtime gate is executed. The adapter is built from the same commit with exact crates.io `rill-ml` 1.5.3. The all-in-one APK does not contain native adapter code or Rill glue; install it with the glue and matching adapter APK. This profile does not claim Hyper-V, router hardware, firmware sysupgrade reboot, or a 24-hour soak until those evidence gates complete.

The current official 25.12.x x86/64 target is available as OpenWrt 25.12.5, including an x86/64 rootfs and SDK; the SDK matrix also qualifies official armsr/armv8 and mediatek/filogic. Runtime gates remain pinned to x86/64 until a booted arm64 rootfs gate is added. CI builds Core, LuCI, Rill glue, the PM-owned adapter, and the all-in-one package for all three native package architectures.

Required target evidence:

1. GitHub CI: the `.github/workflows/ci.yml` source/behavior jobs — `static` (incl. the LuCI render smoke harness `scripts/luci_render_smoke.js`), `adapter-rust`, `pm-rill-provenance` (PM-owned exact artifact), `pm-rill-runtime` (real adapter + protocol roundtrip + fail-closed negatives), `pm-core-rill-roundtrip` (raw shipped Core ↔ PM adapter), `openwrt-ucode` (official OpenWrt 25.12.5 rootfs ucode compile of Core) — plus the remote official SDK build in `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (builds only packages this repository owns and emits build-metadata.json + checksums.txt evidence).
2. Booted OpenWrt 25.12.x x86_64 VM: `scripts/openwrt-target-gate.sh`.
3. Hyper-V and KVM/Proxmox guest hotplug/TargetRef/replay/rollback fixtures.
4. Explicit LAN→Router→WAN and router-local controlled A/B sessions where the action semantics require them.
5. Sysupgrade preservation via `scripts/openwrt-sysupgrade-gate.sh prepare` before the upgrade and `verify` after reboot, plus `scripts/openwrt-resource-soak.sh` for 24h or longer.

The hardware matrix remains available as the `hardware` profile. It is not silently substituted into `portable-docker`, and portable publication must disclose the narrower coverage in its release evidence and notes.

## Docker-based Evidence Progress

Validation can be driven locally from the official 25.12.5 x86/64 rootfs via Docker (see `tools/docker-validate/`), which removes the "offline / non-OpenWrt" blocker for runtime gates. Evidence artifacts are collected in `evidence/`.

Status:

- **1. GitHub CI** — owned by `.github/workflows/ci.yml` (`static`, `adapter-rust`, `pm-rill-provenance` with PM-owned artifact provenance, `pm-rill-runtime` with real adapter execution, `pm-core-rill-roundtrip` with raw Core ↔ PM adapter, `openwrt-ucode` official 25.12.5 rootfs compile of Core) and `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (official SDK builds Core, LuCI, Rill glue, PM-owned adapter, and `luci-app-performance-manager-all`, then verifies exact metadata and bundle payloads; emits build-metadata.json + checksums.txt).
- **2. Booted OpenWrt runtime gate** — PASSED inside the `owrt-pm-gate` container (25.12.5 x86/64): `scripts/openwrt-target-gate.sh` CORE-ONLY, 11/11 assertions green. Evidence: `evidence/openwrt-target-gate-25.12.5.json`.
- **5. Historical resource soak (dev check only)** — the old 120-second sample is not Stable evidence and is not reused by the aggregator. The rc.10 gate requires ≥86400 seconds with Core and exact Rill RSS/CPU, restart counts, logical persistence counters, state bounds, and zero idle Observe/adapter-persistence/pending-Outcome-journal deltas; missing counters are `BLOCKED`, never zero-filled.

Not evaluated by the portable profile: items 3 (Hyper-V/KVM fixtures) and 4 (LAN/WAN A/B sessions), plus the full 24h soak and sysupgrade round-trip from item 5.

Docker notes: the OpenWrt container's netifd bridges `eth0` into `br-lan` and drops the docker default route, so it is offline by design; gates must not depend on `apk add`. The container busybox lacks float sleep, so `tools/docker-validate/sleep-shim` is installed ahead of the gate. The shipped Core is written callee-before-caller (zero forward references, verified), so runtime gates install it verbatim — there is deliberately no `convert_hoist.py` transform (CORE BLOCKER C).
