# Implementation Status — 1.0.0-rc.6

This repository implements the frozen planning pack v0.3.2 through Phase 12 as a **source-complete release candidate** after the strict rc.1 re-audit, the 2026-08-14 independent re-audit hardening, the 2026-08-16 rc.4 single-repo remediation, and the 2026-08-18 rc.6 Rill v1.2.0 Stable real integration. "Source-complete" means the required contracts, runtime mechanisms, UI surfaces, guards, tests and target-evidence tooling exist; it does **not** claim that target/testbed gates have already passed. The independent re-audit closed: benchmark tuning-domain exclusivity (global lock + idle/stale recovery), full context fingerprint with candidate-key masking, strict non-fallback evaluation paths with a resolved-route hard gate, path-specific health, the Rill contextual bandit with formal per-op v2 IPC schema and strict JSON parsing, the target-bound Assisted Auto traffic gate, fail-closed uninstall cleanup, pinned CI toolchain/feeds, behavioral source gates and the self-contained final audit orchestrator.

### 1.0.0-rc.6 round (Rill v1.2.0 Stable real integration)

- **Rill rc.1 candidate → v1.2.0 Stable** — `contracts/rill-dependency.json` (schema `3`) pins the immutable Stable release `v1.2.0` (tag `v1.2.0` → commit `dc96fdb3bf55eacdd1c093f1be08d1c9daed4400`), its Ed25519-signed `stable` index (schema v3, publisher `rillml-examples-2026-001`) and the exact `x86_64-musl` `pm-adapter` (never `latest`/`main`/`candidate-index`). Release `1.2.0` ≠ adapter crate/binary `0.15.0` ≠ pm-rill-shadow protocol `v1`. Ambiguous `minimumRillVersion` → `minimumReleaseVersion` + `minimumAdapterVersion`.
- **Authoritative verifier** — `scripts/verify_rill_release.py` resolves the tag → commit, checks a stable/non-draft release, verifies the Ed25519 `stable`-index signature (schema 3, channel `stable`), uniquely selects the `pm-adapter`/`linux`/`x86_64`/`musl`/protocol-1 artifact and verifies actual size+SHA256 against the signed index → `docs/rill-provenance.json` / `docs/rill-integration-evidence.json`.
- **Static contract scoped** — `rill_contract_check.py` emits the static dependency/protocol contract only, never `functionalIntegration=PASS`; real status comes from the verifier + integration tests.
- **Real adapter + real protocol roundtrip** — CI `pm-rill-provenance` → `pm-rill-runtime` (boot official 25.12.5 x86/64 musl rootfs, `--version`→`0.15.0`, real `status`/`observe`/`outcome` + fail-closed negatives) → `pm-core-rill-roundtrip` (raw shipped Core + verified adapter; `ubus call performance-manager rill_status` negotiates release `1.2.0`, adapter `0.15.0`, protocol `1`, binary `/usr/bin/rill-pm-adapter`).
- **Unified fail-closed binary resolver** — Core `rill_binary_path()` ≡ init `resolve_binary()`: explicit path must be absolute + executable (no silent fallback); empty probes `/usr/bin/rill-pm-adapter` then `/usr/sbin/rill-pm-adapter`. Resolver matrix fixed by tests.
- **Honest `rill_status()`** — distinct `disabled`/`not-provisioned`/`binary-invalid`/`starting`/`socket-unavailable`/`protocol-incompatible`/`capability-incompatible`/`available`, reporting release/adapter/protocol/binary (configured+effective+source).
- **Evidence-driven verdicts** — `build_evidence.py`/`final_audit.py` read `docs/rill-integration-evidence.json`; Rill provenance PASS needs tag identity + index signature + artifact integrity, functional integration additionally needs adapter runtime + PM Core roundtrip. A hand-written SHA is never accepted.

### 1.0.0-rc.5 round (single-repo remediation + real Core harness)

- **Real Core ucode runtime harness (Layer 2)** — `tools/docker-validate/harness` executes the actual `performance-manager.uc` on real OpenWrt 25.12.5 ucode and asserts Multi-WAN/PBR evidence discovery, underlay resolution, path-specific workload, nft candidate-only masking, methodology mismatch, Conservative auto-tick gating and Rill fail-closed; wired into `openwrt-ucode` CI as the blocking behavioral regression.
- **`run()` portability fix** — argv-ARRAY → POSIX-quoted shell string (the array form is rejected by `fs.popen` on the supported runtime); regression test updated to assert safe shell-quoting.
- **`rill_send()` framing fix** — newline framing + partial/oversized/timeout/peer-closed handling.
- **WAN candidates from evidence** (`wan_candidates_evidence`) instead of `wan[0-9]+` naming.
- **nft fingerprint masking** — normalized JSON, volatile counters stripped, PM-owned flow-offload masked.
- **Conservative auto-tick** — safe-allowlist-only auto-apply through the full transactional chain, health/benchmark/backoff gated.
- **Honest Rill integration status** — `docs/rill-integration-status.json` (pmFailClosedContract / upstreamIntegration / overallFeatureStatus); source gates + final audit report the upstream integration as **blocked**, never PASS.
- **Exact APK verification** (`scripts/verify_apks.py`) via `.PKGINFO` pkgname/pkgver/arch.
- **CI hardening** — Actions pinned to SHAs; `make audit` failures not swallowed; CA-bundled TLS apk.
- **Goal UI honesty** — settings labels measurable vs non-measurable goals.
- **rc.3 → rc.4 migration** — `uci-defaults/90-performance-manager` sets the new `main.conservative_auto` on the preserved conffile.

### 1.0.0-rc.3 round (closed blockers / hardening)

- Rill is now an **external runtime dependency** (see ARCHITECTURE.md): `performance-manager-rill/src/` was deleted; `performance-manager-rill` is an integration/meta package (no Rust build path, `Build/Compile` no-op) with a fail-closed init guard; the `shadow` rill section gains a `binary` UCI option; `contracts/rill-dependency.json` + `scripts/rill_contract_check.py` formalize/validate the dependency contract; Core enforces a capability/protocol gate (`external-runtime-missing`, `protocol-major-mismatch`, `RILL_PROTOCOL_API`) that is fail-closed and never auto-applies or fakes a recommendation.
- Benchmark LuCI render crash fixed (temporal dead-zone).
- Goal is first-class: balanced/throughput/latency/cpu_efficiency enter context/ranking/measurement/reward/rill; unsupported goals fail closed.
- Controlled A/B freezes the measurement methodology fingerprint.
- Policy replay cedes on live drift; runtime Topology conforms to the formal schema; real recursive underlay chain.
- Multi-WAN/PBR resolved from runtime evidence rather than naming guesses; Workload Class derived from paths.
- Conservative now has real safety semantics.
- Benchmark context adds a live nft ruleset fingerprint.

| Phase | Source status | Evidence / boundary |
|---|---|---|
| 0 Contract Freeze | Complete | formal schemas + runtime copies/constants; frozen planning pack unchanged |
| 1 Bootstrap | Complete | independent Core, LuCI, Rill packages; procd/ubus; i18n; CI |
| 2 Capability/Topology/Target/Event | Complete | stable TargetRef, PPPoE/VPN underlay, multi-WAN paths, route/rule identity, netifd + rtnl events |
| 3 Telemetry/Health/Analyzer/Path | Complete | fast/deep telemetry, full baseline-relative health, structured evidence/confidence Analyzer |
| 4 Policy/Compatibility | Complete | integrations, provider/ownership posture and multi-WAN/fast-path guards |
| 5 Transaction/Locks/Commit-confirm | Complete | full state machine, durable pending marker, real monotonic deadline/timer, crash recovery, stale-safe rollback, per-boot ownership lease, uninstall cleanup and fail-closed prerm (removal aborts unless the daemon confirms `ok:true`); benchmark experiment locks recovered on daemon start/cleanup |
| 6 Conservative | Complete | Hyper-V ring floor; Native Packet Steering observe/respect; NIC offload observe/protect |
| 7 Benchmark | Complete under capability-first rule | global `benchmark:global` tuning-domain lock (acquire-before-session-write, release on every terminal path, idle-expiry recovery), full context fingerprint with candidate-key masking and `benchmark-context-drift`, strict non-fallback evaluation path, forwarding requires resolved rtnl route (`evaluation-route-unresolved`), path-specific health, real control→candidate→rollback→reward orchestrator; exact reversible providers execute; generic qdisc/unknown SFE remain explicitly blocked when exact restore is not provable |
| 8 Rill Intelligence | Complete | external immutable dependency pinned to released Rill Stable v1.2.0 (Ed25519-signed `stable` index, exact x86_64-musl pm-adapter, never `latest`); formal dependency contract (`contracts/rill-dependency.json`, `scripts/verify_rill_release.py`, `scripts/rill_contract_check.py`); capability/protocol gate (fail-closed on missing/mismatched runtime); pm-rill-shadow protocol v1 (status/observe/outcome), strict JSON parser, context-partitioned model keyed by Core-computed ContextKey, per-operation validation, stale-recommendation invalidation on drift, bounded persistent ledger/model, strict Shadow protocol |
| 9 Recommend | Complete | deterministic legal actions + separate Rill advisory with no actuation authority |
| 10 Assisted Auto | Complete, opt-in only | assisted + explicit switch + maintenance + Health Guard + safe allowlist; low-traffic gate bound to the selected action's own target runtime (`assisted-previous-<runtime>.json`), action chosen before gating |
| 11 Platforms | Complete for RC | Generic x86, Hyper-V, KVM/Proxmox-compatible guest detection/guidance |
| 12 Companion | Complete | `pm-companion/v2` endpoint evidence, exact context binding, no router mutation |

## Stable-only evidence still required

1. Official OpenWrt 25.12.x x86_64 rootfs and SDK CI plus the `rill-contract` gate must actually pass (Rill itself is external; no native Rust build is required here).
2. Core-alone boot/runtime on real OpenWrt must pass.
3. Hyper-V and KVM hotplug/TargetRef/replay/rollback fixtures must pass.
4. Explicit forwarding/router-local A/B testbeds must pass.
5. Sysupgrade and 24h+ resource/write soak must pass.

Use `scripts/openwrt-target-gate.sh`, `scripts/openwrt-sysupgrade-gate.sh`, `scripts/openwrt-resource-soak.sh` and `docs/RELEASE_CHECKLIST.md`. These are target evidence gates, not unresolved source placeholders.
