# Rill Smart Decision Model v2

Performance Manager owns the product policy boundary: the stable feature
vector, action legality, learning-stage gates, confidence thresholds, drift
handling, cooldowns, explainability and Core transaction execution. The
external `/usr/bin/rill-runtime` owns generic ranking and online learning. It
never receives an actuator or router-mutation authority.

## Runtime v3 input

Core sends a generic Runtime v3 envelope over a bounded stdin/stdout subprocess call. The decide
payload contains a ContextKey, goal, current health/topology evidence and the
legal action candidates. Every candidate carries a fixed 20-dimensional
feature vector defined by `contracts/rill-feature-schema.json`; missing values
are neutral zeroes, and the schema hash plus model generation are bound into
the request. The action list always contains `pm.noop`. Runtime IDs include a
bounded digest of the stable target and evaluation paths, so equal business
Action IDs cannot collide across NICs or WAN paths.

The feature vector is deterministic and includes interval-derived byte rate,
packet rate, drop/error ratio, CPU busy, softirq pressure and bounded memory
pressure, plus health, topology/path, workload, integration, target and
action-family signals. The first telemetry snapshot is neutral; cumulative
boot counters are never treated as live utilization. Raw interface names,
shell commands and mutable device identifiers are not used as model features.

## Unified selector

Conservative and Assisted Auto call the same Core selector. Conservative can
consider only the safe direct allowlist. Assisted additionally requires its
explicit opt-in, maintenance window, low-traffic and health gates. Both modes
reject benchmark-only actions for direct Apply. A Runtime recommendation can
influence Auto only when all of these are true:

1. Runtime is available and the response is valid for the current request.
2. The context is `ready`, with at least 8 validated controlled-A/B samples.
3. Confidence meets the configured threshold (0.65 Conservative, 0.75
   Assisted by default).
4. The exact decision binding still matches context, goal, target and action.
5. No performance distribution drift or action cooldown blocks execution.
6. The selected action remains legal and in the Core safe allowlist.

Otherwise Core records the refusal reason and chooses a deterministic safe
fallback or `pm.noop`. `pm.noop` is always available, has no execution
authority and never mutates device state. Benchmark recommendations are
displayed as benchmark-only and require an explicit controlled session.

## Learning stages and drift

Each bounded ContextKey tracks validated samples, reward history, per-action
attempt/success/failure/rollback counts, last reward, cooldown and a rolling reward
distribution. Stages are:

- `cold`: fewer than 3 validated samples; no Rill influence.
- `warming`: 3–7 validated samples; advisory ranking only.
- `ready`: at least 8 samples and no active drift; eligible subject to
  confidence and safety gates.
- `drifted`: the rolling distribution differs from its baseline beyond the
  configured threshold (0.20 default); Rill Auto is paused until 3 new valid
  samples recover the context.

The state file is bounded and versioned at
`/etc/performance-manager/rill/smart-state-v2.json`. Invalid or incompatible
state is ignored safely and never replayed into device configuration.

## Reward and evidence

Only the controlled A/B path may produce a validated learning reward. Core
requires compatible control/candidate evidence, captures throughput, latency
and CPU telemetry, verifies health, rolls back the exact transaction, and
persists the result before sending Runtime feedback. Reward v2 is goal-aware:

- `throughput`: throughput delta;
- `latency`: 50% median-latency improvement plus 50% p95-latency improvement;
- `cpu_efficiency`: inverse CPU-busy delta at comparable throughput;
- `balanced`: weighted throughput/latency/CPU efficiency.

Missing required measurements, methodology mismatch, health regression or
failed rollback yields `measurementQuality=invalid`; it never updates Smart
learning or Runtime feedback. Passive, health-only and safe-direct Auto
execution evidence remain non-training evidence. Only a validated controlled
A/B outcome trains Smart History and sends Runtime feedback.

## Explainability and UI

`recommendations` exposes the selected action, source, confidence, learning
stage, legal/auto eligibility, refusal reason, ranking and drift state. The
Rill LuCI view shows Runtime status, last decision, last reward, ranking,
learning stage, minimum samples, drift and an explicit refresh action. The
`rill_refresh` RPC is read-only, ACL-gated and never applies an action.
