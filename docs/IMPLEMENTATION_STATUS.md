# Implementation Status — 1.0.0-rc.2

This repository implements the frozen planning pack v0.3.2 through Phase 12 as a **source-complete release candidate** after the strict rc.1 re-audit and the 2026-08-14 independent re-audit hardening. “Source-complete” means the required contracts, runtime mechanisms, UI surfaces, guards, tests and target-evidence tooling exist; it does **not** claim that target/testbed gates have already passed. The independent re-audit closed: benchmark tuning-domain exclusivity (global lock + idle/stale recovery), full context fingerprint with candidate-key masking, strict non-fallback evaluation paths with a resolved-route hard gate, path-specific health, the Rill contextual bandit with formal per-op v2 IPC schema and strict JSON parsing, the target-bound Assisted Auto traffic gate, fail-closed uninstall cleanup, pinned CI toolchain/feeds, behavioral source gates and the self-contained final audit orchestrator.

| Phase | Source status | Evidence / boundary |
|---|---|---|
| 0 Contract Freeze | Complete | formal schemas + runtime copies/constants; frozen planning pack unchanged |
| 1 Bootstrap | Complete | independent Core, LuCI, Rill packages; procd/ubus; i18n; CI |
| 2 Capability/Topology/Target/Event | Complete | stable TargetRef, PPPoE/VPN underlay, multi-WAN paths, route/rule identity, netifd + rtnl events |
| 3 Telemetry/Health/Analyzer/Path | Complete | fast/deep telemetry, full baseline-relative health, structured evidence/confidence Analyzer |
| 4 Policy/Compatibility | Complete | integrations, provider/ownership posture and multi-WAN/fast-path guards |
| 5 Transaction/Locks/Commit-confirm | Complete | full state machine, durable pending marker, real monotonic deadline/timer, crash recovery, stale-safe rollback, per-boot ownership lease, uninstall cleanup and fail-closed prerm (removal aborts unless the daemon confirms `ok:true`); benchmark experiment locks recovered on daemon start/cleanup |
| 6 Conservative | Complete | Hyper-V ring floor; Native Packet Steering observe/respect; NIC offload observe/protect |
| 7 Benchmark | Complete under capability-first rule | global `benchmark:global` tuning-domain lock (acquire-before-session-write, release on every terminal path, idle-expiry recovery), full context fingerprint with candidate-key masking and `benchmark-context-drift`, strict non-fallback evaluation path, forwarding requires resolved rtnl route (`evaluation-route-unresolved`), path-specific health, real control→candidate→rollback→reward orchestrator; exact reversible providers execute; generic qdisc/unknown SFE remain explicitly blocked when exact restore is not provable |
| 8 Rill Intelligence | Complete | formal per-op v2 IPC schema (`ctx-v1:` ContextKey binding), strict dependency-free JSON parser, context-partitioned model keyed by Core-computed ContextKey, per-operation validation, stale-recommendation invalidation on drift, bounded persistent ledger/model, strict Shadow protocol |
| 9 Recommend | Complete | deterministic legal actions + separate Rill advisory with no actuation authority |
| 10 Assisted Auto | Complete, opt-in only | assisted + explicit switch + maintenance + Health Guard + safe allowlist; low-traffic gate bound to the selected action's own target runtime (`assisted-previous-<runtime>.json`), action chosen before gating |
| 11 Platforms | Complete for RC | Generic x86, Hyper-V, KVM/Proxmox-compatible guest detection/guidance |
| 12 Companion | Complete | `pm-companion/v2` endpoint evidence, exact context binding, no router mutation |

## Stable-only evidence still required

1. Official OpenWrt 25.12.x x86_64 rootfs/SDK and native Rust CI must actually pass.
2. Core-alone boot/runtime on real OpenWrt must pass.
3. Hyper-V and KVM hotplug/TargetRef/replay/rollback fixtures must pass.
4. Explicit forwarding/router-local A/B testbeds must pass.
5. Sysupgrade and 24h+ resource/write soak must pass.

Use `scripts/openwrt-target-gate.sh`, `scripts/openwrt-sysupgrade-gate.sh`, `scripts/openwrt-resource-soak.sh` and `docs/RELEASE_CHECKLIST.md`. These are target evidence gates, not unresolved source placeholders.
