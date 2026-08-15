# Roadmap

Planning pack v0.3.2 is contract-frozen. `1.0.0-rc.4` closes the source-level blockers found by the strict rc.1 audit, the 2026-08-14 independent re-audit, and the 2026-08-16 rc.4 single-repo remediation (including the real Core ucode runtime harness); the remaining roadmap is evidence collection, not feature expansion. As of rc.4, Rill is an external runtime dependency, so no native Rust build is part of this repository's roadmap.

1. Pass the CI gates on official OpenWrt 25.12.5: `ci.yml` (static, rill-contract, openwrt-ucode rootfs) and `build-openwrt.yml` (openwrt-sdk-build, which also emits build-metadata.json + checksums.txt evidence).
2. Pass booted-target evidence on clean x86_64 OpenWrt 25.12.x VMs, including Core without LuCI/Rill dependency.
3. Pass Hyper-V and KVM/Proxmox TargetRef, hotplug, replay, rollback and ownership-cleanup tests.
4. Run explicit LAN→Router→WAN and router-local controlled A/B for supported benchmark providers.
5. Pass package upgrade/sysupgrade and 24h+ resource/write soak.
6. Freeze `1.0.0` Stable only when all evidence is attached and independently auditable.

New optimizers stay backlog-only until Stable gates pass.
