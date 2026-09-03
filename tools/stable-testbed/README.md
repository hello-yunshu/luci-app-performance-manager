# Stable testbed controllers

All verdict logic is versioned here. Self-hosted runners provide only a transport executable through `PM_TESTBED_TRANSPORT`; it receives a repository-defined JSON request and must return raw observations. The controller independently locates the exact APKs from the selected build run, verifies their hashes, binds the exact Rill adapter, validates gate-specific semantics, and emits `PASS` only after the repository validator accepts the result. Missing transport or infrastructure is `BLOCKED`/job failure, never synthetic evidence.

`.github/workflows/hardware-validation.yml` is the dedicated Hardware evidence
profile. It verifies the exact CI and Build OpenWrt run identities first, then
dispatches the repository-owned controller for `target-core-only`, `target-full`,
`target-mutation`, Hyper-V, KVM, LAN/WAN A/B, router-local A/B, sysupgrade,
lifecycle, and 24-hour resource soak. The Linux jobs use the repository's
gate-specific labels `pm-generic`, `pm-kvm`, `pm-lan-wan`, `pm-router-local`,
`pm-sysupgrade`, `pm-lifecycle`, and `pm-soak`; the Hyper-V job uses
`pm-hyperv`. If those runners or their transport are absent, the hardware
profile remains unavailable/BLOCKED and cannot authorize Stable.
