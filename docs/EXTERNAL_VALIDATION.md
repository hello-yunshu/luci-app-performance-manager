# External Validation Required for 1.0 Stable

`1.0.0-rc.5` closes the source blockers found by the strict rc.1 audit, the 2026-08-14 independent re-audit, and the 2026-08-16 rc.4 single-repo remediation (including the real Core ucode runtime harness), but Stable still requires evidence that cannot be fabricated inside the current offline/non-OpenWrt assembly container.

The current official 25.12.x x86/64 target is available as OpenWrt 25.12.5, including an x86/64 rootfs and SDK. CI is pinned to that release for ucode and three-package build gates.

Required target evidence:

1. GitHub CI: the `.github/workflows/ci.yml` source/behavior jobs — `static` (incl. the LuCI render smoke harness `scripts/luci_render_smoke.js`), `rill-contract` (contract + pinned upstream release provenance, no Rust toolchain), `openwrt-ucode` (official OpenWrt 25.12.5 rootfs ucode compile of Core) — plus the remote official SDK build in `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (builds only packages this repository owns and emits build-metadata.json + checksums.txt evidence). Rill itself is external, so there is no native Rust build here.
2. Booted OpenWrt 25.12.x x86_64 VM: `scripts/openwrt-target-gate.sh`.
3. Hyper-V and KVM/Proxmox guest hotplug/TargetRef/replay/rollback fixtures.
4. Explicit LAN→Router→WAN and router-local controlled A/B sessions where the action semantics require them.
5. Sysupgrade preservation via `scripts/openwrt-sysupgrade-gate.sh prepare` before the upgrade and `verify` after reboot, plus `scripts/openwrt-resource-soak.sh` for 24h or longer.

Until those evidence files actually pass, the correct label is **1.0.0-rc.5**, not Stable.

## Docker-based Evidence Progress

Validation can be driven locally from the official 25.12.5 x86/64 rootfs via Docker (see `tools/docker-validate/`), which removes the "offline / non-OpenWrt" blocker for runtime gates. Evidence artifacts are collected in `evidence/`.

Status:

- **1. GitHub CI** — owned by `.github/workflows/ci.yml` (`static` incl. LuCI render smoke, `rill-contract` with pinned upstream Rill provenance, `openwrt-ucode` official 25.12.5 rootfs compile of Core) and `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build` (official SDK builds only the packages this repository owns: `performance-manager`, `luci-app-performance-manager`, `performance-manager-rill`; emits build-metadata.json + checksums.txt). No local SDK build is required, and no native Rust build is performed.
- **2. Booted OpenWrt runtime gate** — PASSED inside the `owrt-pm-gate` container (25.12.5 x86/64): `scripts/openwrt-target-gate.sh` CORE-ONLY, 11/11 assertions green. Evidence: `evidence/openwrt-target-gate-25.12.5.json`.
- **5. Resource soak (dev check)** — script viability verified for 120s (12 samples): `coreMaxRssKiB` 4744, `coreMeanCpuPercentApprox` 0.083, 0 persistent writes, `executionPassed true`. This is a development check only; the 24h+ Stable gate (`stableDurationSatisfied`) remains outstanding. Evidence: `evidence/openwrt-resource-soak-120s-dev.json`.

Not yet satisfied (require real hypervisor or router hardware): items 3 (Hyper-V/KVM fixtures) and 4 (LAN/WAN A/B sessions), plus the full 24h soak and sysupgrade round-trip from item 5.

Docker notes: the OpenWrt container's netifd bridges `eth0` into `br-lan` and drops the docker default route, so it is offline by design; gates must not depend on `apk add`. The container busybox lacks float sleep, so `tools/docker-validate/sleep-shim` is installed ahead of the gate. The shipped Core is written callee-before-caller (zero forward references, verified), so runtime gates install it verbatim — there is deliberately no `convert_hoist.py` transform (CORE BLOCKER C).
