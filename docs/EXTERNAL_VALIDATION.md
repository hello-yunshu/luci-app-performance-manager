# External Validation Profiles for 1.0.4

Checked-in JSON snapshots under `docs/` and `evidence/` that carry
`historicalOnly: true` are audit history only. Current release decisions must
use same-commit workflow artifacts collected by `collect_stable_evidence.py`;
the historical snapshots never authorize Stable.

`1.0.4` keeps the official OpenWrt SDK build compiling and verifying every PM-owned split package plus three architecture-specific all-in-one APKs. The package matrix is OpenWrt 25.12.5 x86_64, armsr/armv8 (`aarch64_generic`), and mediatek/filogic (`aarch64_cortex-a53`). Each full APK physically contains Core, LuCI, zh-cn, glue, keep rules, notices, and the exact qualified Runtime binary staged from the pinned external `rill-openwrt-packages` artifact; the split `performance-manager-rill` + `rill-runtime` path remains available for developers. This profile does not claim Hyper-V, router hardware, firmware sysupgrade reboot, or a 24-hour soak until those evidence gates complete.

The current official target is OpenWrt 25.12.5, including x86/64, armsr/armv8, and mediatek/filogic SDK coverage. CI builds Core, LuCI, split glue, the canonical Runtime, and the architecture-specific full package for all three native package architectures. The external Runtime feed remains the canonical source and qualification authority; its exact executable is bundled into the full APK and is not a standalone public release asset.

Required target evidence:

1. GitHub CI: the `.github/workflows/ci.yml` source/behavior jobs — `static` (incl. the LuCI render smoke harness `scripts/luci_render_smoke.js`), `rill-runtime-v3` (real external Runtime v3 handshake/health/decide/feedback and fail-closed negatives), `production-core-rill-integration` (raw shipped Core selector → exact candidate binding → transaction against the pinned real Runtime in official OpenWrt ucode), `pm-core-rill-roundtrip` (raw shipped Core ↔ generic Runtime), `openwrt-ucode` (official OpenWrt 25.12.5 rootfs ucode compile of Core) — plus the remote official SDK build in `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (builds only packages this repository owns and emits build-metadata.json + checksums.txt evidence).
2. Booted OpenWrt 25.12.x x86_64 VM: `scripts/openwrt-target-gate.sh`.
3. Hyper-V and KVM/Proxmox guest hotplug/TargetRef/replay/rollback fixtures.
4. Explicit LAN→Router→WAN and router-local controlled A/B sessions where the action semantics require them.
5. Sysupgrade preservation via `scripts/openwrt-sysupgrade-gate.sh prepare` before the upgrade and `verify` after reboot, plus `scripts/openwrt-resource-soak.sh` for 24h or longer. Resource Soak uses Core-resident metrics and bounded Runtime subprocess lifecycle/state counters; it does not require a fictional long-running Runtime daemon metric.

The direct `scripts/openwrt-resource-soak.sh` output is a standalone target measurement report and is not itself Stable authorization. The Hardware workflow's repository-owned controller wraps transport `rawFacts`, applies the canonical schema/evaluator, and is the only path that emits the install/build-bound gate evidence consumed by Stable aggregation.

The hardware matrix remains available as the `hardware` profile. It is not silently substituted into `portable-docker`, and portable publication must disclose the narrower coverage in its release evidence and notes.

## Docker-based Evidence Progress

Validation can be driven locally from the official 25.12.5 x86/64 rootfs via Docker (see `tools/docker-validate/`), which removes the "offline / non-OpenWrt" blocker for runtime gates. Evidence artifacts are collected in `evidence/`.

Status:

- **1. GitHub CI** — owned by `.github/workflows/ci.yml` (`static`, `rill-runtime-v3` with real external Runtime execution, `production-core-rill-integration` with raw Core selector/transaction execution against that Runtime, `pm-core-rill-roundtrip` with raw Core ↔ generic Runtime, `openwrt-ucode` official 25.12.5 rootfs compile of Core) and `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (official SDK builds Core, LuCI, integration glue, and `luci-app-performance-manager-all`, then verifies exact metadata and bundle payloads; emits build-metadata.json + checksums.txt).
- **2. Booted OpenWrt runtime gate** — PASSED inside the `owrt-pm-gate` container (25.12.5 x86/64): `scripts/openwrt-target-gate.sh` CORE-ONLY, 11/11 assertions green. Evidence: `evidence/openwrt-target-gate-25.12.5.json`.
- **5. Historical resource soak (dev check only)** — the old 120-second sample is not Stable evidence and is not reused by the aggregator. The rc.10 gate requires ≥86400 seconds with Core and exact Rill RSS/CPU, restart counts, logical persistence counters, state bounds, and zero idle Observe/adapter-persistence/pending-Outcome-journal deltas; missing counters are `BLOCKED`, never zero-filled.

Not evaluated by the portable profile: items 3 (Hyper-V/KVM fixtures) and 4 (LAN/WAN A/B sessions), plus the full 24h soak and sysupgrade round-trip from item 5.

Docker notes: the OpenWrt container's netifd bridges `eth0` into `br-lan` and drops the docker default route, so it is offline by design; gates must not depend on `apk add`. The container busybox lacks float sleep, so `tools/docker-validate/sleep-shim` is installed ahead of the gate. The shipped Core is written callee-before-caller (zero forward references, verified), so runtime gates install it verbatim — there is deliberately no `convert_hoist.py` transform (CORE BLOCKER C).
