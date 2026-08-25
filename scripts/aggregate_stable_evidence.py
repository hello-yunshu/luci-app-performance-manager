#!/usr/bin/env python3
"""Fail-closed Stable evidence aggregator.

Every required input must be attributable to one exact PM commit. Evidence
that executed with Rill must also name the exact pinned adapter SHA-256.
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
DEPENDENCY = json.loads((ROOT / "contracts/rill-dependency.json").read_text())
PINNED_ADAPTER_SHA = "a" * 64  # Legacy fixture token; release evidence supplies the real same-commit binary SHA.

REQUIRED = {
    "source": "source-audit.json",
    "coreRuntime": "core-runtime.json",
    "rillProvenance": "rill-provenance.json",
    "rillRuntime": "rill-runtime.json",
    "rillCoreFunctional": "rill-core-integration.json",
    "openwrtSdk": "build-metadata.json",
    "apkVerification": "apk-verification.json",
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


def adapter_sha_of(data):
    return (
        data.get("adapterSha256")
        or nested(data, ("adapter", "sha256"))
        or nested(data, ("artifact", "sha256"))
        or nested(data, ("artifact", "actualSha256"))
        or nested(data, ("artifact", "signedIndexSha256"))
        or nested(data, ("rill", "artifactSha256"))
        or nested(data, ("identity", "adapterSha256"))
    )


def combine(values):
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if any(value in {"BLOCKED", "PENDING", "NOT_EVALUATED"} for value in values):
        return "BLOCKED"
    return "PASS"


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
    expected_adapter_sha = adapter_sha_of(provenance_data) or PINNED_ADAPTER_SHA
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
        adapter_sha = adapter_sha_of(data)
        identity_errors = []
        if commit != args.expected_commit:
            identity_errors.append(f"pmCommitSha={commit!r}, expected {args.expected_commit}")
        if name in rill_present and adapter_sha != expected_adapter_sha:
            identity_errors.append(f"adapterSha256={adapter_sha!r}, expected {expected_adapter_sha}")
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
            "adapterSha256": adapter_sha if name in rill_present else None,
        }
        identities[name] = {"pmCommitSha": commit, "adapterSha256": adapter_sha}

    overall = combine([gate["status"] for gate in gates.values()])
    result = {
        "schemaVersion": 1,
        "contract": "openwrt-performance-manager-stable-evidence",
        "releaseProfile": args.profile,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "pmCommitSha": args.expected_commit,
        "adapterSha256": expected_adapter_sha,
        "aggregationRule": "ANY FAIL -> FAIL; otherwise any BLOCKED/PENDING/NOT_EVALUATED -> BLOCKED; otherwise PASS",
        "requiredGates": gates,
        "evidenceIdentity": identities,
        "overallVerdict": overall,
        "stableReleaseAuthorized": overall == "PASS",
        "hardwareCoverage": "NOT_EVALUATED" if args.profile == "portable-docker" else "REQUIRED",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "overallVerdict": overall,
        "pmCommitSha": args.expected_commit,
        "adapterSha256": expected_adapter_sha,
        "blocked": [name for name, gate in gates.items() if gate["status"] == "BLOCKED"],
        "failed": [name for name, gate in gates.items() if gate["status"] == "FAIL"],
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
