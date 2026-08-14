# Benchmark Protocol — 1.0.0-rc.2

## Measurement classes

- `controlled_ab`: strongest evidence; explicit Companion evidence, exact frozen context and exactly one reversible candidate variable are required.
- `passive_before_after`: contextual observation only; `validated=false` and never a reward label.
- `health_only`: safety observation only; `validated=false` and never performance proof.

## Local vs forwarding

- Local endpoint evaluation is used for local CC, buffers and busy-poll classes.
- Forwarding evaluation is mandatory for IRQ/backlog/budget, NIC/coalescing, tx queue and fast-path classes and uses an explicit `path:lan-to-<wan>` identity.
- In multi-WAN/PBR environments the selected path carries a WAN-specific default-route identity derived from `ip -j route/rule` evidence. Any capability/topology/route drift invalidates the session.

## Controlled A/B state machine

```text
begin
  → persist session + frozen capabilityHash/topologyGeneration/routeIdentity
  → awaiting_control
  → ingest pm-companion/v2 control evidence
  → acquire provider resource lock
  → snapshot exact provider state + baseline health
  → apply exactly one candidate value
  → read-back + baseline-relative Health Guard
  → arm monotonic rollback deadline
  → candidate_applied
  → ingest pm-companion/v2 candidate evidence
  → rollback candidate and verify restoration
  → compare control/candidate
  → persist validated result
  → only then send validated outcome to Rill
```

A session/result persistence failure is a hard failure. If candidate state has already been applied, Core restores it before returning an error. Rill never receives a reward if the validated result cannot first be persisted.

## Provider boundary

The frozen Phase-7 catalog is implemented capability-first. Providers with a provable exact inverse are executable. A generic qdisc replacement and unknown third-party SFE are deliberately capability-blocked when the current system cannot provide an exact reversible contract; the project does not fake “completion” by guessing rollback syntax.

## Companion Agent

`companion/pm_companion_agent.py` emits `pm-companion/v2` evidence containing:

- sessionId / phase / actionId / pathId
- topologyGeneration / routeIdentity / capabilityHash
- endpoint role (`lan-client` or `router-local-client`)
- measured throughput

The Companion cannot mutate router configuration. Endpoint evidence is necessary but not sufficient: Core still owns compatibility, locks, candidate transaction, health validation, rollback and final reward eligibility.
