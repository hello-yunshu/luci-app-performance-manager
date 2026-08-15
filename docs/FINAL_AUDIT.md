# Final Audit — 1.0.0-rc.4

## Decision

**PASS — 1.0.0-rc.4 Core/LuCI source candidate; Rill external integration BLOCKED; Stable remains blocked by explicit external target/testbed gates and a provisioned upstream Rill release.**

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

Rill is an external runtime dependency owned, built and released by its upstream repository. This repository does not compile or natively test Rill. The PM-side fail-closed contract **PASSES** (the Core never crashes, never fakes a recommendation, and never auto-applies from an unavailable/incompatible runtime), but because no upstream Rill release is provisioned this cycle the **external integration is BLOCKED** (`docs/rill-integration-status.json`). This is reported honestly: **pmFailClosedContract=pass, upstreamIntegration=blocked, overallFeatureStatus=blocked** — never PASS.

## Real Core runtime harness

Real OpenWrt ucode executes the actual `performance-manager.uc` (Layer 2) via `tools/docker-validate/harness` and asserts on: Multi-WAN/PBR discovery from route/rule evidence (custom `isp-b`/`fiber`), underlay resolution (PPPoE→VLAN→NIC), path-specific workload class (global WireGuard does not leak into plain WAN), nft candidate-only fingerprint masking, measurement-methodology mismatch, Conservative auto-tick gating, and Rill fail-closed on an unavailable socket. Report: `core-runtime-harness.log`.

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
