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
| `performance-manager`, `luci-app-performance-manager`, `performance-manager-rill` | Split source and migration packages; use the single PM package for new installs |
| `rill-runtime-manager` | Shared Runtime LuCI/RPC install, refresh, and update controller |
| `rill-runtime` | Canonical shared Stable Runtime package; uniquely owns `/usr/bin/rill-runtime` |
| `luci-app-performance-manager-all` | Only recommended PM package, containing Core, LuCI, ACL/menu, Simplified Chinese, Rill glue and compatibility manifest; depends on shared Runtime and never bundles its binary |

## Installation

### Prerequisites

- OpenWrt 24.10.8 IPK and 25.12.6 APK target matrix across x86_64, aarch64_generic, aarch64_cortex-a53/a72/a76, and arm_cortex-a7_neon-vfpv4; verify published artifacts for each target
- An OpenWrt SDK or buildroot environment (for source builds)

### Build from source (OpenWrt SDK / buildroot)

```sh
# 1. The canonical Rill feed provides the shared Runtime and package manager
cd /path/to/openwrt-performance-manager
# 2. Then enter the OpenWrt SDK
cd /path/to/openwrt-sdk
./scripts/feeds update -a
./scripts/feeds install -a
mkdir -p package/openwrt-performance-manager
cp -a /path/to/openwrt-performance-manager/package/* package/openwrt-performance-manager/
make defconfig
make package/rill-runtime-manager/compile V=s
make package/rill-runtime/compile V=s
make package/performance-manager/compile V=s
make package/luci-app-performance-manager/compile V=s
make package/performance-manager-rill/compile V=s
make package/luci-app-performance-manager-all/compile V=s
```

The unified PM package depends on the shared Runtime manager and Stable Runtime; it does not contain the Runtime binary. Use the official GitHub Actions SDK workflow and check that CI has verified the target.

> You can also rely on the GitHub Actions `build-openwrt.yml` → `openwrt-sdk-build` job to produce the build instead of using a local SDK.

### Recommended: one unified PM package per device

From [GitHub Releases](https://github.com/hello-yunshu/luci-app-performance-manager/releases), select one `luci-app-performance-manager-all` package matching the OpenWrt release, package format, and device architecture. The Rill page provides Runtime install and update actions.

The unified PM package contains Performance Manager Core, LuCI, Simplified Chinese, and Rill integration. It resolves the shared `rill-runtime` dependency from the configured feed. If legacy `rill-runtime-preview` is installed, the package manager rejects migration; review its other consumers and plan migration manually. It will not be removed or overwritten automatically.

```sh
# OpenWrt 24.10.8
opkg install /tmp/performance-manager-all-v<VERSION>-openwrt-24.10.8-x86_64.ipk
# OpenWrt 25.12.6
apk add --allow-untrusted /tmp/performance-manager-all-v<VERSION>-openwrt-25.12.6-x86_64.apk
```

Mainstream targets are `x86_64`, `aarch64_generic`, `aarch64_cortex-a53`, `aarch64_cortex-a72`, `aarch64_cortex-a76`, and `arm_cortex-a7_neon-vfpv4`. Install only an artifact matching the device release, package format, and architecture.

OpenWrt resolves system libraries, `rill-runtime-manager`, and shared `rill-runtime` from configured repositories. The unified package conflicts with legacy PM split owners and `rill-runtime-preview`; conflicts reject installation without removing packages automatically.

If `luci-app-performance-manager-all` is already installed, the package name is unchanged and it can be upgraded through a configured feed; do not uninstall PM first or manually delete `/usr/bin/rill-runtime`. Historical full packages bundled Runtime in the PM package, while the new package transfers ownership to the separate `rill-runtime` package. The existing APK upgrade gate exercises a same-name upgrade from a lower-version synthetic package containing the Runtime file and checks config preservation; it is not a test against a historical release artifact. The OpenWrt 24.10 opkg same-name upgrade still needs a real SDK/rootfs run.

When the page detects the legacy Preview Runtime, it shows the package owner and version plus these manual steps. First confirm no other packages depend on `rill-runtime-preview`, back up PM configuration and data, then during a maintenance window remove the old PM bundle and Preview package before installing the current bundle from the configured feed:

```sh
# OpenWrt 24.10 (opkg)
cp -a /etc/config/performance-manager /root/performance-manager.config.backup
tar -czf /root/performance-manager-data.backup.tgz /etc/performance-manager
opkg remove luci-app-performance-manager-all rill-runtime-preview
opkg update
opkg install luci-app-performance-manager-all

# OpenWrt 25.12 (apk)
cp -a /etc/config/performance-manager /root/performance-manager.config.backup
tar -czf /root/performance-manager-data.backup.tgz /etc/performance-manager
apk del luci-app-performance-manager-all rill-runtime-preview
apk update
apk add luci-app-performance-manager-all
```

Only remove these packages after confirming all other consumers have migrated. If the package manager reports remaining dependencies, stop and migrate those consumers first; do not force file replacement. The unified package declares `/etc/config/performance-manager` as a conffile; its removal script requests cleanup of PM-owned runtime leases but does not delete config or data directories. Its two keep rules preserve `/etc/performance-manager/` and Rill state across sysupgrade.

### Package info

| Item | Value |
|---|---|
| Recommended package | `luci-app-performance-manager-all` (one PM package) |
| Target | OpenWrt 24.10.8 IPK / 25.12.6 APK; verify each target against CI and release assets |
| Current source candidate | `1.1.1` |
| Unified PM package version | `1.1.1-r1` |
| Split Rill glue package version | `1.1.1-r1` |
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
ubus call performance-manager benchmark_start '{"actionId":"<actionId>","measurementClass":"controlled_ab"}'
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

package/luci-app-performance-manager-all/Makefile  # merges PM-owned content and compiled zh-cn LMO into one target package
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
                          │ shared Runtime package   │
                          │ ranking, no actuator      │
                          └────────────────────────┘
```

> **Consumer ownership boundary.** Rill Runtime source and the canonical package remain owned by `hello-yunshu/rill-openwrt-packages`; the unified PM package depends on it and does not own `/usr/bin/rill-runtime`. Runtime only ranks/reports and cannot apply router changes. Core remains fail-closed when Runtime is missing or incompatible.

## MacBook + Docker local Portable validation

Run the repeatable repository-software validation before pushing:

```sh
make portable-macos
# or: tools/docker-validate/run-local-macos.sh
```

Prerequisites are Docker Desktop, Git, Python 3, an authenticated `gh` CLI, and network access to GitHub / OpenWrt. The same-SHA CI and same-SHA Build for the current commit must already have completed successfully. The first run automatically downloads and verifies the OpenWrt 25.12.6 x86_64 rootfs; later runs may reuse the rootfs cache, but always re-check it against the official `sha256sums`. If the same-SHA Build is not complete, the result is `BLOCKED`, not a project-code `FAIL`.

The entry point reuses the existing source audit, OpenWrt ucode harness, artifact identity, package-composition gate, and portable gate. Run evidence is written to untracked `local-evidence/` and bound to the current commit SHA; package artifacts must come from a same-SHA GitHub Actions Build, never from `latest` or an older branch cache.

`Mac Docker PASS != Hardware PASS`. As of 2026-11-22 the repository owner removed the hardware-evidence precondition for Stable: a `portable-docker` profile whose gates all PASS may authorize a Stable release. Portable evidence still records `hardwareCoverage = NOT_EVALUATED`, and release notes disclose that real NIC behavior, Hyper-V/KVM, LAN-WAN, sysupgrade, reboot, and a real-router 12-hour soak were not executed. If Docker Desktop, linux/amd64 emulation, network downloads, or same-SHA artifacts are unavailable, the entry point reports a diagnostic `BLOCKED` instead of fabricating PASS.

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
- **openwrt-ucode**: compiles and validates Core ucode inside the official OpenWrt 25.12.6 rootfs

**`build-openwrt.yml` (remote official SDK build)**
- **openwrt-sdk-build**: builds four split packages and unified PM packages for OpenWrt 24.10.8/IPK and 25.12.6/APK across six native architectures, and emits Runtime provenance and audit-evidence artifacts

Public release staging emits only the 12 target-specific unified PM IPK/APK packages and `SHA256SUMS.txt`; JSON, MD, ZIP, split packages and standalone Runtime artifacts remain private Actions artifacts.

> The generic Runtime binary is intentionally external and is installed or updated through the shared Runtime manager.

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
