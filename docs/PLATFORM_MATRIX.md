# Platform Matrix

Primary supported baseline: **OpenWrt 25.12.x / x86_64 (APK)**. The rows below describe the additional platform-specific behavior and validation.

| Platform | RC behavior | Stable validation needed |
|---|---|---|
| Generic OpenWrt x86_64 | capability/topology/path discovery; native providers respected | bare-metal/VM smoke + soak |
| Hyper-V | `hv_netvsc` detection; conservative 1024 ring floor when current < 1024 and max >= 1024; host vRSS/VMMQ guidance | Windows Hyper-V guest runtime + hotplug/reboot replay |
| KVM / Proxmox VE guest | QEMU/KVM evidence; virtio multiqueue host guidance | virtio-net multiqueue fixtures on KVM/PVE |

The guest cannot reliably prove that a KVM host is specifically Proxmox VE from generic DMI evidence, so the Core reports KVM and “Proxmox-compatible guest guidance” rather than inventing host identity.
