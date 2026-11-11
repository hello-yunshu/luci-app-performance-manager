# Roadmap

Planning pack v0.3.2 is contract-frozen. Smart Decision v2 adds the unified Core selector, Runtime v3 feature/reward contract, fail-closed learning stages, confidence/drift/cooldown gates, explainability and LuCI refresh/status surfaces. Rill remains an external Runtime dependency; this repository does not vendor a PM-owned adapter or Rust Runtime source. The remaining work is same-commit validation across local, CI and target evidence.

> 审计问题收敛计划（5 阶段，按依赖排序）：[docs/plans/2026-11-09-audit-convergence-plan.md](docs/plans/2026-11-09-audit-convergence-plan.md)。

1. Pass the CI gates on official OpenWrt 25.12.5: `ci.yml` job IDs `static`, `rill-runtime-v3` and `production-core-rill-integration` (the last one boots the official ucode rootfs and exercises the raw shipped Core), plus `build-openwrt.yml` job `openwrt-sdk-build` (which also emits build-metadata.json + checksums.txt evidence).
2. Pass booted-target evidence on clean x86_64 OpenWrt 25.12.x VMs, including Core without LuCI/Rill dependency.
3. Pass Hyper-V and KVM/Proxmox TargetRef, hotplug, replay, rollback and ownership-cleanup tests.
4. Run explicit LAN→Router→WAN and router-local controlled A/B for supported benchmark providers.
5. Pass package upgrade/sysupgrade and 12h+ resource/write soak.
6. Treat public `1.0.3` as the historical portable release; do not relabel or
   mutate it as Hardware Stable.
7. Authorize a current `1.0.4` Stable release only when all hardware evidence
   is attached and independently auditable.

New optimizers stay backlog-only until Stable gates pass.
