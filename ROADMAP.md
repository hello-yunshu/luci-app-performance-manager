# Roadmap

Planning pack v0.3.2 is contract-frozen. `1.0.0-rc.2` closes the source-level blockers found by the strict rc.1 audit; the remaining roadmap is evidence collection, not feature expansion.

1. Pass native Rust, official OpenWrt 25.12.5 rootfs ucode and SDK three-package CI.
2. Pass booted-target evidence on clean x86_64 OpenWrt 25.12.x VMs, including Core without LuCI/Rill dependency.
3. Pass Hyper-V and KVM/Proxmox TargetRef, hotplug, replay, rollback and ownership-cleanup tests.
4. Run explicit LAN→Router→WAN and router-local controlled A/B for supported benchmark providers.
5. Pass package upgrade/sysupgrade and 24h+ resource/write soak.
6. Freeze `1.0.0` Stable only when all evidence is attached and independently auditable.

New optimizers stay backlog-only until Stable gates pass.
