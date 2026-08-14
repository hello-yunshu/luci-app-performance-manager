# Architecture — 1.0.0-rc.2

## Authority boundary

`LuCI / CLI → ubus Core → Analyzer + Policy + Compatibility → Transaction Engine → allowlisted actuator`

Rill is a sidecar, not an actuator:

`Core → bounded UDS → Rill Shadow → advisory only → Core recommendations`

The Companion Agent is an endpoint evidence utility for explicit tests and has no router-control surface.

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
