# Roadmap

Planning pack v0.3.2 is contract-frozen. `1.0.0-rc.8` closes the exact Rill decision lifecycle, persistence-accounting, effective socket access-control, and source-to-Stable evidence-promotion gaps. Rill remains an external runtime dependency, so no native Rust build is part of this repository's roadmap. The remaining work is execution of the declared same-commit validation matrix, not feature expansion.

1. Pass the CI gates on official OpenWrt 25.12.5: `ci.yml` (static, pm-rill-provenance, pm-rill-runtime, pm-core-rill-roundtrip, openwrt-ucode rootfs) and `build-openwrt.yml` (openwrt-sdk-build, which also emits build-metadata.json + checksums.txt evidence).
2. Pass booted-target evidence on clean x86_64 OpenWrt 25.12.x VMs, including Core without LuCI/Rill dependency.
3. Pass Hyper-V and KVM/Proxmox TargetRef, hotplug, replay, rollback and ownership-cleanup tests.
4. Run explicit LAN→Router→WAN and router-local controlled A/B for supported benchmark providers.
5. Pass package upgrade/sysupgrade and 24h+ resource/write soak.
6. Freeze `1.0.0` Stable only when all evidence is attached and independently auditable.

New optimizers stay backlog-only until Stable gates pass.
