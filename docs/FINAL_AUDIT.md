# Final Audit — 1.0.0-rc.3

## Decision

**PASS — 1.0.0-rc.3 source-complete release candidate; Stable remains blocked only by explicit external target/testbed gates.**

This audit is a single self-contained orchestrator: contract validation, host syntax checks, source gates, resource budget and the unittest suite are all rerun in this process, and only the freshly generated reports are consumed. Source completion is deliberately separated from real target evidence.

## Orchestrated gates

- contract-validation: **PASS**
- host-syntax: **PASS**
- source-gates: **PASS**
- rill-contract: **PASS**
- resource-budget: **PASS**


## Local evidence

- Executable unit/contract tests: **84**, status **PASS**.
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
- Phase 8: **PASS** — Rill Intelligence (external runtime)
- Phase 9: **PASS** — Recommend
- Phase 10: **PASS** — Assisted Auto
- Phase 11: **PASS** — Platforms
- Phase 12: **PASS** — Companion

## Rill integration (external runtime)

Rill is an external runtime dependency owned, built and released by its upstream repository. This repository does not compile or natively test Rill. The PM CI `rill-contract` gate verifies the pinned upstream Rill release (provenance/checksum) and the PM<->Rill protocol/capability contract; a missing runtime, unreachable service or protocol-major mismatch is fail-closed and reported as Rill unavailable/incompatible, never silently assumed healthy.

## Closed strict-audit blockers

- Transaction Schema now covers the full frozen state machine and runtime-shaped null/awaiting-confirm states.
- Persistence, Lock, Health, Benchmark Session and Companion Measurement contracts are formal schemas shipped with Core.
- Commit-confirm now arms a real monotonic deadline and timer.
- Active transaction state has a durable pending marker; same-boot daemon crash rolls back, while cross-boot recovery clears stale runtime intent without replay.
- Health Guard includes baseline-relative LAN/WAN/DNS/IPv4/IPv6/proxy/VPN/route, load, steal, OOM, thermal and writable-state checks.
- Route identity is based on `ip -j` default-route/rule evidence and rtnetlink route/link events; multi-WAN candidates are represented explicitly.
- Runtime Topology conforms to the formal schema (string `lanInterface`), and paths resolve a real underlay NIC chain (VLAN/bridge/PPPoE/tunnel/radio) to a stable target.
- Multi-WAN/PBR Path inventory is built from netifd/runtime route/rule evidence, not `wan[0-9]+` naming guesses.
- Workload Class is derived from affected/evaluation path evidence (all seven frozen classes), never hard-coded to `plain_forwarding`.
- Conservative automation carries real safety semantics: safe-allowlist-only auto-apply, never seizes preexisting, observe/respect packet steering, transactional ownership-backed writes, Rill advisory-only.
- Controlled A/B freezes a canonical measurement methodology (host/port/direction/streams/duration/protocol/tool version); any control/candidate mismatch is rejected (`validated=false`, no reward, no Rill outcome).
- Benchmark context includes a live nft ruleset fingerprint and route/rule identity; live-only control/candidate drift invalidates the experiment.
- Policy replay cedes on live drift: if the value PM owns has changed, ownership is relinquished and the user/external value is not overwritten.
- Assisted Auto gates on the selected action's own target traffic before applying, and remains safe-allowlist only.
- Uninstall cleanup is fail-closed: package removal aborts unless the daemon confirms an ownership-safe cleanup; upgrades and staged roots are untouched.
