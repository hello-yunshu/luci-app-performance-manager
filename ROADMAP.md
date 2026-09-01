# Roadmap

Planning pack v0.3.2 is contract-frozen. Smart Decision v2 adds the unified Core selector, Runtime v3 feature/reward contract, fail-closed learning stages, confidence/drift/cooldown gates, explainability and LuCI refresh/status surfaces. Rill remains an external Runtime dependency; this repository does not vendor a PM-owned adapter or Rust Runtime source. The remaining work is same-commit validation across local, CI and target evidence.

1. Pass the CI gates on official OpenWrt 25.12.5: `ci.yml` (static, pm-rill-provenance, pm-rill-runtime, pm-core-rill-roundtrip, openwrt-ucode rootfs) and `build-openwrt.yml` (openwrt-sdk-build, which also emits build-metadata.json + checksums.txt evidence).
2. Pass booted-target evidence on clean x86_64 OpenWrt 25.12.x VMs, including Core without LuCI/Rill dependency.
3. Pass Hyper-V and KVM/Proxmox TargetRef, hotplug, replay, rollback and ownership-cleanup tests.
4. Run explicit LAN→Router→WAN and router-local controlled A/B for supported benchmark providers.
5. Pass package upgrade/sysupgrade and 24h+ resource/write soak.
6. Freeze `1.0.3` Stable only when all evidence is attached and independently auditable.

New optimizers stay backlog-only until Stable gates pass.
