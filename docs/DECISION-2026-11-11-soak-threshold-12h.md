# Decision: lowering the resource-soak stability gate from 24h to 12h

**Date:** 2026-11-11
**Decided by:** repository owner (explicit instruction, not an engineering
judgement by an agent)
**Supersedes:** the 24-hour (86 400 s) resource-soak floor used through rc.10

## Decision

The Stable resource-soak gate is **12 hours (43 200 seconds)**, not 24 hours.

This is a deliberate lowering of the bar. It is not a technical optimisation,
not a re-interpretation of the old text, and not an equivalence claim.

## What this means

- A soak run of at least 43 200 s now satisfies the gate
  (`stableDurationSatisfied`, `passed`, and every validator that consumes
  `docs/RESOURCE_BUDGET.json` or `contracts/evidence/resource-soak.schema.json`).
- **12 hours is not 24 hours of stability evidence.** Any report derived from a
  12-hour run must state the measured duration and must not describe the result
  as "24-hour stability", "24h soak passed", or "equivalent to the previous
  gate". The old 24-hour claim is no longer available from this repository.
- Historical artefacts are frozen. `evidence/openwrt-resource-soak-120s-dev.json`
  (a 120-second developer sample) and the BLOCKED
  `/root/pm-soak-12h.json` device record keep their published content. Where the
  new floor still rejects them, that rejection is the expected outcome and the
  files must not be edited to make them pass.
- Log files and changelog entries written before this date keep their original
  wording; they describe what happened under the 24-hour gate.

## Where the floor lives

| Location | Role |
| --- | --- |
| `scripts/validate_external_evidence.py` (`RESOURCE_SOAK_MINIMUM_SECONDS`) | single source of truth |
| `scripts/aggregate_stable_evidence.py` | passes the constant to the validator |
| `tools/stable-testbed/controller.py` | passes the constant to the validator |
| `scripts/resource_budget.py` → `docs/RESOURCE_BUDGET.json` | `precommittedStableBudgets.minimumElapsedSeconds` |
| `contracts/evidence/resource-soak.schema.json` | `durationSeconds` minimum |
| `scripts/openwrt-resource-soak.sh` | default `PM_SOAK_SECONDS` and the `stableDurationSatisfied` comparison |
| `tests/fixtures/resource-soak-pass.json`, `tests/test_resource_soak_contract.py` | positive 43 200 s fixture and the 43 199 s negative case |

## Explicitly not changed

- `scripts/openwrt-resource-soak.sh`: the `w * 86400 / elapsed` expression
  converts a write delta into writes-per-day. It is a unit conversion, not a
  duration gate, and stays at 86 400.
- `CHANGELOG.md`, `docs/plans/2026-11-09-audit-convergence-plan.md`, and the
  historical `1.0.3` notes in `README.md` / `README.en.md`: historical records
  under the old gate.
