# OpenWrt Performance Manager

> Capability-first, topology-aware, transactional performance control plane for OpenWrt.

**Target:** OpenWrt 25.12.x / x86_64
**Current source candidate:** `1.0.0-rc.2`
**Safety posture:** Conservative by default; no silent WAN saturation; Rill is Shadow-only and has no apply authority.

Performance Manager discovers, understands, orchestrates, verifies and learns from performance capabilities already present in OpenWrt. It is not a sysctl preset bundle and does not replace native providers when OpenWrt already has a mature implementation.

## Implemented scope

- Stable TargetRef + topology/path/workload model, including PPPoE/VPN underlay-safe device targeting.
- Native OpenWrt Packet Steering discovery / observe / respect.
- Hyper-V `hv_netvsc` conservative ring-floor policy with TargetRef replay.
- NIC offload protection observations and integration guards.
- Telemetry, evidence/confidence Analyzer, baseline-relative System Health Guard, resource locks, durable pending markers, verified rollback and real monotonic commit-confirm engine.
- Phase-7 benchmark orchestrator/catalog for irqbalance, backlog/budget, buffers, busy poll, tx queue, coalescing, CC, qdisc, SFO/HFO/SFE and CPU governor; providers execute only when an exact reversible contract is available.
- Controlled A/B truthfulness: persisted control evidence → one-variable transactional candidate → candidate evidence → verified rollback → result persistence → optional Rill outcome; missing/invalid evidence never becomes `validated=true`.
- Rill Shadow learning: context drift, weighted validated-outcome bandit, Decision Ledger, model health and advisory-only recommendations.
- Assisted Auto as explicit opt-in only: maintenance window + low-traffic gate + safe allowlist.
- Generic x86, Hyper-V and KVM/Proxmox-compatible guest guidance.
- Explicit Companion Agent for LAN/WAN iperf3 endpoint evidence; it cannot mutate router state.
- Supported-first LuCI UI with Simplified Chinese translation.

## Packages

| Package | Purpose |
|---|---|
| `performance-manager` | procd-managed ucode/ubus Core, contracts, discovery, telemetry, transaction engine and safe actions |
| `luci-app-performance-manager` | Supported-first LuCI UI |
| `performance-manager-rill` | Dedicated-user Rust Shadow learning sidecar over bounded UDS |

## Safety invariants

- Core has no hard dependency on LuCI/rpcd/Rill.
- Rill accepts only the root Core peer over UDS, cannot execute commands and cannot write UCI/sysctl/firewall state.
- Direct apply uses a fixed safe Action allowlist; benchmark-class actions are not silently promoted into direct writes.
- Existing user/external/preexisting state takes precedence; uninstall restores only a current PM-owned runtime lease and never stale-rolls back over live drift.
- Transactions verify read-back and baseline-relative health. Failed restore is recorded as failure rather than a successful rollback.
- Ordinary telemetry and topology refreshes stay in tmpfs; persistent history is bounded.
- Passive/health benchmark observations remain `validated=false`; only genuine validated outcomes may update Rill learning.

## Build in an OpenWrt SDK/buildroot

```sh
mkdir -p package/openwrt-performance-manager
cp -a /path/to/openwrt-performance-manager/package/* package/openwrt-performance-manager/
./scripts/feeds update -a
./scripts/feeds install -a
make defconfig
make package/performance-manager/compile V=s
make package/luci-app-performance-manager/compile V=s
make package/performance-manager-rill/compile V=s
```

## Runtime API

```sh
ubus call performance-manager status '{}'
ubus call performance-manager capabilities '{}'
ubus call performance-manager topology '{}'
ubus call performance-manager recommendations '{}'
ubus call performance-manager transactions '{}'
ubus call performance-manager diagnostics '{}'
```

A currently legal safe action can be applied only by Action ID + resolved TargetRef:

```sh
ubus call performance-manager apply '{"actionId":"nic.ring.floor","target":"<stableId>"}'
```

## Development / audit

```sh
make audit
make package
```

Booted target evidence is produced by `scripts/openwrt-target-gate.sh`; the default 24h resource/write gate is `scripts/openwrt-resource-soak.sh`. Mutating the target gate requires explicit `PM_ALLOW_MUTATION=1`.

Start with `docs/IMPLEMENTATION_STATUS.md`, `docs/ARCHITECTURE.md`, `docs/RELEASE_CHECKLIST.md` and the immutable planning pack in `docs/planning-v0.3.2/`.

> `1.0.0-rc.2` is intentionally not called Stable until the official OpenWrt SDK/runtime/soak and real forwarding A/B gates have actually passed. See `docs/EXTERNAL_VALIDATION.md`. Target evidence includes `scripts/openwrt-target-gate.sh`, the two-stage `scripts/openwrt-sysupgrade-gate.sh`, and `scripts/openwrt-resource-soak.sh`.
