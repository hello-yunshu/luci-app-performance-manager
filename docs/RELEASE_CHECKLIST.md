# 1.0 Stable Release Checklist

## Build / package

- [ ] Official OpenWrt 25.12.x x86_64 SDK builds `performance-manager`.
- [ ] SDK builds `luci-app-performance-manager`.
- [ ] SDK builds `performance-manager-rill` as an integration/meta package (no Rust build; fail-closed init guard and `lib/upgrade/keep.d` packaged).
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
