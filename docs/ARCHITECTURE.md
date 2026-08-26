# Architecture — 1.0.2

## Authority boundary

`LuCI / CLI → ubus Core → Analyzer + Policy + Compatibility → Transaction Engine → allowlisted actuator`

Rill is a sidecar, not an actuator:

`Core → bounded UDS → Rill Shadow → advisory only → Core recommendations`

The Companion Agent is an endpoint evidence utility for explicit tests and has no router-control surface.

### PM-owned Rill adapter

Since 1.0.1 the consumer-specific adapter is owned by Performance Manager at `integrations/performance-manager-rill-adapter/`. It links exact crates.io `rill-ml = 1.5.3`, implements only the advisory `pm-rill-shadow` v1 contract, and is packaged as target-specific `performance-manager-rill-adapter`. The arch-independent all-in-one APK does not contain native code; install it together with the target package for Rill Intelligence. No RillML Release adapter artifact is downloaded or selected; the upstream PM adapter active surface was removed in RillML 1.5.2.

- The `shadow` rill UCI section resolves explicit paths first, then `/usr/sbin/performance-manager-rill-adapter`, `/usr/bin/performance-manager-rill-adapter`, and only then legacy paths; invalid explicit paths fail closed.
- `contracts/rill-dependency.json` formalizes PM ownership, exact `rill-ml` registry dependency, protocol v1, state schema 1 and advisory authority; `scripts/rill_contract_check.py` validates it.
- Core enforces a capability/protocol gate: `external-runtime-missing`, `protocol-major-mismatch`, `RILL_PROTOCOL_API`, shadow-only ops. Rill missing/unreachable/protocol-incompatible ⇒ Rill unavailable/incompatible, fail-closed, never auto-apply, never fake recommendation.
- Ownership split: `performance-manager` owns Core; `luci-app-performance-manager` owns the LuCI UI; Performance Manager owns the adapter, packaging and release; RillML owns only generic crates and contracts.

## Core invariants

- Core is a procd-managed ucode daemon and has no hard dependency on rpcd, LuCI or Rill.
- Device writes target stable `TargetRef`; long-term policy never treats a raw runtime `eth0` name as identity.
- PPPoE/VPN logical interfaces are resolved to a stable physical/virtual-bus underlay before `ethtool` tuning.
- Multi-WAN/PBR paths carry WAN-specific route evidence and are invalidated on rtnetlink/netifd topology drift.
- Writes use fixed argv execution, fixed Action IDs and resource locks; arbitrary shell is not an API.
- Transaction order follows the frozen state machine: planned → locked → snapshotted → pending → applied → verified → awaiting_confirm/committed.
- Active transactions write a durable pending marker before runtime mutation. Same-boot Core crash fails closed to rollback; cross-boot recovery never replays a stale runtime snapshot.
- A rollback is successful only after restoration read-back succeeds.
- PM-owned ring replay uses a per-boot runtime lease. Uninstall restores only when the current live state still equals the PM-owned value; otherwise live drift is preserved and replay intent alone is removed.
- Native Packet Steering is discovered/observed/respected; its provider ownership is never seized by default.

## Analyzer

`analyze` returns structured findings with evidence and confidence rather than merely echoing recommendations. It combines path resolution, System Health Guard, Profile Contract health, native-provider evidence, capacity pressure and conservative candidates.

## Benchmark boundary

Controlled A/B is an explicit persisted session. Companion control evidence is accepted only if its role and complete frozen context match. Core then applies one reversible variable transactionally, waits for candidate evidence, restores the exact snapshot, validates health/restoration, persists the result and only then emits a learning outcome. Passive/health observations never become validated performance rewards.

## Persistence

- tmpfs: fast/deep telemetry snapshots, ordinary topology events, locks, transaction journal working copies, benchmark sessions.
- persistent `/etc/performance-manager`: active transaction pending markers, accepted PM policy intent/runtime lease, bounded history, validated Rill outcomes and Decision Ledger.
- ordinary stable telemetry observations have no persistent write amplification.
- sysupgrade keep rules preserve the intended config/policy/validated-learning roots only.
