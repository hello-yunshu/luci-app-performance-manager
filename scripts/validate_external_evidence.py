#!/usr/bin/env python3
"""Gate-specific, fail-closed validator for Stable testbed evidence."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "contracts/rill-dependency.json").read_text())["upstream"]["adapter"]["sha256"]
SHA256 = re.compile(r"[0-9a-f]{64}")

GATE_CHECKS = {
    "target-core-only": ["openwrt2512", "x8664", "coreStarted", "ubusReady", "statusValid",
                         "analyzeValid", "topologyValid", "capabilitiesValid", "noStaleLocks",
                         "exactPackagesInstalled"],
    "target-full": ["exactPackagesInstalled", "serviceUserRestricted", "stateDirectoryRestricted",
                    "coreConnectedExactAdapter", "rillStatusReady", "advisoryOnlyAuthority"],
    "target-mutation": ["exactPackagesInstalled", "legalCandidate", "beforeSnapshotExact", "applyExecuted", "readbackExact",
                        "manualRollback", "restorationExact", "secondApply", "cleanupComplete",
                        "ownershipClean", "packetSteeringNotSeized", "noStaleState"],
    "hyperv": ["exactPackagesInstalled", "hypervisorVerified", "vmbusIdentity", "hvNetvscDriver", "hotplugObserved",
               "targetRefStable", "replayTested", "rollbackExact"],
    "kvm": ["exactPackagesInstalled", "hypervisorVerified", "pciIdentity", "nicDriverRecorded", "hotplugObserved",
            "targetRefStable", "replayTested", "rollbackExact"],
    "lan-wan-ab": ["exactPackagesInstalled", "realLanClient", "realWanEndpoint", "routeResolved", "rtnlRouteProvider",
                   "sameMethodology", "oneVariable", "mutationVerified", "rollbackExact",
                   "healthPass", "validatedReward", "rillOutcomeFinal"],
    "router-local-ab": ["exactPackagesInstalled", "routerLocalClient", "localEndpointPath", "sameMethodology", "oneVariable",
                        "mutationVerified", "rollbackExact", "validatedReward", "rillOutcomeFinal"],
    "sysupgrade": ["exactPackagesInstalled", "preIdentityRecorded", "postIdentityRecorded", "bootIdChanged", "configPreserved",
                   "policyPreserved", "exactAdapterAfterUpgrade", "noUnsafePendingMutation", "coreStartedClean"],
    "lifecycle": ["install", "serviceStart", "restart", "upgradeReinstall", "configPreserved",
                  "rillOptional", "uninstallCleanup", "reinstall", "noStaleState"],
    "resource-soak": ["exactPackagesInstalled", "rillPresent", "sampledResources", "noCoreRestart", "noRillRestart",
                      "idleObserveZero", "idleAdapterPersistenceZero", "idleJournalWritesZero",
                      "stateBoundsPass", "historyBoundsPass"],
}
RILL_GATES = set(GATE_CHECKS) - {"target-core-only"}
PRIMARY_PACKAGE = "luci-app-performance-manager-all"
PACKAGE_NAMES = ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", PRIMARY_PACKAGE)
CORE_PAYLOAD = ("/usr/sbin/performance-manager.uc", "/usr/share/performance-manager/contracts.uc")
ALL_IN_ONE_PAYLOAD = CORE_PAYLOAD + (
    "/etc/init.d/performance-manager", "/etc/init.d/performance-manager-rill",
    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
    "/usr/share/luci/menu.d/luci-app-performance-manager.json",
    "/www/luci-static/resources/view/performance-manager/overview.js",
    "/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=True) == \
        json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _exit_ok(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _methodology_equal(benchmark: dict[str, Any]) -> bool:
    control = _dict(benchmark.get("control")).get("methodology")
    candidate = _dict(benchmark.get("candidate")).get("methodology")
    return isinstance(control, dict) and isinstance(candidate, dict) and _same(control, candidate)


def _outcome_final(benchmark: dict[str, Any]) -> bool:
    response = _dict(_dict(benchmark.get("rill")).get("outcome")).get("response")
    response = _dict(response)
    if response.get("ok") is True and response.get("accepted") is True:
        return True
    error = _dict(response.get("error"))
    return error.get("code") == "duplicateFeedback" and error.get("sameFingerprint") is True


def _ab_checks(facts: dict[str, Any], local: bool) -> dict[str, bool]:
    benchmark = _dict(facts.get("benchmark"))
    control = _dict(benchmark.get("control"))
    candidate = _dict(benchmark.get("candidate"))
    mutation = _dict(benchmark.get("mutation"))
    health = _dict(benchmark.get("health"))
    reward = benchmark.get("reward")
    try:
        expected_reward = (float(candidate["bitsPerSecond"]) - float(control["bitsPerSecond"])) / float(control["bitsPerSecond"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        expected_reward = math.nan
    route = _dict(benchmark.get("route"))
    checks = {
        "sameMethodology": _methodology_equal(benchmark),
        "oneVariable": len(mutation.get("changedFields", [])) == 1,
        "mutationVerified": _exit_ok(mutation.get("applyExitCode")) and _same(mutation.get("readback"), mutation.get("candidate")),
        "rollbackExact": _same(mutation.get("before"), mutation.get("afterRollback")),
        "healthPass": health.get("before") is not None and health.get("after") is not None and health.get("regressions") == [],
        "validatedReward": benchmark.get("validated") is True and isinstance(reward, (int, float)) and not isinstance(reward, bool) and math.isfinite(float(reward)) and math.isfinite(expected_reward) and math.isclose(float(reward), expected_reward, rel_tol=1e-9, abs_tol=1e-12),
        "rillOutcomeFinal": _outcome_final(benchmark),
    }
    if local:
        checks.update({
            "routerLocalClient": _dict(benchmark.get("client")).get("role") == "router-local-client",
            "localEndpointPath": _dict(benchmark.get("endpoint")).get("kind") == "router-local",
        })
    else:
        checks.update({
            "realLanClient": _dict(benchmark.get("client")).get("role") == "lan-client",
            "realWanEndpoint": _dict(benchmark.get("endpoint")).get("kind") == "wan",
            "routeResolved": route.get("resolved") is True,
            "rtnlRouteProvider": route.get("provider") == "ip-full+rtnl-events",
        })
    return checks


def _package_layout_ok(packages: dict[str, Any], gate: str) -> bool:
    """Verify installed identity; build inventory is checked separately."""
    present = {name for name, value in packages.items() if isinstance(value, dict)}
    if gate == "target-core-only":
        return present == {"performance-manager"}
    if gate == "lifecycle":
        return True
    return present == {PRIMARY_PACKAGE}


def evaluate_raw_facts(raw: dict[str, Any], gate: str) -> dict[str, bool]:
    """Derive every Stable subcheck from raw observations.

    The transport is deliberately unable to submit verdict-shaped fields.
    These evaluators consume measurements, command results, identities and
    before/after records only; a forged ``subchecks`` map is never consulted.
    """
    names = GATE_CHECKS[gate]
    facts = _dict(raw.get("rawFacts"))
    environment = _dict(facts.get("environment"))
    packages = _dict(facts.get("installedPackages"))
    checks: dict[str, bool] = {}
    package_layout = _package_layout_ok(packages, gate)
    if gate == "target-core-only":
        checks = {
            "openwrt2512": environment.get("release") == "25.12.5",
            "x8664": environment.get("target") == "x86/64",
            "coreStarted": _dict(facts.get("process")).get("corePid", 0) > 0,
            "ubusReady": facts.get("ubusSocketReady") is True,
            "statusValid": facts.get("statusResponseValid") is True,
            "analyzeValid": facts.get("analyzeResponseValid") is True,
            "topologyValid": facts.get("topologyEvidenceValid") is True,
            "capabilitiesValid": facts.get("capabilitiesEvidenceValid") is True,
            "noStaleLocks": facts.get("staleLocks") == 0,
            "exactPackagesInstalled": package_layout,
        }
    elif gate == "target-full":
        permissions = _dict(facts.get("permissions"))
        rill = _dict(facts.get("rill"))
        checks = {
            "exactPackagesInstalled": package_layout,
            "serviceUserRestricted": permissions.get("serviceUid") == 5666 and permissions.get("serviceUserDedicated") is True,
            "stateDirectoryRestricted": permissions.get("stateDirectoryMode") == "0750" and permissions.get("stateDirectoryOwner") == "performance-manager-rill:performance-manager-rill",
            "coreConnectedExactAdapter": rill.get("adapterSha256") == PIN and rill.get("connectedToCore") is True,
            "rillStatusReady": _dict(rill.get("statusResponse")).get("ready") is True,
            "advisoryOnlyAuthority": facts.get("rillDirectMutationCount") == 0 and facts.get("mutationAuthority") == "pm-core",
        }
    elif gate == "target-mutation":
        mutation = _dict(facts.get("mutation"))
        candidate = _dict(mutation.get("candidate"))
        checks = {
            "exactPackagesInstalled": package_layout,
            "legalCandidate": bool(candidate.get("actionId")) and candidate.get("authority") == "advisory-only" and candidate.get("mutationOwner") == "pm-core",
            "beforeSnapshotExact": isinstance(mutation.get("before"), dict),
            "applyExecuted": _exit_ok(mutation.get("applyExitCode")),
            "readbackExact": _same(mutation.get("readback"), mutation.get("candidateState")),
            "manualRollback": _exit_ok(mutation.get("rollbackExitCode")),
            "restorationExact": _same(mutation.get("before"), mutation.get("afterRollback")),
            "secondApply": _exit_ok(mutation.get("secondApplyExitCode")),
            "cleanupComplete": mutation.get("staleLocks") == 0 and mutation.get("stalePolicies") == 0,
            "ownershipClean": mutation.get("ownershipAfter") == "clean",
            "packetSteeringNotSeized": mutation.get("packetSteeringOwner") != "performance-manager",
            "noStaleState": mutation.get("staleRuntimeState") == 0,
        }
    elif gate == "hyperv":
        hotplug = _dict(facts.get("hotplug")); rollback = _dict(facts.get("rollback"))
        checks = {"exactPackagesInstalled": package_layout, "hypervisorVerified": environment.get("hypervisor") == "Hyper-V", "vmbusIdentity": bool(environment.get("vmbusId")), "hvNetvscDriver": environment.get("nicDriver") == "hv_netvsc", "hotplugObserved": hotplug.get("before") != hotplug.get("after"), "targetRefStable": facts.get("targetRefStableId") is True, "replayTested": facts.get("replayCount", 0) > 0, "rollbackExact": _same(rollback.get("before"), rollback.get("after"))}
    elif gate == "kvm":
        hotplug = _dict(facts.get("hotplug")); rollback = _dict(facts.get("rollback"))
        checks = {"exactPackagesInstalled": package_layout, "hypervisorVerified": environment.get("hypervisor") in {"KVM", "QEMU"}, "pciIdentity": bool(environment.get("pciId")), "nicDriverRecorded": bool(environment.get("nicDriver")), "hotplugObserved": hotplug.get("before") != hotplug.get("after"), "targetRefStable": facts.get("targetRefStableId") is True, "replayTested": facts.get("replayCount", 0) > 0, "rollbackExact": _same(rollback.get("before"), rollback.get("after"))}
    elif gate == "lan-wan-ab":
        checks = {"exactPackagesInstalled": package_layout, **_ab_checks(facts, local=False)}
    elif gate == "router-local-ab":
        checks = {"exactPackagesInstalled": package_layout, **_ab_checks(facts, local=True)}
    elif gate == "sysupgrade":
        upgrade = _dict(facts.get("upgrade")); before = _dict(upgrade.get("before")); after = _dict(upgrade.get("after"))
        checks = {
            "exactPackagesInstalled": package_layout,
            "preIdentityRecorded": bool(before.get("bootId")) and bool(before.get("packageSha256")),
            "postIdentityRecorded": bool(after.get("bootId")) and bool(after.get("packageSha256")),
            "bootIdChanged": before.get("bootId") != after.get("bootId"),
            "configPreserved": before.get("configSha256") == after.get("configSha256"),
            "policyPreserved": before.get("policySha256") == after.get("policySha256"),
            "exactAdapterAfterUpgrade": after.get("adapterSha256") == PIN,
            "noUnsafePendingMutation": after.get("pendingMutationCount") == 0,
            "coreStartedClean": after.get("coreStarted") is True and after.get("staleLocks") == 0,
        }
    elif gate == "lifecycle":
        lifecycle = _dict(facts.get("lifecycle")); steps = _dict(lifecycle.get("steps"))
        def step_ok(name: str) -> bool:
            item = _dict(steps.get(name))
            return _exit_ok(item.get("exitCode")) and item.get("observed") is True
        checks = {name: step_ok(name) for name in ("install", "serviceStart", "restart", "upgradeReinstall", "configPreserved", "rillOptional", "uninstallCleanup", "reinstall", "noStaleState")}
    elif gate == "resource-soak":
        soak = _dict(facts.get("soak")); resources = _dict(soak.get("resources"))
        checks = {
            "exactPackagesInstalled": package_layout,
            "rillPresent": soak.get("rillPresent") is True,
            "sampledResources": soak.get("sampleCount", 0) > 0 and isinstance(resources, dict),
            "noCoreRestart": soak.get("coreRestartCount") == 0,
            "noRillRestart": soak.get("rillRestartCount") == 0,
            "idleObserveZero": soak.get("idleRillObserveAcceptedDelta") == 0,
            "idleAdapterPersistenceZero": soak.get("idleExpectedAdapterPersistenceEventsDelta") == 0,
            "idleJournalWritesZero": soak.get("idlePendingOutcomeJournalWrites") == 0 and soak.get("executingJournalDelta") == 0,
            "stateBoundsPass": resources.get("coreRssKiB", 0) <= 65536 and resources.get("rillRssKiB", 0) <= 98304 and resources.get("bindingHighWater", 0) <= 64 and resources.get("interventionRequiredCount", 0) == 0,
            "historyBoundsPass": resources.get("persistentHistoryGrowthBytes", 0) <= 262144,
        }
    return {name: checks.get(name, False) for name in names}


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
    build_artifacts = data.get("buildArtifacts")
    installed_artifacts = data.get("installedArtifacts")
    if not isinstance(build_artifacts, dict):
        errors.append("buildArtifacts object missing")
    if not isinstance(installed_artifacts, dict):
        errors.append("installedArtifacts object missing")
    if errors:
        return errors
    for name in PACKAGE_NAMES:
        record = build_artifacts.get(name)
        if not isinstance(record, dict) or not _sha(record.get("apkSha256")) \
                or not isinstance(record.get("version"), str) or not isinstance(record.get("filename"), str):
            errors.append(f"buildArtifacts.{name} lacks exact APK/version/filename identity")
    for name in PACKAGE_NAMES:
        rec = installed_artifacts.get(name)
        if not isinstance(rec, dict):
            if gate == "target-core-only" and name != "performance-manager":
                if rec not in (None, "not-installed"):
                    errors.append(f"installedArtifacts.{name} must be absent")
            elif gate != "lifecycle" and name != PRIMARY_PACKAGE:
                if rec not in (None, "not-installed"):
                    errors.append(f"installedArtifacts.{name} must be absent")
            elif gate != "lifecycle":
                errors.append(f"installedArtifacts.{name} missing")
            continue
        if not _sha(rec.get("apkSha256")) or not isinstance(rec.get("version"), str):
            errors.append(f"installedArtifacts.{name} lacks exact APK/version identity")
        payload = rec.get("installedPayload")
        required_payload = ALL_IN_ONE_PAYLOAD if name == PRIMARY_PACKAGE else CORE_PAYLOAD if name == "performance-manager" else ()
        if required_payload:
            if not isinstance(payload, dict) or any(not _sha(payload.get(path)) for path in required_payload):
                errors.append(f"{name} installed Core/contracts payload hashes missing")
        if build:
            expected = (build.get("packages") or {}).get(name) or {}
            expected_record = build_artifacts.get(name) or {}
            if expected_record.get("apkSha256") != expected.get("apkSha256"):
                errors.append(f"buildArtifacts.{name}.apkSha256 does not match build metadata")
            if rec.get("apkSha256") != expected.get("apkSha256"):
                errors.append(f"installedArtifacts.{name}.apkSha256 does not match build metadata")
            if rec.get("version") != expected.get("pkgver"):
                errors.append(f"installedArtifacts.{name}.version does not match build metadata")
            expected_payload = expected.get("installedPayload") or {}
            for path, digest in (payload or {}).items():
                if digest != expected_payload.get(path):
                    errors.append(f"installed payload {path} does not match build metadata")
        if apk_report:
            expected = (apk_report.get("packages") or {}).get(name) or {}
            if rec.get("apkSha256") != expected.get("sha256"):
                errors.append(f"installedArtifacts.{name}.apkSha256 does not match APK verifier")
    if gate == "target-core-only":
        if data.get("primaryPackage") != "performance-manager":
            errors.append("target-core-only primaryPackage must be performance-manager")
        primary = installed_artifacts.get("performance-manager")
        if not isinstance(primary, dict) or data.get("primaryPackageSha256") != primary.get("apkSha256"):
            errors.append("target-core-only primary artifact identity missing or mismatched")
    else:
        primary = installed_artifacts.get(PRIMARY_PACKAGE)
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
        raw_facts = data.get("rawFacts")
        if not isinstance(raw_facts, dict):
            errors.append("rawFacts object missing; verdicts must be derived from transport observations")
        else:
            derived = evaluate_raw_facts(data, gate)
            for name in GATE_CHECKS[gate]:
                if checks.get(name) is not derived.get(name):
                    errors.append(f"subcheck {name} does not match repository evaluator")
    if (require_rill or gate in RILL_GATES) and data.get("adapterSha256") != PIN:
        errors.append(f"adapterSha256={data.get('adapterSha256')!r}")
    try:
        if int(data.get("durationSeconds", 0)) < minimum_duration:
            errors.append(f"durationSeconds={data.get('durationSeconds')!r}")
    except (TypeError, ValueError):
        errors.append("durationSeconds invalid")
    errors.extend(_artifact_errors(data, gate, build_metadata, apk_report))

    if gate == "hyperv":
        environment = _dict(_dict(data.get("rawFacts")).get("environment"))
        if environment.get("hypervisor") != "Hyper-V" or environment.get("nicDriver") != "hv_netvsc" \
                or not str(environment.get("vmbusId") or ""):
            errors.append("Hyper-V semantic identity invalid")
    elif gate == "kvm":
        environment = _dict(_dict(data.get("rawFacts")).get("environment"))
        if environment.get("hypervisor") not in {"KVM", "QEMU"} \
                or not environment.get("nicDriver") or not environment.get("pciId"):
            errors.append("KVM/QEMU semantic identity invalid")
    elif gate in {"lan-wan-ab", "router-local-ab"}:
        derived = evaluate_raw_facts(data, gate)
        if not all(derived.get(name) is True for name in GATE_CHECKS[gate]):
            errors.append("A/B canonical rawFacts evaluation failed")
    elif gate == "sysupgrade":
        upgrade = _dict(_dict(data.get("rawFacts")).get("upgrade"))
        before = _dict(upgrade.get("before")); after = _dict(upgrade.get("after"))
        if not before.get("bootId") or before.get("bootId") == after.get("bootId"):
            errors.append("sysupgrade boot identity did not change")
        if before.get("packageSha256") == after.get("packageSha256"):
            errors.append("sysupgrade package identity did not change")
    elif gate == "resource-soak":
        soak = _dict(_dict(data.get("rawFacts")).get("soak"))
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
