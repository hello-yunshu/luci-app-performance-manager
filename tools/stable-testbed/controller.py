#!/usr/bin/env python3
"""Repository-owned Stable test logic; runners provide transport/infrastructure only.

The transport executable receives one JSON request on stdin and returns raw
observations on stdout. It may operate VMs, bridges, SSH or serial, but cannot
choose verdicts: this controller and validate_external_evidence.py do that.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_external_evidence import PIN, validate_evidence  # noqa: E402

RESERVED_TRANSPORT_FIELDS = {
    "verdict", "passed", "subchecks", "validationErrors", "controller",
    "pmCommitSha", "buildRunId", "adapterSha256", "schemaVersion", "gate",
}

GATE_CHECKS = {
    "target-core-only": ["openwrt2512", "x8664", "coreStarted", "ubusReady", "statusValid", "analyzeValid", "topologyValid", "capabilitiesValid", "noStaleLocks"],
    "target-full": ["exactPackagesInstalled", "serviceUserRestricted", "stateDirectoryRestricted", "coreConnectedExactAdapter", "rillStatusReady", "advisoryOnlyAuthority"],
    "target-mutation": ["legalCandidate", "beforeSnapshotExact", "applyExecuted", "readbackExact", "manualRollback", "restorationExact", "secondApply", "cleanupComplete", "ownershipClean", "packetSteeringNotSeized", "noStaleState"],
    "hyperv": ["hypervisorVerified", "vmbusIdentity", "hvNetvscDriver", "hotplugObserved", "targetRefStable", "replayTested", "rollbackExact"],
    "kvm": ["hypervisorVerified", "pciIdentity", "nicDriverRecorded", "hotplugObserved", "targetRefStable", "replayTested", "rollbackExact"],
    "lan-wan-ab": ["realLanClient", "realWanEndpoint", "routeResolved", "rtnlRouteProvider", "sameMethodology", "oneVariable", "mutationVerified", "rollbackExact", "healthPass", "validatedReward", "rillOutcomeFinal"],
    "router-local-ab": ["routerLocalClient", "localEndpointPath", "sameMethodology", "oneVariable", "mutationVerified", "rollbackExact", "validatedReward", "rillOutcomeFinal"],
    "sysupgrade": ["preIdentityRecorded", "postIdentityRecorded", "bootIdChanged", "configPreserved", "policyPreserved", "exactAdapterAfterUpgrade", "noUnsafePendingMutation", "coreStartedClean"],
    "lifecycle": ["install", "serviceStart", "restart", "upgradeReinstall", "configPreserved", "rillOptional", "uninstallCleanup", "reinstall", "noStaleState"],
    "resource-soak": ["rillPresent", "sampledResources", "noCoreRestart", "noRillRestart", "idleObserveZero", "idleAdapterPersistenceZero", "idleJournalWritesZero", "stateBoundsPass", "historyBoundsPass"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(root: Path, name: str) -> Path:
    found = [p for p in root.rglob(name) if p.is_file()]
    if len(found) != 1:
        raise RuntimeError(f"expected one {name}, found {found}")
    return found[0]


def artifact_files(root: Path, metadata: dict) -> dict[str, Path]:
    result = {}
    for name, record in (metadata.get("packages") or {}).items():
        expected = record.get("apkSha256")
        matches = [p for p in root.rglob("*.apk") if p.is_file() and sha256(p) == expected]
        if len(matches) != 1:
            raise RuntimeError(f"{name}: exact APK {expected} not uniquely present")
        result[name] = matches[0]
    return result


def evaluate_raw_facts(raw: dict, gate: str) -> dict[str, bool]:
    """Derive repository-owned subchecks from raw observations.

    A transport may report measurements, identities, counters and installed
    bytes under ``rawFacts``. It cannot submit a verdict-shaped object. Missing
    facts intentionally evaluate false and keep the gate blocked.
    """
    facts = raw.get("rawFacts")
    if not isinstance(facts, dict):
        return {name: False for name in GATE_CHECKS[gate]}
    environment = facts.get("environment") or {}
    process = facts.get("process") or {}
    packages = facts.get("installedPackages") or {}
    checks = {}
    if gate == "target-core-only":
        checks = {
            "openwrt2512": environment.get("release") == "25.12.5",
            "x8664": environment.get("target") == "x86/64",
            "coreStarted": process.get("corePid", 0) > 0,
            "ubusReady": facts.get("ubusSocketReady") is True,
            "statusValid": facts.get("statusResponseValid") is True,
            "analyzeValid": facts.get("analyzeResponseValid") is True,
            "topologyValid": facts.get("topologyEvidenceValid") is True,
            "capabilitiesValid": facts.get("capabilitiesEvidenceValid") is True,
            "noStaleLocks": facts.get("staleLocks") == 0,
        }
    elif gate == "hyperv":
        checks = {"hypervisorVerified": environment.get("hypervisor") == "Hyper-V", "vmbusIdentity": bool(environment.get("vmbusId")), "hvNetvscDriver": environment.get("nicDriver") == "hv_netvsc", "hotplugObserved": facts.get("hotplug", {}).get("before") != facts.get("hotplug", {}).get("after"), "targetRefStable": facts.get("targetRefStableId") is True, "replayTested": facts.get("replayCount", 0) > 0, "rollbackExact": facts.get("rollback", {}).get("before") == facts.get("rollback", {}).get("after")}
    elif gate == "kvm":
        checks = {"hypervisorVerified": environment.get("hypervisor") in {"KVM", "QEMU"}, "pciIdentity": bool(environment.get("pciId")), "nicDriverRecorded": bool(environment.get("nicDriver")), "hotplugObserved": facts.get("hotplug", {}).get("before") != facts.get("hotplug", {}).get("after"), "targetRefStable": facts.get("targetRefStableId") is True, "replayTested": facts.get("replayCount", 0) > 0, "rollbackExact": facts.get("rollback", {}).get("before") == facts.get("rollback", {}).get("after")}
    else:
        # Do not accept a verdict-shaped ``observed`` map. These gates need a
        # gate-specific evaluator over named raw measurements before they can
        # be admitted as evidence; until then they remain fail-closed.
        checks = {name: False for name in GATE_CHECKS[gate]}
    return checks


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
        "adapterSha256": PIN, "ciInput": str(ci_root),
        "requirements": "install exact local APKs; return raw installed hashes and gate observations",
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
    evidence = {
        **raw,
        "schemaVersion": 1, "gate": args.gate, "pmCommitSha": expected_sha,
        "buildRunId": str(build.get("workflowRunId")), "adapterSha256": None if args.gate == "target-core-only" else PIN,
        "controller": {"source": "repository", "path": args.controller_path, "sha256": sha256(controller)},
        "subchecks": evaluate_raw_facts(raw, args.gate),
        "primaryPackage": "performance-manager" if args.gate == "target-core-only" else "luci-app-performance-manager-all",
        "primaryPackageSha256": ((raw.get("artifacts") or {}).get("performance-manager") or {}).get("apkSha256") if args.gate == "target-core-only" else ((raw.get("artifacts") or {}).get("luci-app-performance-manager-all") or {}).get("apkSha256"),
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
