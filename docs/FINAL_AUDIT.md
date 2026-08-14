# Final Audit — 1.0.0-rc.2

## Decision

**PASS — 1.0.0-rc.2 source-complete release candidate; Stable remains blocked only by explicit external target/testbed gates.**

This audit is a single self-contained orchestrator: contract validation, host syntax checks, source gates, resource budget, the unittest suite and the Rill native test suite are all rerun in this process, and only the freshly generated reports are consumed. Source completion is deliberately separated from real target evidence.

## Orchestrated gates

- contract-validation: **PASS**
- host-syntax: **PASS**
- source-gates: **PASS**
- resource-budget: **PASS**

- Rill native tests: **PASS**

## Local evidence

- Executable unit/contract tests: **69**, status **PASS**.
- Host syntax/JSON/JS/YAML checks: **21**, status **PASS**.
- Formal schemas/examples and frozen profiles: validated by `scripts/validate_contracts.py`.
- zh_Hans: all current literal LuCI msgids are covered.
- Resource budget: generated; target-only RSS/CPU/writes/day/boot-time values remain explicitly unmeasured until a real OpenWrt VM is used.

## Source phase gates

- Phase 0: **PASS** — Contract Freeze
- Phase 1: **PASS** — Bootstrap
- Phase 2: **PASS** — Capability / Topology / Target / Event
- Phase 3: **PASS** — Telemetry / Health / Analyzer / Path
- Phase 4: **PASS** — Policy / Compatibility
- Phase 5: **PASS** — Transactions / Locks / Commit-confirm
- Phase 6: **PASS** — Conservative
- Phase 7: **PASS** — Benchmark
- Phase 8: **PASS** — Rill Intelligence
- Phase 9: **PASS** — Recommend
- Phase 10: **PASS** — Assisted Auto
- Phase 11: **PASS** — Platforms
- Phase 12: **PASS** — Companion

## Closed strict-audit blockers

- Transaction Schema now covers the full frozen state machine and runtime-shaped null/awaiting-confirm states.
- Persistence, Lock, Health, Benchmark Session and Companion Measurement contracts are formal schemas shipped with Core.
- Commit-confirm now arms a real monotonic deadline and timer.
- Active transaction state has a durable pending marker; same-boot daemon crash rolls back, while cross-boot recovery clears stale runtime intent without replay.
- Health Guard includes baseline-relative LAN/WAN/DNS/IPv4/IPv6/proxy/VPN/route, load, steal, OOM, thermal and writable-state checks.
- Route identity is based on `ip -j` default-route/rule evidence and rtnetlink route/link events; multi-WAN candidates are represented explicitly.
- Controlled A/B is now an explicit session: control evidence → one-variable candidate transaction → candidate evidence → verified rollback → comparison.
- Generic qdisc and third-party SFE are capability-blocked unless an exact reversible provider contract is proven.
- Benchmark experiments are exclusive under a single tuning-domain lock, acquire-before-session-write, with stale/idle lock recovery on daemon start and cleanup.
- Benchmark context fingerprinting covers per-service running state, UCI config digests (candidate-mutated keys masked) and ip rule evidence; any drift fails the session closed.
- Forwarding benchmarks require a resolved route (`routeResolved===true` from the rtnl listener) and a strict, non-fallback evaluation path.
- Rill is a root-peer Shadow bandit with a strict JSON parser, per-operation schema validation, a context-partitioned model keyed by Core-computed ContextKeys, and stale-recommendation invalidation on drift.
- Assisted Auto gates on the selected action's own target traffic before applying, and remains safe-allowlist only.
- Uninstall cleanup is fail-closed: package removal aborts unless the daemon confirms an ownership-safe cleanup; upgrades and staged roots are untouched.
