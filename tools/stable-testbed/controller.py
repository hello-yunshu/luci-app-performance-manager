#!/usr/bin/env python3
"""Repository-owned Stable test logic; runners provide transport/infrastructure only.

The transport executable receives one JSON request on stdin and returns raw
observations on stdout. It may operate VMs, bridges, SSH or serial, but cannot
choose verdicts: this controller and validate_external_evidence.py do that.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256  # noqa: E402
from validate_external_evidence import evaluate_raw_facts, validate_evidence  # noqa: E402

RUNTIME_PACKAGE = "rill-runtime"

RESERVED_TRANSPORT_FIELDS = {
    "verdict", "passed", "subchecks", "validationErrors", "controller",
    "pmCommitSha", "buildRunId", "runtimeSha256", "schemaVersion", "gate",
    "artifacts", "buildArtifacts", "installedArtifacts", "environment", "benchmark",
    "upgrade", "soak", "canonical", "installPlan",
}

INSTALL_PLANS = {
    "target-core-only": {"primaryPackage": "performance-manager", "requiredPackages": ["performance-manager"], "forbiddenBusinessPackages": ["luci-app-performance-manager", "performance-manager-rill", "luci-app-performance-manager-all"]},
}
for _gate in ("target-full", "target-mutation", "hyperv", "kvm", "lan-wan-ab", "router-local-ab", "sysupgrade", "resource-soak"):
    INSTALL_PLANS[_gate] = {"primaryPackage": "luci-app-performance-manager-all", "requiredPackages": ["luci-app-performance-manager-all", RUNTIME_PACKAGE], "forbiddenBusinessPackages": ["performance-manager", "luci-app-performance-manager", "performance-manager-rill"]}
INSTALL_PLANS["lifecycle"] = {"phases": [
    {"name": "split", "requiredPackages": ["performance-manager", "luci-app-performance-manager", "performance-manager-rill", RUNTIME_PACKAGE]},
    {"name": "bundle", "requiredPackages": ["luci-app-performance-manager-all", RUNTIME_PACKAGE]},
]}

def unique(root: Path, name: str) -> Path:
    found = [p for p in root.rglob(name) if p.is_file()]
    if len(found) != 1:
        raise RuntimeError(f"expected one {name}, found {found}")
    return found[0]


def artifact_files(root: Path, metadata: dict) -> dict[str, Path]:
    result = {}
    for name, record in (metadata.get("packages") or {}).items():
        expected = record.get("apkSha256")
        filename = record.get("apkFilename") or record.get("filename")
        try:
            identity = resolve_artifact(name, expected, [root], filename)
        except ArtifactIdentityError as exc:
            raise RuntimeError(str(exc)) from exc
        result[name] = Path(identity["canonicalPath"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True)
    parser.add_argument("--controller-path", required=True)
    args = parser.parse_args(argv)
    build_root = Path(os.environ["PM_BUILD_INPUT"])
    ci_root = Path(os.environ["PM_CI_INPUT"])
    output = Path(os.environ["PM_EVIDENCE_OUT"])
    expected_sha = os.environ["PM_EXPECTED_SHA"]
    transport = os.environ.get("PM_TESTBED_TRANSPORT")
    if not transport:
        raise RuntimeError("PM_TESTBED_TRANSPORT is required; no external PASS JSON is accepted")
    build_path = unique(build_root, "build-metadata.json")
    apk_path = unique(build_root, "apk-verification.json")
    build = json.loads(build_path.read_text())
    apk = json.loads(apk_path.read_text())
    if build.get("repositoryCommitSha") != expected_sha or apk.get("pmCommitSha") != expected_sha:
        raise RuntimeError("build/APK evidence commit mismatch")
    apks = artifact_files(build_root, build)
    request = {
        "schemaVersion": 1, "operation": "execute-stable-gate", "gate": args.gate,
        "pmCommitSha": expected_sha, "buildRunId": str(build.get("workflowRunId")),
        "exactArtifacts": {name: {"path": str(path), "sha256": sha256(path)} for name, path in apks.items()},
        "runtimeSha256": (build.get("externalRuntime") or {}).get("sha256"), "ciInput": str(ci_root),
        "installPlan": INSTALL_PLANS[args.gate],
        "requirements": "execute the repository installPlan exactly; return raw installed hashes and gate observations",
    }
    completed = subprocess.run([transport], input=json.dumps(request), text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"transport failed: {completed.stderr.strip()}")
    raw = json.loads(completed.stdout)
    if not isinstance(raw, dict):
        raise RuntimeError("transport output is not an object")
    forbidden = sorted(RESERVED_TRANSPORT_FIELDS.intersection(raw))
    if forbidden:
        raise RuntimeError(f"transport may return raw facts only; reserved verdict fields present: {forbidden}")
    controller = ROOT / args.controller_path
    if not isinstance(raw.get("rawFacts"), dict):
        raise RuntimeError("transport must return exactly one rawFacts object")
    facts = raw["rawFacts"]
    installed = facts.get("installedPackages") if isinstance(facts.get("installedPackages"), dict) else {}
    installed_artifacts = {name: installed.get(name) for name in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", RUNTIME_PACKAGE, "luci-app-performance-manager-all")}
    build_artifacts = {
        name: {
            "apkSha256": record.get("apkSha256"),
            "version": record.get("pkgver"),
            "filename": record.get("apkFilename") or record.get("filename"),
        }
        for name, record in (build.get("packages") or {}).items()
    }
    evidence_schema_version = 2 if args.gate == "resource-soak" else 1
    evidence = {
        "rawFacts": facts,
        "schemaVersion": evidence_schema_version, "gate": args.gate, "pmCommitSha": expected_sha,
        "buildRunId": str(build.get("workflowRunId")), "runtimeSha256": None if args.gate == "target-core-only" else (build.get("externalRuntime") or {}).get("sha256"),
        "controller": {"source": "repository", "path": args.controller_path, "sha256": sha256(controller)},
        "subchecks": evaluate_raw_facts(raw, args.gate),
        "buildArtifacts": build_artifacts,
        "installedArtifacts": installed_artifacts,
        "durationSeconds": facts.get("durationSeconds", 0),
        "primaryPackage": "performance-manager" if args.gate == "target-core-only" else "luci-app-performance-manager-all",
        "primaryPackageSha256": (installed_artifacts.get("performance-manager") or {}).get("apkSha256") if args.gate == "target-core-only" else (installed_artifacts.get("luci-app-performance-manager-all") or {}).get("apkSha256"),
        "verdict": "PASS", "passed": True,
    }
    errors = validate_evidence(evidence, args.gate, expected_sha, require_rill=args.gate != "target-core-only",
                               minimum_duration=86400 if args.gate == "resource-soak" else 0,
                               build_metadata=build, apk_report=apk)
    evidence["passed"] = not errors
    evidence["verdict"] = "PASS" if not errors else "FAIL"
    evidence["validationErrors"] = errors
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
