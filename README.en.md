# luci-app-performance-manager

[中文](README.md) | **English**

<p align="center">
  <img src="logo.png" alt="OpenWrt Performance Manager" width="480">
</p>

<p align="center">
  <strong>A capability-first, topology-aware, transactional performance control plane for OpenWrt</strong>
</p>

<p align="center">
  OpenWrt Performance Manager first discovers the capabilities already present in OpenWrt, drivers and the platform, then resolves Topology / TargetRef / Path / Workload. A legitimate Action only exists after passing Policy, Compatibility, Locks and Health Guard checks, and is executed through a closed loop of transactions, read-back, health verification and rollback. It is not a sysctl preset bundle, and it never replaces native providers when OpenWrt already has a mature implementation.
</p>

---

## Features

- **Capability-first**: stable TargetRef so long-lived policies never bind to `eth0`; PPPoE / VPN scenarios resolve the real underlay first
- **Topology-aware**: route / policy-route evidence and rtnl events feed the topology, path and workload model
- **Native Packet Steering**: discover / observe / respect OpenWrt's native implementation, never rewrite the algorithm
- **NIC offload protection**: observe / protect, compatible with OpenClash / PassWall / HomeProxy / SQM / qosify / mwan3 / pbr / VPN / Docker discovery
- **Hyper-V safe policy**: conservative `hv_netvsc` 1024 ring floor with boot / device / topology replay
- **Telemetry + Health Guard**: evidence/confidence Analyzer, baseline-relative health gate, resource locks, durable pending markers, verified rollback and a real monotonic commit-confirm engine
- **Phase-7 benchmark orchestration**: irqbalance, backlog/budget, buffers, busy poll, tx queue, coalescing, CC, qdisc, SFO/HFO/SFE and CPU governor; providers run only when an exact reversible contract exists
- **Controlled A/B truthfulness**: persisted control evidence → one-variable transactional candidate → candidate evidence → verified rollback → result persistence → optional Rill outcome; missing/invalid evidence never becomes `validated=true`
- **Rill Shadow learning**: Rill is an external runtime dependency built and released by its upstream repository; PM only consumes its advisory through a bounded shadow-only IPC protocol (context drift detection, validated-outcome weighting, Decision Ledger, model health), failing closed without faking recommendations when Rill is missing or incompatible
- **Assisted Auto**: explicit opt-in only — maintenance window + low-traffic gate + safe allowlist
- **Multi-platform guidance**: generic x86, Hyper-V and KVM (including Proxmox VE guest guidance)
- **Companion Agent**: an explicit LAN/WAN iperf3 endpoint tool with no router-mutation authority
- **LuCI Supported-first UI** with Simplified Chinese translation

## Safety invariants

- Core has no hard dependency on LuCI / rpcd / Rill and runs standalone
- Rill accepts only the root Core peer over UDS, cannot execute commands and cannot write UCI / sysctl / firewall
- Direct apply uses a fixed safe Action allowlist; benchmark-class actions are never silently promoted into direct writes
- Existing user / external / preexisting state takes precedence; uninstall restores only a current PM-owned runtime lease and never stale-rolls back over live drift
- Transactions verify read-back and baseline-relative health; a failed restore is recorded as a failure, not a successful rollback
- Ordinary telemetry and topology refreshes stay in tmpfs; persistent history is bounded
- Passive / health benchmark observations remain `validated=false`; only genuine validated outcomes update Rill learning

## The three OpenWrt packages

| Package | Purpose |
|---|---|
| `performance-manager` | procd-managed ucode/ubus Core: contracts, discovery, telemetry, transaction engine and safe actions |
| `luci-app-performance-manager` | Supported-first LuCI UI (Simplified Chinese) |
| `performance-manager-rill` | PM ↔ upstream Rill integration glue: consumes the upstream Rill release only, never compiles Rill |

## Installation

### Prerequisites

- OpenWrt 25.12.x / x86_64
- An OpenWrt SDK or buildroot environment (for source builds)

### Build from source (OpenWrt SDK / buildroot)

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

> You can also rely on the GitHub Actions `build-openwrt.yml` → `openwrt-sdk-build` job to produce the build instead of using a local SDK.

### Package info

| Item | Value |
|---|---|
| Package name | `luci-app-performance-manager` (Core: `performance-manager`) |
| Target | OpenWrt 25.12.x / x86_64 |
| Current source candidate | `1.0.0-rc.6` |
| Service script | `/etc/init.d/performance-manager` |
| UCI config | `/etc/config/performance-manager` |
| Core binary | `/usr/sbin/performance-manager.uc` |
| RPC backend | `performance-manager` (`ubus call performance-manager <method>`) |

### Dependencies

```text
ucode ucode-mod-ubus ucode-mod-uci ucode-mod-rtnl ucode-mod-uloop ucode-mod-jsonc ubusd rpcd luci-base
```

## Usage

### LuCI UI (Network → Performance Manager)

The UI is Simplified-Chinese-first and automatically follows the OpenWrt/LuCI system language setting: choose Chinese in LuCI "System → Language and Style" for Chinese, or English for English (English is the secondary language and the fallback for unmatched locales).

| Page | Description |
|---|---|
| Overview | runtime status, health and recent transaction overview |
| Smart Optimization | recommended actions and safe apply |
| Performance Test | Phase-7 controlled benchmark orchestration |
| Capabilities | capability / topology / TargetRef views |
| Rill Intelligence | shadow learning model and decision ledger |
| History & Rollback | history and rollback |
| Settings / Advanced | configuration |

### Runtime API

```sh
ubus call performance-manager status '{}'
ubus call performance-manager capabilities '{}'
ubus call performance-manager topology '{}'
ubus call performance-manager targets '{}'
ubus call performance-manager paths '{}'
ubus call performance-manager analyze '{}'
ubus call performance-manager recommendations '{}'
ubus call performance-manager transactions '{}'
ubus call performance-manager locks '{}'
ubus call performance-manager history '{"limit":100}'
ubus call performance-manager diagnostics '{}'
ubus call performance-manager rill_status '{}'
```

A currently legal safe action is applied only by Action ID + resolved TargetRef:

```sh
ubus call performance-manager apply '{"actionId":"nic.ring.floor","target":"<stableId>"}'
ubus call performance-manager confirm '{"transactionId":"<tx>"}'
ubus call performance-manager rollback '{"transactionId":"<tx>"}'
```

Benchmark lifecycle:

```sh
ubus call performance-manager benchmark_start '{"measurementClass":"controlled_ab"}'
ubus call performance-manager benchmark_status '{"sessionId":"<session>"}'
ubus call performance-manager benchmark_stop '{"sessionId":"<session>"}'
```

## Project structure

```text
package/performance-manager/files/
├── etc/
│   ├── config/performance-manager    # UCI config
│   ├── init.d/performance-manager    # procd service script
│   └── uci-defaults/90-performance-manager
├── lib/upgrade/keep.d/performance-manager
└── usr/
    ├── sbin/performance-manager.uc   # Core (ucode/ubus)
    └── share/performance-manager/
        ├── contracts.uc              # safe action contracts
        ├── profiles/                 # capability profiles
        └── schemas/                  # JSON schemas (validation)

package/luci-app-performance-manager/
├── htdocs/luci-static/resources/performance-manager/   # api.js / ui.js
├── htdocs/luci-static/resources/view/performance-manager/  # 8 views
├── po/zh_Hans/                        # Simplified Chinese translation
└── root/usr/share/luci/menu.d/        # LuCI menu registration
```

## Architecture

```text
┌──────────────┐ ubus/rpcd ┌────────────────────────┐
│   LuCI UI    │ ─────────→ │  performance-manager   │
│  (8 views)   │ ←───────── │  Core (ucode/ubus)     │
└──────────────┘  JSON     └───────────┬────────────┘
                                      │ UDS (bounded, shadow-only)
                          ┌───────────▼────────────┐
                          │ performance-manager-rill │
                          │   (integration glue)     │
                          └───────────┬────────────┘
                                      │ consumes upstream release
                          ┌───────────▼────────────┐
                          │   Rill upstream runtime │
                          │ (built/released upstream)│
                          └────────────────────────┘
```

> **Rill is an external runtime dependency.** Rill's source, Rust toolchain, cross-platform compilation and binary release all belong to the Rill upstream repository; this repository does not vendor, compile or natively test Rill's Rust implementation. `performance-manager-rill` is PM-specific integration glue (fail-closed capability gate + service glue) that only consumes and verifies the upstream release artifact.

**Data flow**:

1. Core discovers capabilities and topology through ubus / rtnl / uci and keeps stable TargetRefs
2. The UI queries status / capabilities / recommendations via `ubus call performance-manager <method>`
3. Legal actions run through the transaction engine: read-back → health verification → commit-confirm → rollback when needed
4. Validated outcomes optionally feed Rill; Rill only returns advisory output; Core stays healthy and fails closed when Rill is missing / protocol-incompatible

## UCI configuration reference

### core section (main)

| Option | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | 1 | Enable Core |
| `automation` | enum | conservative | automation level |
| `assisted_auto` | boolean | 0 | explicit Assisted Auto opt-in (second confirmation) |
| `maintenance_start` / `maintenance_end` | string | 03:00 / 05:00 | maintenance window |
| `goal` | enum | balanced | optimization goal |
| `profile` | string | recommended | capability profile |
| `telemetry` / `history` | boolean | 1 | collection and persistent history toggles |
| `telemetry_interval` / `deep_interval` | integer | 45 / 600 | sampling interval (seconds) |
| `commit_confirm_seconds` | integer | 30 | commit-confirm window |
| `state_dir` | string | /tmp/performance-manager | runtime state (tmpfs) |
| `persistent_dir` | string | /etc/performance-manager | persistent directory |
| `health_dns_name` | string | openwrt.org | health-check DNS target |
| `oom_window_seconds` / `max_load_per_cpu` / `max_cpu_steal_percent` / `max_thermal_millicelsius` | integer | 600 / 2 / 20 / 90000 | health gate thresholds |

### rill section (shadow)

| Option | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | 1 | enable Rill Shadow |
| `mode` | enum | shadow | read-only learning, no apply authority |
| `socket` | string | /run/performance-manager/rill.sock | UDS path |
| `max_message` | integer | 65536 | max message bytes |
| `timeout_ms` | integer | 1000 | call timeout |
| `state_dir` | string | /etc/performance-manager/rill | Rill persistent state |

### benchmark section

| Option | Type | Default | Description |
|---|---|---|---|
| `require_explicit_start` | boolean | 1 | benchmark must be started explicitly |
| `one_variable` | boolean | 1 | one-variable controlled A/B |
| `allow_background_saturation` | boolean | 0 | background WAN saturation not allowed |
| `default_measurement_class` | enum | passive_before_after | default measurement class |
| `candidate_timeout_seconds` | integer | 120 | candidate timeout |
| `session_idle_seconds` | integer | 600 | session idle timeout |

## Build and audit

This project is built and verified automatically with GitHub Actions, triggered by pushing to main or manually:

**`ci.yml` (source & behavior audit, non-compiling)**
- **static**: unit tests + contract validation + source gates + final audit + LuCI JS syntax & render smoke
- **rill-contract**: verifies the PM ↔ upstream Rill dependency contract and pinned upstream release provenance (never compiles Rill), and emits `rill-consumed-manifest.json`
- **openwrt-ucode**: compiles and validates Core ucode inside the official OpenWrt 25.12.5 rootfs

**`build-openwrt.yml` (remote official SDK build)**
- **openwrt-sdk-build**: builds the three packages this repository owns (Core / LuCI / integration glue) with the official SDK, and emits `build-metadata.json`, `checksums.txt` and audit-evidence artifacts

> This repository no longer has a `rill-native` / Rill SDK build job: no Rust toolchain is installed to compile Rill. Rill's native build and tests are the responsibility of the Rill upstream repository's Actions.

Local quick verification:

```sh
make audit          # unit tests + contract validation + source gates + final audit
make package        # build release artifacts
```

- On-target gate: `scripts/openwrt-target-gate.sh`
- Resource / write soak: `scripts/openwrt-resource-soak.sh`
- External validation evidence: `docs/EXTERNAL_VALIDATION.md`

> `1.0.0-rc.6` is intentionally not called Stable until the official OpenWrt SDK / runtime / soak and real forwarding A/B gates have actually passed. See `docs/RELEASE_CHECKLIST.md` and `docs/EXTERNAL_VALIDATION.md`.

## Documentation

- `docs/ARCHITECTURE.md` · `docs/IMPLEMENTATION_STATUS.md` · `docs/RELEASE_CHECKLIST.md`
- `docs/EXTERNAL_VALIDATION.md`

## License

This project is licensed under **GNU GPL v3.0-only** ([LICENSE](LICENSE)). As free software you may use, modify and redistribute it, but any modified version must also be released under GPL-3.0 with the corresponding source code.
