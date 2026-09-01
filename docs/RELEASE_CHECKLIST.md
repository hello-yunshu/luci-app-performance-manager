# 1.0 Stable Release Checklist

## Portable Docker release profile

The current public `1.0.3` release uses `portable-docker`. It requires the
same-commit CI/Rill chain, official SDK/APK identity, hosted Action tests, and
the real Core ucode harness executed inside Docker. It must disclose that
Hyper-V, KVM hotplug, real-router A/B, firmware sysupgrade reboot, and 24-hour
hardware soak are **NOT_EVALUATED**. The checklist below remains the separate
`hardware` profile and must not be represented as passed by portable evidence.

## Build / package

- [ ] Official OpenWrt 25.12.x x86_64 SDK builds `performance-manager`.
- [ ] SDK builds `luci-app-performance-manager`.
- [ ] SDK builds `performance-manager-rill` as an integration/meta package (no Rust build; fail-closed init guard and `lib/upgrade/keep.d` packaged).
- [ ] SDK builds `luci-app-performance-manager-all` and `performance-manager-rill`; exact APK verification proves all repository-owned Core/LuCI/rpcd source files match and the compiled zh-cn LMO is present. The generic Runtime remains an external package.
- [ ] Public assembly includes exactly one `luci-app-performance-manager-all` and one `performance-manager-rill` APK; `rill-runtime` remains an external package from `rill-openwrt-packages` and is verified by its own provenance/compatibility chain.
- [ ] Official OpenWrt rootfs compiles Core ucode with all declared modules.

## Runtime / topology / ownership

- [ ] Core boots and publishes the frozen ubus API with LuCI absent.
- [ ] Core remains functional with Rill absent/stopped.
- [ ] Native Packet Steering state is discovered and never seized by default.
- [ ] PPPoE WAN resolves tuning to underlay, not the logical PPP device.
- [ ] Multi-WAN/PBR paths resolve WAN-specific route identity and invalidate on drift.
- [ ] Hyper-V ring floor applies only under the frozen threshold condition.
- [ ] Ring read-back, baseline-relative health, manual rollback and policy-intent removal pass.
- [ ] Uninstall cleanup restores only a current PM-owned runtime lease and preserves external live drift.
- [ ] Reboot/device-up/topology-change policy replay re-resolves TargetRef and refreshes the runtime lease.
- [ ] Lock conflict tests prevent stale rollback overwrite.

## Rill / security

- [ ] One exact Rill decision can be reserved by only one transaction/session and disappears from fresh advisory UI immediately.
- [ ] A validated execution has a persistent immutable Outcome intent before the terminal transaction/session is reported.
- [ ] Core restart and router reboot recover pending Outcome delivery without re-observing or re-executing the decision.
- [ ] Connect/partial-send failures never set `mayHaveReachedPeer`; full-send response loss does, and only exact owner/fingerprint duplicates reconcile.
- [ ] Outcome retry remains active with telemetry disabled and emits no Observe traffic.
- [ ] Upstream Rill release is consumed; `scripts/rill_contract_check.py` and the `rill-contract` CI gate pass against pinned upstream release provenance.
- [ ] Core stays fail-closed (no auto-apply, no fake recommendation) when the external Rill runtime is absent, unreachable or protocol-incompatible.
- [ ] Rill wrong peer, oversized message, flood, timeout, malformed UTF-8/JSON, bad schema and crash tests pass.
- [ ] Rill ordinary observations cause no persistent write amplification.
- [ ] Rill state remains bounded and survives intended sysupgrade preservation.

## Benchmark / testbed

- [ ] Controlled A/B uses explicit Companion evidence, a frozen context and exactly one reversible variable.
- [ ] Forwarding classes use LAN client → Router → WAN server.
- [ ] Local classes use router-local endpoint semantics where applicable.
- [ ] Candidate is restored/read-back verified before reward is persisted/sent to Rill.
- [ ] Fast-path tests hard-fail on functional regression.

## Upgrade / resource / release

- [ ] `scripts/openwrt-sysupgrade-gate.sh prepare` → real sysupgrade/reboot → `verify` proves boot change and preservation of config/PM/Rill persistent roots with no stale lock/pending marker.
- [ ] `scripts/openwrt-target-gate.sh` evidence passes on required target matrices.
- [ ] `scripts/openwrt-resource-soak.sh` runs 24h+ and resource/flash-write budget is accepted.
- [ ] SHA-256 release artifact, manifest, source audit and target evidence are attached.
- [ ] Every external gate passes its versioned semantic evidence schema; a minimal top-level `PASS` envelope fails.
- [ ] Target-installed Core/contracts hashes and exact APK hashes match the selected same-commit build metadata and APK verifier.
- [ ] CI/build/target input runs pass conclusion, head SHA and workflow-identity checks before artifact download.
- [ ] Testbed verdict logic comes from `tools/stable-testbed`; runner-local code is transport/infrastructure only.
