# Changelog

## 1.0.0-rc.2 — independent re-audit hardening (2026-08-14)

- Closed the independent re-audit blockers (Blocker/High/Medium) against the same frozen v0.3.2 contract:
- **Benchmark exclusivity (Blocker):** experiments are globally exclusive under a single `benchmark:global` tuning-domain lock, acquired before the session write, released on every terminal path, with idle-expiry (`benchmark.session_idle_seconds`) and stale-lock recovery at daemon start/cleanup.
- **Context fingerprint (Blocker):** benchmark sessions and Rill payloads now carry a full context fingerprint (per-service running state, UCI config digests, `ip -j rule` digest); any capability/topology/route/integration/workload drift fails the session closed (`benchmark-context-drift`). Candidate-mutated UCI keys are masked so the candidate cannot self-trigger drift.
- **Strict evaluation path (High):** invalid evaluation paths are rejected (`evaluation-path-not-found`) instead of silently falling back to primary; forwarding benchmarks require a resolved route (`routeResolved===true`, rtnl-provided) with `evaluation-route-unresolved`.
- **Path-specific health (Medium-High):** baseline/regression health is now computed for the evaluated path's own WAN interface, not just the primary WAN.
- **Rill contextual bandit (High 3+4):** Core computes a canonical bounded `ctx-v1:` ContextKey shared by observe and outcome payloads; Rill validates every operation against a formal per-op schema, ingests full Action/Observe metadata, partitions its model per context, and invalidates stale recommendations on drift.
- **Rill strict protocol (High 5 + Medium):** `contracts/rill-ipc.schema.json` is now a formal per-op v2 protocol (envelope + observe/outcome required sets, `ctx-v1:` pattern, outcome `validated:const true`); Rill uses a hand-written strict JSON parser (duplicate-key rejection, nesting bound, strict numbers/escapes) with per-operation validation and rejections for missing metadata.
- **Assisted Auto target gate (Medium-High):** low-traffic gate is bound to the selected action's own target runtime (`assisted-previous-<runtime>.json` baseline), after the action is chosen.
- **Uninstall fail-closed (Medium):** `prerm` now aborts removal unless the daemon confirms `ok:true` from ownership-safe cleanup; only inert replays (binary already gone), staged roots and upgrades bypass cleanup.
- **Reproducible CI (Medium):** native Rust tests pin `dtolnay/rust-toolchain@1.88.0`; SDK feed sources are pinned to the official release `feeds.buildinfo` commits via `scripts/pin_feeds.py` with HEAD verification.
- **Source gates (Medium):** `scripts/source_gates.py` upgraded from token-presence to behavioral constructs (lock exclusivity, drift fingerprint, route gate, contextual Rill model, target-bound Assisted Auto, fail-closed prerm).
- **Self-contained audit (Medium):** `scripts/final_audit.py` is now the single orchestrator that reruns contract validation, host syntax, source gates, resource budget, the unittest suite and Rill native tests, consuming only freshly generated reports; `make audit` is exactly this.
- Benchmark Session schema extended with `integrationFingerprint`, `deviceProfile`, `benchmarkLock` and `createdMonotonicMs`; Rill outcome validation now enforces `integrationFingerprint` like the schema.
- Local suite grew to 69 Python tests and 15 Rust tests, all passing; Rill suite is green including the previously failing unvalidated-outcome boundary.

## 1.0.0-rc.2 — 2026-08-13

- Closed the strict rc.1 audit blockers against planning pack v0.3.2 rather than extending optimizer scope.
- Aligned formal Transaction/Action contracts with the runtime and added Persistence, Lock, Health, Benchmark Session and Companion Measurement schemas.
- Added durable pending markers, real monotonic commit-confirm arming, same-boot crash rollback and cross-boot stale-snapshot refusal.
- Added baseline-relative DNS/proxy/VPN/route/CPU steal/thermal/storage health and structured Analyzer evidence/confidence.
- Reworked multi-WAN/PBR route identity around WAN-specific `ip -j route/rule` evidence plus rtnetlink route/link invalidation.
- Replaced fake capability hash with a stable capability contract hash.
- Implemented the controlled-A/B state machine with `pm-companion/v2` context binding, one-variable provider locks, read-back, health verification, verified rollback before reward and persistence-before-Rill ordering.
- Made benchmark/session write failures fail closed; providers without an exact reversible contract remain explicitly blocked.
- Moved Rill learning state to bounded persistent storage, hardened UTF-8/JSON parsing and exposed logical persistent-write accounting for soak evidence.
- Added per-boot PM-owned runtime leases and ownership-safe package-removal cleanup; package upgrades bypass uninstall cleanup.
- Expanded Profile Contract checking across packages, commands, capabilities, conditional packages and target constraints.
- Rebuilt LuCI Benchmark flow and added Advanced diagnostics with complete current zh_Hans literal coverage.
- Replaced hard-coded final-audit claims with executable tests/source gates; local suite now also covers benchmark persistence and uninstall/sysupgrade ownership semantics.
- Added booted-target, two-stage sysupgrade, and 24h resource/write evidence scripts; shortened soak runs cannot claim Stable pass; CI is pinned to current OpenWrt 25.12.5 x86/64.

## 1.0.0-rc.1 — 2026-08-13

- Completed frozen Phase 0–12 source implementation while preserving v0.3.2 planning contracts.
- Added stable underlay-aware TargetRef resolution for PPPoE/VPN topologies.
- Hardened ring transactions: rollback read-back, persistence-failure rollback, same-boot committed rollback and policy-intent removal.
- Bounded persistent history and moved ordinary topology/event telemetry to tmpfs.
- Expanded capability discovery for native Packet Steering queue topology, local-port/conntrack capacity, wireless observe, fast path and benchmark-class kernel/NIC features.
- Added complete Phase-7 benchmark catalog and removed false validation: no explicit forwarding endpoints means no controlled A/B result.
- Added Rill context drift, weighted validated-outcome Shadow bandit, Decision Ledger and model-health reporting; advisory remains non-actuating.
- Added deterministic + Rill-separated recommendation output.
- Added explicit opt-in Assisted Auto with maintenance-window, low-traffic, health and safe-allowlist gates.
- Added Generic/Hyper-V/KVM platform model with Proxmox-compatible guest guidance.
- Added Phase-12 explicit iperf3 Companion Agent and evidence schema with no router mutation authority.
- Added LuCI confirm/committed rollback controls, persistent/runtime history separation and learned-advisory rendering.
- Added release documentation, official OpenWrt rootfs ucode CI, native Cargo check and official SDK three-package build CI.

## 0.1.0-rc.1 — development baseline

- Phase 0–6 bootstrap and initial Rill Shadow collector.
