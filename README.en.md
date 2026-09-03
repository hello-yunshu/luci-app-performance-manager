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
- **Rill Runtime v3 Smart Decision**: an external `rill-runtime` ranks a stable feature vector; Core owns the unified Conservative/Assisted selector, safe allowlist, `pm.noop`, confidence, drift and cooldown gates, and never delegates actuation authority
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

## OpenWrt packages

| Package | Purpose |
|---|---|
| `performance-manager` | procd-managed ucode/ubus Core: contracts, discovery, telemetry, transaction engine and safe actions |
| `luci-app-performance-manager` | Supported-first LuCI UI (Simplified Chinese) |
| `performance-manager-rill` | External Runtime integration glue; the Rill Runtime package owns `/usr/bin/rill-runtime` |
| `luci-app-performance-manager-all` | Recommended all-in-one APK: physically contains Core, LuCI, rpcd ACL/menu and Simplified Chinese translation |

## Installation

### Prerequisites

- OpenWrt 25.12.x / x86_64, aarch64_generic, or aarch64_cortex-a53; current real runtime gates remain x86_64-scoped
- An OpenWrt SDK or buildroot environment (for source builds)

### Build from source (OpenWrt SDK / buildroot)

```sh
# 1. Provide the external Rill Runtime from the Rill OpenWrt feed
cd /path/to/openwrt-performance-manager
# 2. Then enter the OpenWrt SDK
cd /path/to/openwrt-sdk
./scripts/feeds update -a
./scripts/feeds install -a
mkdir -p package/openwrt-performance-manager
cp -a /path/to/openwrt-performance-manager/package/* package/openwrt-performance-manager/
make defconfig
make package/performance-manager/compile V=s
make package/luci-app-performance-manager/compile V=s
make package/performance-manager-rill/compile V=s
make package/luci-app-performance-manager-all/compile V=s
```

The Rill package is an external-runtime integration boundary; this repository does not build or vendor Rust Runtime source. Install the matching external `/usr/bin/rill-runtime` package together with `luci-app-performance-manager-all`.

> You can also rely on the GitHub Actions `build-openwrt.yml` → `openwrt-sdk-build` job to produce the build instead of using a local SDK.

### Recommended: one-APK installation

Download `luci-app-performance-manager-all-1.0.4-r1.apk` and `performance-manager-rill-1.0.4-r1.apk` from the GitHub Release, plus the matching external `rill-runtime` package from the Rill OpenWrt feed. The Runtime package is not built or copied by this repository.

```text
performance-manager-rill-1.0.4-r1.apk
rill-runtime-<matching-target>.apk
```

```sh
apk add --allow-untrusted /tmp/luci-app-performance-manager-all-1.0.4-r1.apk
apk add --allow-untrusted /tmp/rill-runtime-1.5.6-r1.apk /tmp/performance-manager-rill-1.0.4-r1.apk
```

Install the qualified external `rill-runtime` for the device architecture before the `performance-manager-rill` glue package. If the package manager resolves dependencies, it must preserve the same Runtime-before-glue requirement; a missing Runtime remains fail-closed.

OpenWrt still resolves system runtime libraries such as `luci-base`, `rpcd` and `ucode` from its configured repositories. The all-in-one APK contains the Core, LuCI, backend and translation payloads; the external Runtime owns `/usr/bin/rill-runtime`, while the small `performance-manager-rill` package owns only integration glue. Back up `/etc/config/performance-manager` and switch package forms only during a maintenance window.

### Package info

| Item | Value |
|---|---|
| Recommended package | `luci-app-performance-manager-all` (one APK) |
| Target | OpenWrt 25.12.5 / x86_64, aarch64_generic, aarch64_cortex-a53 (package-level); runtime evidence is x86_64 |
| Current source candidate | `1.0.4` |
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
| Rill Intelligence | Runtime advisory model and decision ledger |
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

package/luci-app-performance-manager-all/Makefile  # merges all owned runtime content and compiled zh-cn LMO into one APK
```

## Architecture

```text
┌──────────────┐ ubus/rpcd ┌────────────────────────┐
│   LuCI UI    │ ─────────→ │  performance-manager   │
│  (8 views)   │ ←───────── │  Core (ucode/ubus)     │
└──────────────┘  JSON     └───────────┬────────────┘
                                      │ UDS (bounded, Runtime v3)
                          ┌───────────▼────────────┐
                          │ performance-manager-rill │
                          │   (external glue)        │
                          └───────────┬────────────┘
                                      │ generic Runtime v3
                          ┌───────────▼────────────┐
                          │ external rill-runtime     │
                          │ ranking, no actuator      │
                          └────────────────────────┘
```

> **Consumer ownership boundary.** Performance Manager owns the Core selector, feature mapping, Smart v2 state and UI. The external Rill Runtime owns only generic ranking/learning and its binary; it cannot apply router changes. Core remains fail-closed when the Runtime is missing or incompatible.

## MacBook + Docker local Portable validation

Run the repeatable repository-software validation before pushing:

```sh
make portable-macos
# or: tools/docker-validate/run-local-macos.sh
```

Prerequisites are Docker Desktop, Git, Python 3, an authenticated `gh` CLI, and network access to GitHub / OpenWrt. The same-SHA CI and same-SHA Build for the current commit must already have completed successfully. The first run automatically downloads and verifies the OpenWrt 25.12.5 x86_64 rootfs; later runs may reuse the rootfs cache, but always re-check it against the official `sha256sums`. If the same-SHA Build is not complete, the result is `BLOCKED`, not a project-code `FAIL`.

The entry point reuses the existing source audit, OpenWrt ucode harness, artifact identity, package-composition gate, and portable gate. Run evidence is written to untracked `local-evidence/` and bound to the current commit SHA; package artifacts must come from a same-SHA GitHub Actions Build, never from `latest` or an older branch cache.

`Mac Docker PASS != Hardware Stable PASS`. Portable evidence always reports `hardwareCoverage = NOT_EVALUATED` and `stableReleaseAuthorized = false`; it cannot cover real NIC behavior, Hyper-V/KVM, LAN-WAN, sysupgrade, reboot, or a real-router 24-hour soak. If Docker Desktop, linux/amd64 emulation, network downloads, or same-SHA artifacts are unavailable, the entry point reports a diagnostic `BLOCKED` instead of fabricating PASS.

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

### rill section (Runtime v3)

| Option | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | 1 | enable external Runtime |
| `mode` | fixed semantic | advisory | advisory ranking only, no apply authority; legacy `shadow` is read once by upgrade migration |
| `binary` | string | (empty) | external Runtime path; empty uses `/usr/bin/rill-runtime` |
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

**`ci.yml` (source, behavior, contract & Runtime v3 verification)**
- **static**: unit tests + contract validation + source gates + final audit + LuCI JS syntax & render smoke
- **rill-runtime-v3**: verifies the generic Runtime v3 handshake/health/decide/feedback contract and fail-closed behavior
- **openwrt-ucode**: compiles and validates Core ucode inside the official OpenWrt 25.12.5 rootfs

**`build-openwrt.yml` (remote official SDK build)**
- **openwrt-sdk-build**: builds the split Core/LuCI/glue packages plus the all-in-one APK with the official SDK, and emits `build-metadata.json`, `checksums.txt` and audit-evidence artifacts

> The generic Runtime binary is intentionally external. This repository validates the Runtime v3 boundary and does not build, vendor or release a PM-owned Rust adapter.

Local quick verification:

```sh
make audit          # unit tests + contract validation + source gates + final audit
make package        # build release artifacts
```

- On-target gate: `scripts/openwrt-target-gate.sh`
- Resource / write soak: `scripts/openwrt-resource-soak.sh`
- External validation evidence: `docs/EXTERNAL_VALIDATION.md`

> Historical public `1.0.3` uses the explicit `portable-docker` release profile and does not claim Hyper-V, real-router A/B, firmware sysupgrade, or 24-hour soak coverage. Current `1.0.4` and later Stable releases require every `hardware` gate to pass; the external `rill-runtime` package is qualified and published by its own feed.

## Documentation

- `docs/ARCHITECTURE.md` · `docs/IMPLEMENTATION_STATUS.md` · `docs/RELEASE_CHECKLIST.md`
- `docs/EXTERNAL_VALIDATION.md`

## License

This project is licensed under **GNU GPL v3.0-only** ([LICENSE](LICENSE)). As free software you may use, modify and redistribute it, but any modified version must also be released under GPL-3.0 with the corresponding source code.
