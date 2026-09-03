#!/usr/bin/env python3
"""Fail-closed Stable evidence aggregator.

Every required input must be attributable to one exact PM commit. Evidence
that executed with Rill must also name the exact generic Runtime SHA-256.
Missing or non-final evidence is BLOCKED; identity contradictions are FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_external_evidence import validate_evidence

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONTRACT = json.loads((ROOT / "contracts/rill-runtime.json").read_text())

REQUIRED = {
    "source": "source-audit.json",
    "coreRuntime": "core-runtime.json",
    "rillProvenance": "rill-provenance.json",
    "rillRuntime": "rill-runtime.json",
    "rillCoreFunctional": "rill-core-integration.json",
    "openwrtSdk": "build-metadata.json",
    "apkVerification": "apk-verification.json",
    "packageComposition": "package-composition.json",
    "targetCoreOnly": "target-core-only.json",
    "targetFull": "target-full.json",
    "targetMutation": "target-mutation.json",
    "hyperV": "hyperv.json",
    "kvm": "kvm.json",
    "lanWanAb": "lan-wan-ab.json",
    "routerLocalAb": "router-local-ab.json",
    "sysupgrade": "sysupgrade.json",
    "lifecycle": "lifecycle.json",
    "resourceSoak24h": "resource-soak.json",
}
RILL_PRESENT = {
    "rillProvenance", "rillRuntime", "rillCoreFunctional", "targetFull",
    "targetMutation", "hyperV", "kvm", "lanWanAb", "routerLocalAb",
    "sysupgrade", "lifecycle", "resourceSoak24h",
}
EXTERNAL_GATES = {
    "targetCoreOnly": "target-core-only", "targetFull": "target-full",
    "targetMutation": "target-mutation", "hyperV": "hyperv", "kvm": "kvm",
    "lanWanAb": "lan-wan-ab", "routerLocalAb": "router-local-ab",
    "sysupgrade": "sysupgrade", "lifecycle": "lifecycle",
    "resourceSoak24h": "resource-soak",
}
PORTABLE_REQUIRED = {
    "source": "source-audit.json",
    "rillProvenance": "rill-provenance.json",
    "rillRuntime": "rill-runtime.json",
    "rillCoreFunctional": "rill-core-integration.json",
    "openwrtSdk": "build-metadata.json",
    "apkVerification": "apk-verification.json",
    "portableDocker": "portable-docker.json",
    "packageComposition": "package-composition.json",
}
PORTABLE_RILL_PRESENT = {"rillProvenance", "rillRuntime", "rillCoreFunctional"}


def norm(value):
    text = str(value or "BLOCKED").upper()
    if text == "PENDING" or text == "NOT_EVALUATED":
        return "BLOCKED"
    return text if text in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED"


def nested(data, path):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def verdict(name, data):
    if not isinstance(data, dict):
        return "BLOCKED", "malformed JSON object"
    candidates = {
        "source": [("sourceCandidateVerdict",)],
        "rillProvenance": [("provenanceVerdict",)],
        "rillRuntime": [("overallVerdict",)],
        "openwrtSdk": [("verdicts", "pmPackagesBuildVerdict")],
    }.get(name, [("verdict",), ("overallVerdict",)])
    for path in candidates:
        value = nested(data, path)
        if value is not None:
            return norm(value), None
    if data.get("passed") is True:
        return "PASS", None
    if data.get("passed") is False:
        return "FAIL", None
    return "BLOCKED", "verdict missing"


def commit_of(name, data):
    if name == "openwrtSdk":
        return data.get("repositoryCommitSha")
    return data.get("pmCommitSha") or data.get("commit")


def runtime_sha_of(data):
    return (
        data.get("runtimeSha256")
        or nested(data, ("runtime", "sha256"))
        or nested(data, ("artifact", "sha256"))
        or nested(data, ("artifact", "actualSha256"))
        or nested(data, ("artifact", "signedIndexSha256"))
        or nested(data, ("rill", "runtimeSha256"))
        or nested(data, ("identity", "runtimeSha256"))
    )


def combine(values):
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if any(value in {"BLOCKED", "PENDING", "NOT_EVALUATED"} for value in values):
        return "BLOCKED"
    return "PASS"


def stable_authorization(profile, overall, gates):
    """Return authorization only for complete, same-profile hardware proof."""
    if profile != "hardware" or overall != "PASS":
        return False
    return bool(EXTERNAL_GATES) and all(
        gates.get(name, {}).get("status") == "PASS" for name in EXTERNAL_GATES
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--out", default=str(ROOT / "docs/final-stable-evidence.json"))
    parser.add_argument("--profile", choices=("hardware", "portable-docker"), default="hardware")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_commit):
        parser.error("--expected-commit must be one full lowercase Git SHA")

    evidence_dir = Path(args.evidence_dir)
    def load_optional(filename):
        try:
            return json.loads((evidence_dir / filename).read_text())
        except Exception:
            return None

    required = PORTABLE_REQUIRED if args.profile == "portable-docker" else REQUIRED
    rill_present = PORTABLE_RILL_PRESENT if args.profile == "portable-docker" else RILL_PRESENT
    external_gates = {} if args.profile == "portable-docker" else EXTERNAL_GATES
    build_metadata = load_optional(required["openwrtSdk"])
    apk_report = load_optional(required["apkVerification"])
    provenance_data = load_optional(required["rillProvenance"])
    expected_runtime_sha = runtime_sha_of(provenance_data)
    gates = {}
    identities = {}
    for name, filename in required.items():
        path = evidence_dir / filename
        if not path.exists():
            gates[name] = {"status": "BLOCKED", "reason": f"missing {filename}"}
            continue
        try:
            data = json.loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            gates[name] = {"status": "FAIL", "reason": f"invalid {filename}: {exc}"}
            continue
        status, reason = verdict(name, data)
        commit = commit_of(name, data)
        runtime_sha = runtime_sha_of(data)
        identity_errors = []
        if commit != args.expected_commit:
            identity_errors.append(f"pmCommitSha={commit!r}, expected {args.expected_commit}")
        if name in rill_present and runtime_sha != expected_runtime_sha:
            identity_errors.append(f"runtimeSha256={runtime_sha!r}, expected {expected_runtime_sha}")
        if identity_errors:
            status = "FAIL"
            reason = "; ".join(identity_errors)
        if name in external_gates and status == "PASS":
            semantic_errors = validate_evidence(
                data, external_gates[name], args.expected_commit,
                require_rill=name in rill_present,
                minimum_duration=86400 if name == "resourceSoak24h" else 0,
                build_metadata=build_metadata, apk_report=apk_report,
            )
            if semantic_errors:
                status = "FAIL"
                reason = "; ".join(semantic_errors)
        gates[name] = {
            "status": status,
            "reason": reason,
            "file": filename,
            "pmCommitSha": commit,
            "runtimeSha256": runtime_sha if name in rill_present else None,
        }
        identities[name] = {"pmCommitSha": commit, "runtimeSha256": runtime_sha}

    overall = combine([gate["status"] for gate in gates.values()])
    hardware_gate_statuses = [gates[name]["status"] for name in EXTERNAL_GATES if name in gates]
    hardware_complete = args.profile == "hardware" and bool(hardware_gate_statuses) and all(
        status == "PASS" for status in hardware_gate_statuses
    )
    # Portable evidence is useful for RC/preview admission, but it is never a
    # Stable authorization input. Only the hardware profile may authorize a
    # Stable release, and only after every required external gate is PASS.
    stable_authorized = stable_authorization(args.profile, overall, gates)
    hardware_coverage = (
        "NOT_EVALUATED" if args.profile == "portable-docker"
        else "PASS" if hardware_complete else "BLOCKED"
    )
    result = {
        "schemaVersion": 1,
        "contract": "openwrt-performance-manager-stable-evidence",
        "releaseProfile": args.profile,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "pmCommitSha": args.expected_commit,
        "runtimeVersion": RUNTIME_CONTRACT["resolved"]["version"],
        "runtimeSha256": expected_runtime_sha,
        "aggregationRule": "ANY FAIL -> FAIL; otherwise any BLOCKED/PENDING/NOT_EVALUATED -> BLOCKED; otherwise PASS",
        "requiredGates": gates,
        "evidenceIdentity": identities,
        "overallVerdict": overall,
        "portableVerdict": overall if args.profile == "portable-docker" else None,
        "stableReleaseVerdict": overall if args.profile == "hardware" else "NOT_EVALUATED",
        "stableReleaseAuthorized": stable_authorized,
        "hardwareCoverage": hardware_coverage,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "overallVerdict": overall,
        "pmCommitSha": args.expected_commit,
        "runtimeSha256": expected_runtime_sha,
        "blocked": [name for name, gate in gates.items() if gate["status"] == "BLOCKED"],
        "failed": [name for name, gate in gates.items() if gate["status"] == "FAIL"],
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
