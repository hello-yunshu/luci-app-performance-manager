# Changelog

## 1.0.1 — PM-owned Rill adapter migration (2026-08-25)

- Moves the consumer-specific `pm-rill-shadow` v1 adapter into `integrations/performance-manager-rill-adapter/`, preserving the immutable v1.5.1 source behavior and MIT attribution.
- Pins exact crates.io `rill-ml = 1.5.1`, commits `Cargo.lock`, builds `performance-manager-rill-adapter` as a target-specific OpenWrt package, and removes the active dependency on the RillML PM adapter Release artifact.
- Keeps `/etc/performance-manager/rill/adapter-state.json` schema 1 compatible with PM v1.0.0 adapter state and fails closed on corrupt or incompatible state instead of silently resetting it.
- Publishes PM v1.0.1 metadata and a machine-readable ownership handoff; real x86_64 OpenWrt roundtrip, sysupgrade, Actions and public Release status remain evidence gates.

## 1.0.0 — Final Stable candidate (2026-08-22)

- Defines the portable-docker release profile for hosted Actions plus Docker verification when hardware testbeds are unavailable; hardware coverage remains explicitly NOT_EVALUATED.
- Closes fail-closed Stable evidence semantics for resource metrics, firmware sysupgrade proof, lifecycle phase facts, action-specific mutation/A/B evidence, and cross-boot journal retention.
- Keeps publication gated by one exact Final SHA and the real same-commit CI, official SDK, target matrix, and 24-hour soak aggregate.

## 1.0.0-rc.14 — Final Stable evidence closure (2026-08-22)

- Share one exact artifact resolver across controller, prerelease, Stable assembly and APK staging; identical all-in-one copies pass and conflicting identities fail closed.
- Separate build inventory from installed identity; non-core Stable targets require all-in-one only, while Core-only requires Core only.
- Make `rawFacts` the sole transport input, derive A/B/sysupgrade semantics from nested facts, add controller→validator→aggregate E2E coverage, and bound retired execution journals.

## 1.0.0-rc.13 — Stable evidence evaluator hardening (2026-08-22)

- Terminalize post-mutation journal failures and invalid benchmark candidate exits.
- Derive every Stable testbed subcheck from raw transport observations and reject forged verdict maps.

## 1.0.0-rc.12 — All-in-one release candidate (2026-08-22)

- Keep the official OpenWrt SDK build compiling and verifying every split package plus the physical `luci-app-performance-manager-all` package.
- Promote `luci-app-performance-manager-all` to the sole public install asset for prerelease and Stable release downloads; this is a release convenience rule, not a build restriction.
- Fix the controlled benchmark success path so rollback remains eligible for the validated Rill Outcome.

## 1.0.0-rc.11 — Stable closure candidate (2026-08-22)

- Terminalize every post-mutation Rill execution failure without fabricating feedback; unresolved restore state is durable `intervention-required` and blocks further Rill actuation.
- Persist a crash-consistent terminal proof before arming an Outcome, so router reboot recovery does not depend on `/tmp` owner journals.
- Make Stable testbed transport raw-facts-only, require the all-in-one APK as the primary non-core artifact, and bind Actions/run evidence to immutable identities.

## 1.0.0-rc.10 — Verified all-in-one OpenWrt APK (2026-08-20)

- Adds `luci-app-performance-manager-all`, a physical single APK containing Core, LuCI, rpcd ACL/menu, configuration, profiles/schemas, compiled Simplified Chinese translation and repository-owned Rill integration glue.
- Keeps the existing split packages for advanced deployments while declaring conflicts to prevent duplicate ownership of installed paths; it deliberately avoids cross-package `PROVIDES` aliases under OpenWrt APK semantics.
- Extends the official OpenWrt 25.12 SDK workflow, exact APK verifier and build metadata to require the all-in-one artifact and byte-compare every repository-owned installed file against source.
- Keeps the upstream Rill runtime external and fail-closed; the bundle includes no Rill source, Rust toolchain or native binary.
- Moves GitHub Actions to current stable major tags and retains digest-bound SDK/feed caches.
- Remains a prerelease; full target, hypervisor, sysupgrade and soak evidence is still required for Stable.

## 1.0.0-rc.9 — Exact Rill Outcome + semantic Stable evidence (2026-08-20)

- Reserves each exact Rill decision to one transaction or benchmark owner before mutation and blocks duplicate execution.
- Persists immutable execution/Outcome intent under `/etc/performance-manager/rill-executions`, recovering delivery across Core restart and router reboot without replaying mutation.
- Distinguishes connect/send/full-send/response states and reconciles `duplicateFeedback` only for the exact durable owner and fingerprint.
- Runs bounded Outcome retry independently from telemetry and never performs periodic Observe.
- Replaces top-level external `PASS` envelopes with versioned gate-specific schemas, semantic subchecks, contradiction tests, and build/APK/installed-payload cross-checks.
- Verifies Action run conclusion, head SHA, and workflow identity before artifact download; Stable controller verdict logic is checked into `tools/stable-testbed`.
- Remains a release candidate; real self-hosted target matrix and 24-hour soak evidence are still required for Stable.

## 1.0.0-rc.8 — Exact Rill decision lifecycle + Stable evidence closure (2026-08-20)

- binds every Rill-assisted execution to the exact `decisionId`/action/context/goal/generation and freezes it into the production transaction or benchmark journal;
- validates every adapter response envelope and payload fail-closed, keeps retryable Outcome bindings, and reconciles `duplicateFeedback` only after a recorded same-attempt response loss;
- removes telemetry-driven Observe/persistence amplification, keeps unexecuted advisories in runtime memory, and exposes audited logical persistence counters;
- extends the real production Core↔exact-adapter gate through Observe, decision freeze, Core/adapter restart, controlled A/B, exact rollback, and accepted Outcome;
- replaces source-report promotion with non-promotable source/static verdicts and a same-commit Stable aggregator covering SDK/APK, targets, hypervisors, A/B, sysupgrade, lifecycle, and 24-hour Rill-present soak;
- replaces the unsupported socket inode-mode assertion with the implemented `0750` directory/dedicated-service-user access-control boundary.

## 1.0.0-rc.7 — Rill v1.2.0 real wire contract + decision ledger + evidence false-PASS closure (2026-08-19)

- **Request schema rewritten to the real adapter contract.** `contracts/rill-ipc.schema.json` replaces the old root-level `allOf`/permissive shape with per-operation `oneOf` branches (`$defs/statusRequest|observeRequest|outcomeRequest`), each with `additionalProperties:false` mirroring upstream's `deny_unknown_fields`: extra fields are now **rejected**, not ignored. `observeRequest` gains `goal` in `required` and changes `integrations` to a bounded `array` of `{id,present}` objects; `outcomeRequest` is reduced to the exact upstream-accepted field set (`decisionId/contextKey/actionId/sessionId/goal/modelGeneration/validated/reward`), removing the previously sent topology/measurement/device/context fields. Package schema copy (`usr/share/performance-manager/schemas/`) is kept in sync.
- **New response contract.** `contracts/rill-ipc-response.schema.json` validates `statusResponse` (`rillVersion`+`adapterVersion`), `observeResponse` (`decisionId`+`recommendation`), `outcomeResponse` (`accepted`) and `errorResponse`, plus the shared `contract`/`protocolVersion`/`requestId` echo/`ok` envelope. `rill_contract_check.py` and `test_contracts.py`/`test_rill_context.py` now read constants and per-op required fields from `$defs` (oneOf) instead of the removed root `properties`/`allOf`.
- **Core observe builds and parses the real protocol.** `rill_integrations_payload()` converts the internal `integration_state()` map to a deterministic bounded array; `rill_observe()` sends `goal` and validates the success response (contract, protocolVersion==1, requestId echo, `ok==true`, valid hex `decisionId`, `recommendation.actionId` ∈ `availableActions`, `advisory==true`, finite confidence). An error response can no longer pass as a successful observe.
- **Decision ledger binding.** On a successful observe Core persists a bounded, TTL-limited binding (schemaVersion, `decisionId`/`actionId`/`contextKey`/`goal`/`modelGeneration` frozen from the observe, monotonic timestamp, cleanup/prune, persisted under `/etc/performance-manager/rill`). The fabricated `pm-managed-apply` decisionId is gone: no real Rill decision ⇒ no Rill outcome.
- **Advisory only from observe, drift/TTL invalidated.** `learnedAdvisory` now comes solely from a successful observe (`rill_advisory_update`), never from `status` (real status carries no recommendations). `rill_advisory_get()` invalidates on topology-generation / route-identity / integration-fingerprint / goal drift, action disappearance, or TTL expiry.
- **Outcome rewrite with hard gates.** `rill_report_outcome()` consumes the live binding and sends only the frozen decision's exact field set; it skips (`rill.outcome.skipped`) when there is no bound decision, mismatched action, or stale/generation-mismatched binding, and validates the adapter's real `accepted` (no longer the fabricated `acknowledged`). Duplicate outcomes are prevented by one-shot binding consumption. Benchmark sessions keep the bound `rillDecisionId`/`rillActionId`/`rillContextKey`/`rillGoal`/`rillModelGeneration`; ordinary apply/rollback without a real Rill decision no longer emits outcomes.
- **Status reads real wire fields.** `rill_status()` drops `releaseVersion` as a wire claim, validates `ok`/requestId echo/contract/protocol/required capabilities/modelHealth, and reports `releaseVersion` from pinned dependency/provenance metadata only, alongside `adapterVersion`/`protocolVersion`.
- **Real adapter runtime test rewritten (false positives removed).** `scripts/rill_adapter_runtime.py` drives the exact released v1.2.0 adapter with real `status`/`observe`→real `decisionId`→`outcome` roundtrips and a 15-case negative suite (wrong contract, protocol 2, missing `goal`, `integrations` object, outcome unknown field, unknown decision, action/context/generation mismatch, `validated=false`, duplicate outcome, oversized/malformed/timeout/peer-close fail-closed). Any runtime BLOCKED now fails the release-critical job (non-zero exit).
- **Evidence false-PASS paths closed.** `build_evidence.py` adopts `combine_required` (`ANY FAIL→FAIL`, `ALL PASS→PASS`, else `BLOCKED`) across provenance/runtime/functional/Core-integration/rc verdicts; CI jobs emit separate per-job evidence (`rill-provenance.json`, `rill-runtime.json`, `rill-core-integration.json`) and the new `aggregate_final_evidence.py` combines only same-commit evidence into `final-release-evidence.json`; the consumed-release manifest is generated by one shared script (`generate_rill_consumed_manifest.py`), and `verify_rill_release.py` is contract-driven from `contracts/rill-dependency.json` (single source of truth for repository/tag/commit/index/adapter metadata).
- **Security/correctness hardening.** `shell_quote` removes `|` from the unquoted-safe character set (no pipe/command-injection); Core `rill_binary_path()` now rejects non-absolute or non-present explicit binaries (`binary-invalid`, no silent fallback); `RILL_MODEL.md` corrects the false `SO_PEERCRED` claim to the actual PM-created socket-directory ownership/permission model. Unit tests were upgraded from token `assertIn` checks to behavior tests of the real builder/parser/binding/combiner paths, with `tests/fixtures/` based on pinned v1.2.0 response semantics.

## 1.0.0-rc.6 — Rill v1.2.0 Stable real integration + provenance/runtime/roundtrip closure (2026-08-18)

- **Rill dependency moves rc.1 candidate → v1.2.0 Stable.** `contracts/rill-dependency.json` upgrades to schema `3` and pins the immutable Stable release `v1.2.0` (tag `v1.2.0` → commit `dc96fdb3bf55eacdd1c093f1be08d1c9daed4400`) with its Ed25519-signed `stable` release index (schema v3, publisher `rillml-examples-2026-001`) and the exact `x86_64-musl` `pm-adapter` artifact (never `latest`/`main`/`candidate-index`). Version semantics are kept distinct and unambiguous: **release bundle `1.2.0` ≠ adapter crate/binary `0.15.0` ≠ pm-rill-shadow protocol `v1`**. The old ambiguous `minimumRillVersion` is replaced by `minimumReleaseVersion` + `minimumAdapterVersion` (legacy alias explicitly marked deprecated).
- **Authoritative release verifier.** New `scripts/verify_rill_release.py` resolves the `v1.2.0` tag to its commit, checks the release is stable/non-draft, downloads and verifies the Ed25519 signature on the `stable`-index (schema 3, channel `stable`), selects the unique `pm-adapter`/`linux`/`x86_64`/`musl`/protocol-1 artifact, and verifies actual size+SHA256 against the signed index (`docs/rill-provenance.json`, `docs/rill-integration-evidence.json`). Provenance/schema/channel have dedicated negative tests (unknown schemaVersion or `candidate` channel fail-closed).
- **Static contract no longer over-claims.** `scripts/rill_contract_check.py` is scoped to the PM-side static dependency/protocol contract only; it never emits a `functionalIntegration=PASS`. Real upstream/runtime/roundtrip status comes solely from the verifier + integration tests.
- **Real adapter execution + protocol roundtrip.** `pm-rill-provenance` verifies the pin and uploads the exact verified adapter; `pm-rill-runtime` bootstraps the official 25.12.5 x86/64 musl rootfs, executes the released adapter (`--version` → `0.15.0`, never `1.2.0`), and drives real `status`/`observe`/`outcome` roundtrips plus fail-closed negatives over the UDS; `pm-core-rill-roundtrip` installs the raw shipped Core + the verified adapter and asserts `ubus call performance-manager rill_status` actually negotiates the real adapter (state, release `1.2.0`, adapter `0.15.0`, protocol `1`, binary `/usr/bin/rill-pm-adapter`).
- **Core/init binary resolver unified (fail-closed).** `rill_binary_path()` (Core) and `resolve_binary()` (init) implement the same contract: explicit `shadow.binary` must be absolute + executable with **no silent fallback**; an empty value probes `/usr/bin/rill-pm-adapter` then `/usr/sbin/rill-pm-adapter` and otherwise reports not-provisioned. Resolver matrix (default present/missing, custom present/missing) is fixed by tests.
- **Honest Rill status semantics.** `rill_status()` distinguishes `disabled`/`not-provisioned`/`binary-invalid`/`starting`/`socket-unavailable`/`protocol-incompatible`/`capability-incompatible`/`available` and reports release/adapter/protocol/binary (configured+effective+source) without over-strong "has binary ⇒ available" inference.
- **`build_evidence.py` / `final_audit.py` consume real evidence.** They read `docs/rill-integration-evidence.json` and only grant Rill provenance PASS when tag identity + Ed25519 index signature + artifact integrity are all PASS, and functional integration additionally requires adapter runtime + PM Core roundtrip PASS; a hand-written SHA alone is never accepted. CI jobs are pinned to commit SHA and the old "no upstream release provisioned" comments are removed.

# Changelog

## 1.0.0-rc.5 — single-repo remediation + real Core runtime harness (2026-08-16)

- **Real Core ucode runtime harness (Layer 2).** `tools/docker-validate/harness` now executes the *actual* `performance-manager.uc` (after the same ucode-hoist the service uses) on a real OpenWrt 25.12.5 ucode, with the data-provider seam (conn/run/read/interface_dump/device_dump) re-seated to runtime-shaped fixtures. It asserts (not substring): Multi-WAN/PBR discovery from route/rule evidence (custom `isp-b`/`fiber`), underlay resolution (PPPoE→VLAN→NIC), path-specific workload class (global WireGuard does not leak into a plain WAN), nft candidate-only fingerprint masking, measurement-methodology mismatch, Conservative auto-tick gating, and Rill fail-closed on an unavailable socket. Wired into `openwrt-ucode` CI as the blocking behavioral regression.
- **`run()` portability fix.** Replaced the argv-ARRAY form (which `fs.popen` rejects on the supported OpenWrt ucode runtime, silently failing every command) with a shell-joined string where each argument is POSIX-quoted via `shell_quote()`. The secure-execution regression test was updated to assert this safe shell-quoting instead of the broken array form.
- **`rill_send()` framing fix.** Proper newline framing, partial-read/oversized/timeout/peer-closed handling (`rill_recv_frame`), validated by the Rill fail-closed harness section against a real socket.
- **WAN candidates from evidence, not naming.** `wan_candidates_evidence()` derives WANs from `ip -j` default-route/rule evidence and netifd l3/device mapping, so custom-named WANs (`isp-b`, `fiber`) are detected without `wan[0-9]+` guessing.
- **NFT ruleset fingerprint masking.** `nft_ruleset_fingerprint()` normalizes the JSON ruleset, strips volatile counters, and masks PM-owned flowtable/flow rules when `fastpath-mask-nft` is set, so only genuinely external flow-offload changes invalidate a benchmark.
- **Conservative auto-tick.** `conservative_auto_tick()` auto-applies ONLY the v0.1 safe allowlist through the full transactional safety chain (`apply_ring`), gated by health guard, benchmark-lock exclusion (`benchmark_active()`) and backoff; it never seizes preexisting values.
- **Honest Rill integration status.** `scripts/rill_contract_check.py` writes `docs/rill-integration-status.json` with three distinct fields (`pmFailClosedContract`, `upstreamIntegration`, `overallFeatureStatus`); source gates and the final audit now report the upstream integration as **blocked** (never PASS) because no upstream Rill release is provisioned this cycle.
- **Source gates = structural evidence only.** `scripts/source_gates.py` no longer claims complex behavior from substrings; it asserts authoritative forbidden-API/repo-structure guards (no Cargo/Rust reintroduced) and reports structural evidence, deferring behavioral truth to the real Core harness.
- **Exact APK verification.** `scripts/verify_apks.py` reads `.PKGINFO` (pkgname/pkgver/arch) so `performance-manager` vs `performance-manager-rill` can never be confused and a stale rc.3 artifact can never pass.
- **CI hardening.** All GitHub Actions pinned to commit SHAs; `make audit` failures no longer swallowed by `|| true`; CA bundle seeded so apk verifies TLS (no `--no-check-certificate`).
- **Goal UI honesty.** `settings.js` labels which goals are measurable for controlled A/B (`balanced`/`throughput`) versus valid-but-not-measurable (`latency`/`cpu_efficiency`), matching the Core's fail-closed `goal-unsupported-for-controlled-ab`.
- **rc.3 → rc.4 migration.** `uci-defaults/90-performance-manager` makes the new `main.conservative_auto` explicit on the preserved conffile during upgrade.

## 1.0.0-rc.3 — Rill externalization + rc.3 remedial hardening (2026-08-15)

- **Rill externalized as an external runtime dependency.** Performance Manager now only *consumes* the Rill release produced by the Rill upstream repository; it no longer vendors, compiles, cross-compiles or natively tests Rill's Rust implementation. Deleted `package/performance-manager-rill/src/` (Cargo.toml/lock, src/main.rs) and all CI jobs that installed Rust to build Rill.
- **`performance-manager-rill` is now integration glue** (make/meta package, no Rust build path): fail-closed capability gate + PM-specific service/config glue + `lib/upgrade/keep.d`. It depends on the upstream Rill runtime/path and starts nothing when the external binary is absent (`external Rill runtime not installed; integration blocked (fail-closed)`).
- **New PM↔Rill dependency contract** `contracts/rill-dependency.json` plus `scripts/rill_contract_check.py`: pins protocol API/ops, `ctx-v1:` ContextKey bounds, required capabilities, minimum Rill version and upstream release provenance (never `latest`, non-empty SHA-256); a misprovisioned/blocked upstream fails closed.
- **Core capability/protocol gate** (`external-runtime-missing`, `protocol-major-mismatch`, bounded ContextKey, shadow-only ops `status`/`observe`/`outcome`): Rill missing/unreachable/protocol-major-mismatch is reported as unavailable/incompatible and can never auto-apply or fake a recommendation.
- **Blocker 1 — Benchmark LuCI `render()` crash fixed.** Reordered the `pathSelect`/`refreshPaths()` initialization to remove the temporal-dead-zone crash; added `scripts/luci_render_smoke.js` runtime render harness (action switch + path selector rebuild) so JS `--check` no longer stands in for UI runtime PASS.
- **Blocker 2 — Goal is first-class.** `balanced`/`throughput`/`latency`/`cpu_efficiency` now enter Context, Action ranking, benchmark measurement selection, reward, recommendation, Rill request and ContextKey/evidence partition. Goals without a supported measurement (`latency`, `cpu_efficiency`) fail closed instead of silently degrading to throughput.
- **Blocker 3 — controlled A/B freezes measurement methodology.** Canonical fingerprint (host/port/direction/parallel streams/duration/protocol/tool version) recorded by the Companion (`pm_companion_agent.py`) and validated by the Core; any control/candidate mismatch ⇒ `validated=false`, no reward, no Rill outcome.
- **Blocker 4 — policy replay cedes on live drift.** If the value PM owns has changed since its lease, ownership is relinquished (`ceded-live-drift`) and the user/external value is never overwritten on replay.
- **High 9.1–9.6 整改:** runtime Topology conforms to the formal schema (`lanInterface` string, empty for the local-endpoint path); real recursive underlay chain (logical→L3→VLAN→bridge→PPPoE→tunnel→NIC/radio); Multi-WAN/PBR Path inventory built from runtime route/rule evidence (not `wan[0-9]+` naming guesses) with consistent selector; Workload Class derived from affected/evaluation paths (all seven frozen classes, never hard-coded `plain_forwarding`); Conservative automation carries real safety semantics (safe-allowlist-only, never seizes preexisting, observe/respect packet steering, transactional ownership-backed writes, Rill advisory-only); Benchmark context adds a live nft ruleset fingerprint + route/rule identity so live-only drift invalidates the experiment.
- **Audit gates upgraded from token checks to behavioral checks:** 12 classes of behavioral regression tests (`tests/test_behavior_regressions.py`) covering LuCI render smoke, runtime topology→schema, Goal semantic differentiation, methodology rejection, replay cede-on-drift, underlay fixtures, Multi-WAN/PBR fixtures, workload derivation, live firewall/route drift invalidation, Rill capability handshake, Rill missing/incompatible fail-closed, and upstream artifact provenance gate.
- **CI restructured:** `.github/workflows/ci.yml` now has `static` (incl. LuCI render smoke), `rill-contract` (contract + pinned upstream provenance, no Rust, emits `rill-consumed-manifest.json`), `openwrt-ucode` (official 25.12.5 rootfs compile of Core); the remote official SDK build moved to `.github/workflows/build-openwrt.yml` → `openwrt-sdk-build`, which builds only the packages this repository owns and uploads auditable evidence (`build-metadata.json` via `scripts/build_evidence.py`, `checksums.txt`, audit artifacts, Rill consumed manifest). Removed `rill-native` and `openwrt-sdk-build-rill`.
- Local source suite: 84 Python tests pass; contract validation, host syntax (21 checks), source gates (Phase 0–12) and resource budget all pass.

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
