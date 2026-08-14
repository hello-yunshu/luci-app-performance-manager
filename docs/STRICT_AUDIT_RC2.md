# OpenWrt Performance Manager 1.0.0-rc.2 — Strict Remediation Audit

Date: 2026-08-13  
Planning authority: `docs/planning-v0.3.2/` (Contract Freeze)  
Predecessor audit: `OpenWrt_Performance_Manager_1.0.0-rc.1_Strict_Audit_2026-08-13.md`

## Decision

**SOURCE REMEDIATION PASS — `1.0.0-rc.2` may be treated as a source-complete release candidate, but it is not 1.0 Stable.**

This decision is deliberately narrower than “release passed”. It means the source-level blockers found in the rc.1 strict audit have been closed and the repository now contains the required target-evidence machinery. It does **not** claim OpenWrt SDK/rootfs build, booted VM, Hyper-V/KVM, forwarding A/B, sysupgrade or 24h soak evidence that has not actually run.

## Independent local evidence

- Frozen planning tree: unchanged by `git diff -- docs/planning-v0.3.2`.
- Formal contract validation: 5 profiles, 13 schema examples, 18 frozen ubus methods; runtime schema copies identical.
- Executable Python unit/reference-contract tests: **43 PASS**.
- Host syntax / JSON / JavaScript / YAML checks: **21 PASS**.
- Machine source gates: Phase 0–12 **PASS**, explicitly labeled source-only.
- `git diff --check`: PASS.
- Current LuCI literal zh_Hans coverage: PASS.
- No prompt artifact is allowed into the release tree by contract validation.
- Cargo/Rust and ucode target compilation are **not locally available** and remain CI/target evidence, not silently inferred from source scans.

## rc.1 strict-audit findings — disposition

| rc.1 finding | rc.2 disposition | Evidence / implementation |
|---|---|---|
| Transaction pending/recovery lived only in tmpfs | **CLOSED (source)** | Active transaction pending marker is durable under `/etc/performance-manager/pending`; volatile journal remains in tmpfs. Same-boot crash recovery rolls back; cross-boot marker recovery refuses stale runtime snapshot replay. |
| Commit-confirm deadline existed as a dead field | **CLOSED (source)** | `arm_commit_confirm()` sets a real monotonic deadline, persists state and arms `uloop` timeout; recovery rearms or rolls back on timeout/missing deadline. |
| Transaction/Action Schema disagreed with runtime | **CLOSED** | Formal schemas cover full frozen transaction states and runtime-null shapes; Action requires risk/benchmark/persistence/lock/confirm safety fields. |
| Persistence/Lock/Health/Benchmark contracts missing | **CLOSED** | Dedicated schemas added and copied into Core runtime payload; examples validate with Draft 2020-12. |
| Phase 7 was a catalog, not controlled A/B | **CLOSED under capability-first rule** | Controlled session now freezes context, ingests control evidence, applies exactly one reversible candidate through common transaction/lock/readback/health machinery, ingests candidate evidence, verifies rollback **before** reward, then persists result before Rill outcome. Providers without exact inverse remain capability-blocked instead of guessed. |
| Companion was not an end-to-end Core benchmark participant | **CLOSED (source)** | `pm-companion/v2` carries session/phase/action/path/topology/route/capability context; Core performs exact evidence binding and staged ingestion. Companion remains endpoint-only/no router mutation. |
| Health Guard omitted frozen dimensions | **CLOSED (source)** | Baseline-relative LAN/WAN/DNS/IPv4/IPv6/proxy/VPN/route plus memory/OOM/load/steal/thermal/state/persistent-storage checks and structured Analyzer evidence/confidence. |
| Multi-WAN/PBR route identity was a synthetic string | **CLOSED (source)** | WAN-specific default-route evidence plus policy rules from `ip -j`; route/link rtnetlink events invalidate topology; explicit WAN paths are selectable for benchmark evaluation. |
| Event loop did not cover route/device changes robustly | **CLOSED (source)** | ubus network/interface/firewall events plus rtnetlink NEW/DEL route/link listeners feed debounce/topology generation/re-resolution. |
| Rill learning state defaulted to volatile `/var` and grew unbounded | **CLOSED (source)** | Persistent `/etc/performance-manager/rill`, sysupgrade keep rule, bounded line/file storage and compaction; logical persistent-write counter exposed for soak measurement. |
| Profile Healthy checked commands only | **CLOSED (source)** | Inherited required/recommended/conditional packages, expected commands/capabilities and target constraints are evaluated separately. |
| `capabilityHash` was not a real capability identity hash | **CLOSED (source)** | Stable hash is computed over canonical capability identity/provider/availability/adjustability rather than count-only summary; benchmark freezes it in context. |
| Tests were dominated by source-string existence assertions | **CLOSED as an audit-semantics blocker; runtime evidence still external** | Real schema instance validation and reference-model tests now cover transaction recovery, baseline-relative health, Companion exact context, reward, ownership cleanup, benchmark persistence ordering, sysupgrade evidence semantics and Profile inheritance. Source-token checks remain only in an explicitly named `SOURCE_GATES` layer and are never presented as target-runtime proof. |
| `final_audit.py` hard-coded test count and Phase completion | **CLOSED** | Final audit reruns unittest dynamically, reads generated host report and machine source gates; test count and pass decision are calculated at execution time. |
| LuCI zh_Hans was substantially incomplete | **CLOSED for current literal UI surface** | Contract validator extracts current literal `_('…')` msgids and requires zh_Hans coverage; duplicate PO msgids are also checked. |

## Additional defects found and closed during rc.2 remediation

1. **Package-removal cleanup vs upgrade:** custom Core `prerm` now skips cleanup under staged root and `PKG_UPGRADE=1`; actual package removal still calls root-only ownership cleanup.
2. **Ownership-safe uninstall:** Core records a per-boot runtime lease (`beforeRing` + exact PM-owned value). Cleanup restores only when current live state still equals the PM-owned value; external drift is preserved and only replay intent is removed.
3. **Replay persistence failure:** if a replayed runtime state cannot persist its refreshed ownership lease, the just-applied runtime change is restored immediately.
4. **Benchmark persistence order:** session creation failure aborts before candidate work; completed result must persist after safe rollback before Rill receives a learning outcome.
5. **Absent UCI option restoration:** SFO/HFO candidates restore “option absent” as absent rather than inventing `0`.
6. **Partial multi-write failure:** CPU-governor / firewall-backed candidates restore already-changed components before releasing locks.
7. **Rill JSON correctness:** parser handles UTF-8/JSON escapes and valid surrogate pairs while rejecting malformed/lone surrogates.
8. **Resource-gate false positive:** a shortened soak can no longer emit a passing Stable result; `<86400s` yields `stableDurationSatisfied=false`, `passed=false`, and non-zero exit.
9. **Sysupgrade evidence gap:** new two-stage `openwrt-sysupgrade-gate.sh prepare|verify` requires a changed boot ID, validates preserved config/Core/Rill persistent roots, and rejects stale locks/pending markers.
10. **Core-only target evidence:** target gate can require LuCI and Rill to be absent (`PM_REQUIRE_CORE_ONLY=1`); explicit mutation mode now fails if the expected legal ring candidate is missing instead of silently skipping.
11. **Companion protocol drift:** remaining v1 documentation/schema compatibility text was removed; current source contract is consistently `pm-companion/v2`.

## Phase 0–12 strict source status

| Phase | Strict source status | Important boundary |
|---|---|---|
| 0 Contract Freeze | PASS | Formal schemas/constants; frozen planning files unchanged |
| 1 Bootstrap | PASS | Three packages, independent Core, LuCI/Rill optional, CI source present |
| 2 Capability/Topology/Target/Event | PASS | Multi-WAN route identity, TargetRef underlay safety, ubus+rtnl invalidation |
| 3 Telemetry/Health/Analyzer/Path | PASS | Baseline-relative guard and evidence/confidence analyzer |
| 4 Policy/Compatibility | PASS | Integration discovery and ownership/provider guards |
| 5 Transaction/Locks/Commit-confirm | PASS | Durable marker, timers, crash/boot recovery, ownership-safe cleanup |
| 6 Conservative | PASS | Safe direct allowlist remains Hyper-V ring floor; native Packet Steering observed/respected |
| 7 Benchmark | PASS under capability-first rule | Exact reversible providers execute; unsafe/inexact providers must stay blocked |
| 8 Rill Intelligence | PASS | Shadow-only, drift, weighted validated outcomes, bounded persistent state |
| 9 Recommend | PASS | Deterministic recommendation + authority-free Rill advisory separated |
| 10 Assisted Auto | PASS | Default off; double opt-in + maintenance + traffic + Health + safe allowlist |
| 11 Platforms | PASS for RC source | Generic x86/Hyper-V/KVM guest detection/guidance; real matrix remains target gate |
| 12 Companion | PASS | v2 exact-context endpoint evidence with no router configuration authority |

## Evidence that is still genuinely external

The following are **release evidence**, not remaining source implementation tasks:

1. GitHub/native Rust `cargo test` + `cargo check` must actually run.
2. Official OpenWrt 25.12.x x86/64 rootfs must actually compile Core ucode with declared modules.
3. Official OpenWrt SDK must actually build Core, LuCI and Rill packages.
4. Booted x86_64 OpenWrt must pass `scripts/openwrt-target-gate.sh`; a dedicated Core-only run should use `PM_REQUIRE_CORE_ONLY=1`.
5. Hyper-V mutation fixture must run target gate with `PM_ALLOW_MUTATION=1`; absence of a legal candidate is a failure in that mode.
6. KVM/Proxmox-compatible guest hotplug/TargetRef/replay behavior must be exercised on a real guest.
7. Forwarding classes require explicit LAN client → Router → WAN server evidence; local classes require router-local semantics where appropriate.
8. Run `scripts/openwrt-sysupgrade-gate.sh prepare`, perform the intended real sysupgrade/reboot, then run `verify`.
9. Run `scripts/openwrt-resource-soak.sh` for at least 86400 seconds; shorter runs cannot pass the Stable gate.

Until these pass, **do not rename rc.2 to 1.0 Stable**.

## Final strict recommendation

`1.0.0-rc.2` is suitable for source release / external validation. No additional optimizer expansion is recommended before collecting the external evidence above. If any target gate reveals a source defect, fix it and issue a later RC; otherwise Stable promotion can be evidence-driven rather than feature-driven.
