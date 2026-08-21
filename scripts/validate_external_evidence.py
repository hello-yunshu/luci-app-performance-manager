#!/usr/bin/env python3
"""Gate-specific, fail-closed validator for Stable testbed evidence."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "contracts/rill-dependency.json").read_text())["upstream"]["adapter"]["sha256"]
SHA256 = re.compile(r"[0-9a-f]{64}")

GATE_CHECKS = {
    "target-core-only": ["openwrt2512", "x8664", "coreStarted", "ubusReady", "statusValid",
                         "analyzeValid", "topologyValid", "capabilitiesValid", "noStaleLocks"],
    "target-full": ["exactPackagesInstalled", "serviceUserRestricted", "stateDirectoryRestricted",
                    "coreConnectedExactAdapter", "rillStatusReady", "advisoryOnlyAuthority"],
    "target-mutation": ["legalCandidate", "beforeSnapshotExact", "applyExecuted", "readbackExact",
                        "manualRollback", "restorationExact", "secondApply", "cleanupComplete",
                        "ownershipClean", "packetSteeringNotSeized", "noStaleState"],
    "hyperv": ["hypervisorVerified", "vmbusIdentity", "hvNetvscDriver", "hotplugObserved",
               "targetRefStable", "replayTested", "rollbackExact"],
    "kvm": ["hypervisorVerified", "pciIdentity", "nicDriverRecorded", "hotplugObserved",
            "targetRefStable", "replayTested", "rollbackExact"],
    "lan-wan-ab": ["realLanClient", "realWanEndpoint", "routeResolved", "rtnlRouteProvider",
                   "sameMethodology", "oneVariable", "mutationVerified", "rollbackExact",
                   "healthPass", "validatedReward", "rillOutcomeFinal"],
    "router-local-ab": ["routerLocalClient", "localEndpointPath", "sameMethodology", "oneVariable",
                        "mutationVerified", "rollbackExact", "validatedReward", "rillOutcomeFinal"],
    "sysupgrade": ["preIdentityRecorded", "postIdentityRecorded", "bootIdChanged", "configPreserved",
                   "policyPreserved", "exactAdapterAfterUpgrade", "noUnsafePendingMutation", "coreStartedClean"],
    "lifecycle": ["install", "serviceStart", "restart", "upgradeReinstall", "configPreserved",
                  "rillOptional", "uninstallCleanup", "reinstall", "noStaleState"],
    "resource-soak": ["rillPresent", "sampledResources", "noCoreRestart", "noRillRestart",
                      "idleObserveZero", "idleAdapterPersistenceZero", "idleJournalWritesZero",
                      "stateBoundsPass", "historyBoundsPass"],
}
RILL_GATES = set(GATE_CHECKS) - {"target-core-only"}
PRIMARY_PACKAGE = "luci-app-performance-manager-all"


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _schema_errors(value: Any, schema: dict[str, Any], schema_dir: Path,
                   location: str = "evidence") -> list[str]:
    """Validate the deliberately small JSON-Schema subset used by evidence.

    Stable target runners must not depend on PyPI/network access.  This checks
    every keyword present in contracts/evidence (including local refs/allOf,
    required, types, constants, enums, patterns, minima and object bounds).
    Unsupported schema keywords fail closed instead of being silently ignored.
    """
    errors: list[str] = []
    supported = {"$schema", "$id", "$ref", "allOf", "type", "additionalProperties",
                 "required", "properties", "items", "const", "enum", "pattern", "minimum"}
    unknown = set(schema) - supported
    if unknown:
        return [f"{location}: unsupported schema keywords {sorted(unknown)}"]
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or "://" in ref or ref.startswith("/"):
            return [f"{location}: unsafe schema ref {ref!r}"]
        ref_path = (schema_dir / ref).resolve()
        if ref_path.parent != schema_dir.resolve() or not ref_path.is_file():
            return [f"{location}: unresolved schema ref {ref!r}"]
        return _schema_errors(value, json.loads(ref_path.read_text()), schema_dir, location)
    for idx, child in enumerate(schema.get("allOf", [])):
        errors.extend(_schema_errors(value, child, schema_dir, f"{location}.allOf[{idx}]"))
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, choice) for choice in choices):
            return errors + [f"{location}: expected type {choices}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: value does not equal schema const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value is outside schema enum")
    if "pattern" in schema and isinstance(value, str) and re.search(schema["pattern"], value) is None:
        errors.append(f"{location}: value does not match schema pattern")
    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        errors.append(f"{location}: value is below schema minimum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{location}.{key}: required by schema")
        for key, child_value in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                errors.extend(_schema_errors(child_value, child_schema, schema_dir, f"{location}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{location}.{key}: additional property forbidden by schema")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_schema_errors(child_value, schema["additionalProperties"], schema_dir,
                                             f"{location}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for idx, item in enumerate(value):
            errors.extend(_schema_errors(item, schema["items"], schema_dir, f"{location}[{idx}]"))
    return errors


def _get(data: Any, path: str) -> Any:
    cur = data
    for key in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _artifact_errors(data: dict[str, Any], gate: str, build: dict[str, Any] | None,
                     apk_report: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        return ["artifacts object missing"]
    required = ["performance-manager"]
    if gate != "target-core-only":
        required += ["luci-app-performance-manager", "performance-manager-rill", PRIMARY_PACKAGE]
    for name in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill"):
        rec = artifacts.get(name)
        if name not in required:
            if rec not in (None, "not-installed"):
                errors.append(f"artifacts.{name} must be null/not-installed")
            continue
        if not isinstance(rec, dict):
            errors.append(f"artifacts.{name} missing")
            continue
        if not _sha(rec.get("apkSha256")) or not isinstance(rec.get("version"), str):
            errors.append(f"artifacts.{name} lacks exact APK/version identity")
        payload = rec.get("installedPayload")
        if name == "performance-manager":
            if not isinstance(payload, dict) or not _sha(payload.get("/usr/sbin/performance-manager.uc")) \
                    or not _sha(payload.get("/usr/share/performance-manager/contracts.uc")):
                errors.append("performance-manager installed Core/contracts payload hashes missing")
        if build:
            expected = (build.get("packages") or {}).get(name) or {}
            if rec.get("apkSha256") != expected.get("apkSha256"):
                errors.append(f"artifacts.{name}.apkSha256 does not match build metadata")
            if rec.get("version") != expected.get("pkgver"):
                errors.append(f"artifacts.{name}.version does not match build metadata")
            if name == "performance-manager":
                expected_payload = expected.get("installedPayload") or {}
                for path, digest in (payload or {}).items():
                    if digest != expected_payload.get(path):
                        errors.append(f"installed payload {path} does not match build metadata")
        if apk_report:
            expected = (apk_report.get("packages") or {}).get(name) or {}
            if rec.get("apkSha256") != expected.get("sha256"):
                errors.append(f"artifacts.{name}.apkSha256 does not match APK verifier")
    if gate == "target-core-only":
        if data.get("primaryPackage") != "performance-manager":
            errors.append("target-core-only primaryPackage must be performance-manager")
    else:
        primary = artifacts.get(PRIMARY_PACKAGE)
        if data.get("primaryPackage") != PRIMARY_PACKAGE:
            errors.append(f"primaryPackage must be {PRIMARY_PACKAGE}")
        if not isinstance(primary, dict) or not _sha(primary.get("apkSha256")):
            errors.append("all-in-one primary artifact identity missing")
        elif data.get("primaryPackageSha256") != primary.get("apkSha256"):
            errors.append("primaryPackageSha256 does not match all-in-one artifact")
        if build:
            expected = (build.get("packages") or {}).get(PRIMARY_PACKAGE) or {}
            if primary.get("apkSha256") != expected.get("apkSha256") or primary.get("version") != expected.get("pkgver"):
                errors.append("all-in-one primary artifact does not match build metadata")
        if apk_report:
            expected = (apk_report.get("packages") or {}).get(PRIMARY_PACKAGE) or {}
            if primary.get("apkSha256") != expected.get("sha256"):
                errors.append("all-in-one primary artifact does not match APK verifier")
    if build and str(data.get("buildRunId")) != str(build.get("workflowRunId")):
        errors.append("buildRunId does not match build metadata")
    return errors


def validate_evidence(data: Any, gate: str, expected_commit: str, *, require_rill: bool = False,
                      minimum_duration: int = 0, build_metadata: dict[str, Any] | None = None,
                      apk_report: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if gate not in GATE_CHECKS:
        return [f"unsupported gate {gate!r}"]
    if not isinstance(data, dict):
        return ["evidence root must be an object"]
    schema_path = ROOT / "contracts/evidence" / f"{gate}.schema.json"
    if not schema_path.is_file():
        errors.append(f"schema missing for {gate}")
    else:
        errors.extend(_schema_errors(data, json.loads(schema_path.read_text()), schema_path.parent))
    if data.get("schemaVersion") != 1 or data.get("gate") != gate:
        errors.append(f"schemaVersion/gate mismatch ({data.get('schemaVersion')!r}, {data.get('gate')!r})")
    if data.get("pmCommitSha") != expected_commit:
        errors.append(f"pmCommitSha={data.get('pmCommitSha')!r}")
    if str(data.get("verdict", "")).upper() != "PASS" or data.get("passed") is not True:
        errors.append(f"verdict={data.get('verdict')!r} passed={data.get('passed')!r}")
    if not str(data.get("buildRunId") or ""):
        errors.append("buildRunId missing")
    controller = data.get("controller") or {}
    if controller.get("source") != "repository" or not str(controller.get("path") or "").startswith("tools/stable-testbed/") \
            or not _sha(controller.get("sha256")):
        errors.append("controller must be repository-sourced with exact SHA-256")
    checks = data.get("subchecks")
    if not isinstance(checks, dict):
        errors.append("subchecks object missing")
    else:
        for name in GATE_CHECKS[gate]:
            if checks.get(name) is not True:
                errors.append(f"subcheck {name} did not pass")
    if (require_rill or gate in RILL_GATES) and data.get("adapterSha256") != PIN:
        errors.append(f"adapterSha256={data.get('adapterSha256')!r}")
    try:
        if int(data.get("durationSeconds", 0)) < minimum_duration:
            errors.append(f"durationSeconds={data.get('durationSeconds')!r}")
    except (TypeError, ValueError):
        errors.append("durationSeconds invalid")
    errors.extend(_artifact_errors(data, gate, build_metadata, apk_report))

    if gate == "hyperv":
        if _get(data, "environment.hypervisor") != "Hyper-V" or _get(data, "environment.nicDriver") != "hv_netvsc" \
                or not str(_get(data, "environment.vmbusId") or ""):
            errors.append("Hyper-V semantic identity invalid")
    elif gate == "kvm":
        if _get(data, "environment.hypervisor") not in {"KVM", "QEMU"} \
                or not _get(data, "environment.nicDriver") or not _get(data, "environment.pciId"):
            errors.append("KVM/QEMU semantic identity invalid")
    elif gate in {"lan-wan-ab", "router-local-ab"}:
        bench = data.get("benchmark") or {}
        if bench.get("controlMethodologyFingerprint") != bench.get("candidateMethodologyFingerprint"):
            errors.append("A/B methodology fingerprints differ")
        if bench.get("variableCount") != 1 or bench.get("validated") is not True \
                or not isinstance(bench.get("reward"), (int, float)):
            errors.append("A/B validation/reward/one-variable contract invalid")
        if gate == "lan-wan-ab" and (bench.get("routeResolved") is not True or bench.get("routeProvider") != "ip-full+rtnl-events"):
            errors.append("LAN-WAN route evidence invalid")
        if bench.get("rillOutcome") not in {"accepted", "reconciled"}:
            errors.append("Rill Outcome is not final")
    elif gate == "sysupgrade":
        upgrade = data.get("upgrade") or {}
        if not upgrade.get("beforeBootId") or upgrade.get("beforeBootId") == upgrade.get("afterBootId"):
            errors.append("sysupgrade boot identity did not change")
        if upgrade.get("beforeVersion") == upgrade.get("afterVersion"):
            errors.append("sysupgrade package identity did not change")
    elif gate == "resource-soak":
        soak = data.get("soak") or {}
        if int(data.get("durationSeconds", 0)) < 86400 or int(soak.get("sampleCount", 0)) <= 0:
            errors.append("24h soak duration/sample evidence invalid")
        for key in ("idleRillObserveAcceptedDelta", "idleExpectedAdapterPersistenceEventsDelta", "idlePendingOutcomeJournalWrites"):
            if soak.get(key) != 0:
                errors.append(f"soak {key} must be zero")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--require-rill", action="store_true")
    parser.add_argument("--minimum-duration", type=int, default=0)
    parser.add_argument("--build-metadata")
    parser.add_argument("--apk-verification")
    args = parser.parse_args(argv)
    data = json.loads(Path(args.file).read_text())
    build = json.loads(Path(args.build_metadata).read_text()) if args.build_metadata else None
    apk = json.loads(Path(args.apk_verification).read_text()) if args.apk_verification else None
    errors = validate_evidence(data, args.gate, args.expected_commit, require_rill=args.require_rill,
                               minimum_duration=args.minimum_duration, build_metadata=build, apk_report=apk)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: {args.gate} commit={args.expected_commit} adapter={data.get('adapterSha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
