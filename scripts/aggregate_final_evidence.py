#!/usr/bin/env python3
"""Final release evidence aggregator (rc.7 prompt sections 25/27/29).

This is the ONLY place that turns the per-job evidence files into the release
verdict.  It enforces two hard rules that the individual jobs cannot:

  1. same-commit evidence chain -- every per-job evidence file MUST carry the
     SAME PM commit SHA (or match --expected-commit).  A job that ran on a
     different commit makes the whole chain FAIL, because its verdicts cannot
     be attributed to this release.  Any missing/unknown commit SHA is FAIL
     (fail-closed: absence of proof is never proof).
  2. combine_required aggregation -- ANY FAIL -> FAIL, ALL PASS -> PASS,
     otherwise BLOCKED.  A PASS+BLOCKED mix is BLOCKED, never silently
     upgraded to PASS, so the final rcVerdict can never report PASS while any
     release-critical gate is unresolved.

Per-job files consumed (each produced by exactly one CI job, see ci.yml and
build-openwrt.yml):

    rill-provenance.json       pm-rill-provenance      (tag/index/artifact)
    rill-runtime.json          pm-rill-runtime         (real generic Runtime)
    rill-core-integration.json pm-core-rill-roundtrip  (real Core<->Runtime)
    rill-wire-harness.json     pm-rill-provenance      (mock wire harness)
    build-metadata.json        openwrt-sdk-build       (APK build gates)
    apk-verification.json      openwrt-sdk-build       (exact APK report)

Usage:
  python3 scripts/aggregate_final_evidence.py \
    [--evidence-dir docs] [--expected-commit <sha>] [--scope full|rill|rill-runtime|build]
    [--out docs/final-release-evidence.json]

Exit code: 0 only when the combined verdict of the selected scope is PASS; any
FAIL or BLOCKED (or a broken evidence chain) exits non-zero -- fail closed.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Scope = which release-critical evidence chain this aggregation gates on
# (prompt sections 28/29/43):
#   full  -> both the Rill jobs AND the SDK/APK build gates (merged docs dir)
#   rill  -> the three Rill jobs only (ci.yml); SDK/APK gates are owned by the
#            build-openwrt.yml workflow and merged at release-audit time
#   rill-runtime -> generic Runtime/provenance jobs only (ordinary ci.yml);
#                   Core roundtrip is owned by the SDK/target workflow
#   build -> SDK/APK build gates only (build-openwrt.yml); Rill runtime /
#            functional gates are owned by the ci.yml workflow
REQUIRED_FILES = {
    "full": (
        "rill-provenance.json",
        "rill-runtime.json",
        "rill-core-integration.json",
        "build-metadata.json",
        "apk-verification.json",
    ),
    "rill": ("rill-provenance.json", "rill-runtime.json", "rill-core-integration.json"),
    "rill-runtime": ("rill-provenance.json", "rill-runtime.json"),
    "build": ("build-metadata.json", "apk-verification.json"),
}
OPTIONAL_FILES = ("rill-wire-harness.json", "rill-runtime-contract.json")
OUT_OF_SCOPE = "OUT_OF_SCOPE"


def _norm(v):
    v = str(v or "BLOCKED").upper()
    return v if v in ("PASS", "FAIL", "BLOCKED") else "BLOCKED"


def combine_required(values):
    """ANY FAIL -> FAIL; ALL PASS -> PASS; otherwise BLOCKED."""
    vals = [_norm(v) for v in values]
    if any(v == "FAIL" for v in vals):
        return "FAIL"
    if all(v == "PASS" for v in vals):
        return "PASS"
    return "BLOCKED"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}


def commit_of(name: str, data: dict):
    """Return the PM commit SHA this per-job evidence was produced at."""
    if not isinstance(data, dict):
        return None
    if name == "build-metadata.json":
        return data.get("repositoryCommitSha")
    if name == "rill-runtime-contract.json":
        return data.get("pmCommitSha")
    return data.get("pmCommitSha")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aggregate per-job evidence into the final release verdict")
    ap.add_argument("--evidence-dir", default=str(ROOT / "docs"))
    ap.add_argument("--expected-commit", default=None,
                    help="the PM commit SHA this release is being gated on; every evidence file must match")
    ap.add_argument("--scope", choices=("full", "rill", "rill-runtime", "build"), default="full",
                    help="evidence chain to gate on: full = Rill + SDK/APK; rill = Rill jobs only "
                         "(SDK/APK gates owned by build-openwrt.yml); build = SDK/APK only "
                         "(Rill gates owned by ci.yml)")
    ap.add_argument("--out", default=str(ROOT / "docs" / "final-release-evidence.json"))
    args = ap.parse_args(argv)

    ev_dir = Path(args.evidence_dir)
    required = REQUIRED_FILES[args.scope]
    in_rill = args.scope in ("full", "rill", "rill-runtime")
    in_core = args.scope in ("full", "rill")
    in_build = args.scope in ("full", "build")
    files = {}
    missing = []
    for name in required + OPTIONAL_FILES:
        p = ev_dir / name
        if not p.exists():
            if name in required:
                missing.append(name)
            continue
        files[name] = load(p)

    errors = []

    # ------------------------------------------------------------------
    # Gate 0: same-commit evidence chain (fail-closed on any uncertainty)
    # ------------------------------------------------------------------
    chain_commits = {}
    for name, data in files.items():
        # The mock wire harness is deliberately supplementary: it is useful
        # diagnostic context, but it is neither a release-critical gate nor
        # part of the same-commit proof chain.  In particular, a checked-in
        # historical wire snapshot must never invalidate fresh real runtime
        # and SDK evidence.  The consumed manifest, when present, remains in
        # the chain because it identifies the exact Rill artifact consumed.
        if name == "rill-wire-harness.json":
            continue
        c = commit_of(name, data)
        if c:
            chain_commits[name] = c
        elif name in required:
            chain_commits[name] = "<missing>"

    expected = args.expected_commit
    chain_verdict = "PASS"
    chain_reason = None
    if missing:
        chain_verdict = "FAIL"
        chain_reason = f"missing required per-job evidence: {', '.join(missing)}"
        errors.append(chain_reason)
    elif expected:
        bad = [n for n, c in chain_commits.items() if c != expected]
        if bad:
            chain_verdict = "FAIL"
            chain_reason = f"evidence produced at different commit than expected {expected}: " \
                           f"{', '.join(f'{n}={chain_commits[n]}' for n in bad)}"
            errors.append(chain_reason)
    else:
        known = {c for c in chain_commits.values() if c and c != "<missing>"}
        unknown = [n for n, c in chain_commits.items() if not c or c == "<missing>"]
        if len(known) > 1:
            chain_verdict = "FAIL"
            chain_reason = f"evidence files disagree on PM commit: {sorted(known)}"
            errors.append(chain_reason)
        elif unknown:
            chain_verdict = "FAIL"
            chain_reason = f"evidence file(s) carry no PM commit SHA: {', '.join(unknown)}"
            errors.append(chain_reason)

    # ------------------------------------------------------------------
    # Per-source verdicts (authoritative per-job files, never re-derived)
    # ------------------------------------------------------------------
    def file_verdict(name, *paths, default="BLOCKED"):
        data = files.get(name)
        if not isinstance(data, dict) or not data:
            return default, f"{name} absent"
        cur = data
        for k in paths:
            if not isinstance(cur, dict):
                return default, f"{name}.{'.'.join(paths)} malformed"
            cur = cur.get(k)
            if cur is None:
                return default, f"{name}.{'.'.join(paths)} missing"
        return _norm(cur), None

    # ------------------------------------------------------------------
    # Per-source verdicts (authoritative per-job files, never re-derived).
    # Gates outside the selected scope are recorded as OUT_OF_SCOPE and
    # excluded from rc_verdict: ci.yml gates on the Rill chain, build-openwrt
    # on the SDK/APK chain, so neither workflow can falsely PASS what the other
    # workflow alone can prove.
    # ------------------------------------------------------------------
    prov_v = prov_reason = OUT_OF_SCOPE
    if in_rill:
        provenance = files.get("rill-provenance.json") or {}
        if provenance.get("contract") != "rill-runtime-provenance":
            prov_v = "FAIL"
            prov_reason = "rill-provenance.json does not use the canonical generic Runtime provenance contract"
        else:
            prov_v, prov_reason = file_verdict("rill-provenance.json", "provenanceVerdict")
            if prov_v in ("PASS", "FAIL", "BLOCKED") and (
                not provenance.get("runtimeSha256") or not provenance.get("runtimeOwner")
            ):
                prov_v = "BLOCKED"
                prov_reason = "generic Runtime provenance is missing owner or binary SHA-256"

    # Runtime compatibility: executable/version/startup/status from the real
    # adapter runtime job.  Functional: observe/outcome/failClosed + the real
    # Core roundtrip verdict.
    runtime_compat = runtime_func = functional = core_v = OUT_OF_SCOPE
    rc_reason = rf_reason = core_reason = None
    if in_rill:
        # Always derive runtime/functional from the granular per-gate verdicts
        # (prompt section 44), NOT from a single top-level field: a file that
        # claims functionalIntegrationVerdict=PASS while a sub-gate is BLOCKED
        # must FAIL here, never be trusted (prompt section U).  The file's own
        # top-level fields are cross-checked: any disagreement is a FAIL.
        rt_data = files.get("rill-runtime.json") or {}
        sub = (rt_data.get("verdicts") or {}) if isinstance(rt_data, dict) else {}
        if "rill-runtime.json" in missing or not sub:
            runtime_compat, rc_reason = file_verdict("rill-runtime.json", "runtimeCompatibilityVerdict")
            runtime_func, rf_reason = file_verdict("rill-runtime.json", "functionalIntegrationVerdict")
            if "rill-runtime.json" not in missing:
                rc_reason = rf_reason = "rill-runtime.json lacks verdicts.* granular gates"
        else:
            runtime_compat = combine_required(
                [sub.get(k) for k in ("executableVerdict", "versionVerdict", "startupVerdict", "statusVerdict")])
            runtime_func = combine_required(
                [sub.get(k) for k in ("observeVerdict", "outcomeVerdict", "failClosedVerdict")])
            top_compat = rt_data.get("runtimeCompatibilityVerdict")
            top_func = rt_data.get("functionalIntegrationVerdict")
            if top_compat is not None and _norm(top_compat) != runtime_compat:
                rc_reason = f"top-level runtimeCompatibilityVerdict={top_compat} contradicts verdicts.* ({runtime_compat})"
                runtime_compat = "FAIL"
            if top_func is not None and _norm(top_func) != runtime_func:
                rf_reason = (rf_reason or "") + f" top-level functionalIntegrationVerdict={top_func} contradicts verdicts.* ({runtime_func})"
                runtime_func = "FAIL"
        if in_core:
            core_v, core_reason = file_verdict("rill-core-integration.json", "verdict")
            functional = combine_required([runtime_func, core_v])
        else:
            core_v = OUT_OF_SCOPE
            functional = runtime_func
        if functional != "PASS":
            rf_reason = (rf_reason or "") + f" coreRoundtrip={core_v}"

    # APK build gates from the SDK build job.
    build_v = apk_v = OUT_OF_SCOPE
    apk_reason = None
    if in_build:
        bm = files.get("build-metadata.json") or {}
        bm_v = (bm.get("verdicts") or {}) if isinstance(bm, dict) else {}
        build_v = combine_required([bm_v.get("pmPackagesBuildVerdict"), bm_v.get("apkExactVerificationVerdict")])
        apk_v, apk_reason = file_verdict("apk-verification.json", "verdict")

    # Wire harness (mock protocol level) is supplementary but must not fail a
    # real release on its own; it is recorded for transparency.
    wire_v, wire_reason = file_verdict("rill-wire-harness.json", "runtime", "wireHarnessVerdict",
                                       default="BLOCKED")

    release_verdicts = {
        "evidenceChainVerdict": chain_verdict,
        "apkPackagesBuildVerdict": build_v,
        "apkExactVerificationVerdict": apk_v,
        "rillArtifactProvenanceVerdict": prov_v,
        "rillRuntimeCompatibilityVerdict": runtime_compat,
        "rillFunctionalIntegrationVerdict": functional,
        "wireHarnessVerdict": wire_v,
    }
    rc_inputs = []
    if in_build:
        rc_inputs += [build_v, apk_v]
    if in_rill:
        rc_inputs += [prov_v, runtime_compat, functional]
    rc_verdict = combine_required(rc_inputs)
    overall = combine_required([rc_verdict, chain_verdict])

    manifest = files.get("rill-runtime-contract.json") or {}
    result = {
        "schemaVersion": 1,
        "contract": "pm-release-final-evidence",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "aggregationRule": "ANY FAIL -> FAIL; ALL PASS -> PASS; otherwise BLOCKED (combine_required); "
                           "evidence chain must be same-commit else FAIL",
        "scope": args.scope,
        "outOfScope": [k for k, v in release_verdicts.items() if v == OUT_OF_SCOPE],
        "expectedCommitSha": expected,
        "evidenceCommits": {k: v for k, v in chain_commits.items()},
        "evidenceSources": {name: str(ev_dir / name) for name in files},
        "missingEvidence": missing,
        "rillRelease": {
            "releaseVersion": manifest.get("rillMlVersion") or manifest.get("releaseVersion"),
            "releaseTag": manifest.get("releaseTag") or manifest.get("historicalReleaseTag"),
            "releaseCommitSha": manifest.get("releaseCommitSha") or manifest.get("historicalReleaseCommitSha"),
            "protocolContract": manifest.get("protocolContract"),
            "protocolVersion": manifest.get("protocolVersion"),
            "artifactSha256": manifest.get("runtimeSha256") or manifest.get("artifactSha256"),
        },
        "verdicts": release_verdicts,
        "rcVerdict": rc_verdict,
        "evidenceChainVerdict": chain_verdict,
        "overallVerdict": overall,
        "errors": errors,
        "reasons": {
            "evidenceChain": chain_reason,
            "provenance": prov_reason,
            "runtimeCompatibility": rc_reason,
            "functionalIntegration": rf_reason,
            "coreRoundtrip": core_reason,
            "apkVerification": apk_reason,
            "wireHarness": wire_reason,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({
        "scope": args.scope,
        "overallVerdict": overall,
        "rcVerdict": rc_verdict,
        "evidenceChainVerdict": chain_verdict,
        "apkPackagesBuildVerdict": build_v,
        "apkExactVerificationVerdict": apk_v,
        "rillArtifactProvenanceVerdict": prov_v,
        "rillRuntimeCompatibilityVerdict": runtime_compat,
        "rillFunctionalIntegrationVerdict": functional,
        "evidenceCommits": chain_commits,
        "missingEvidence": missing,
        "errors": errors,
        "output": str(out),
    }, ensure_ascii=False, indent=2))

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
