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
SHA256 = re.compile(r"[0-9a-f]{64}")

GATE_CHECKS = {
    "target-core-only": ["openwrt2512", "x8664", "coreStarted", "ubusReady", "statusValid",
                         "analyzeValid", "topologyValid", "capabilitiesValid", "noStaleLocks",
                         "exactPackagesInstalled"],
    "target-full": ["exactPackagesInstalled", "serviceUserRestricted", "stateDirectoryRestricted",
                    "coreConnectedExactRuntime", "rillStatusReady", "advisoryOnlyAuthority"],
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
                   "policyPreserved", "firmwareUpgradeProven", "exactRuntimeAfterUpgrade", "noUnsafePendingMutation", "coreStartedClean"],
    "lifecycle": ["install", "serviceStart", "restart", "upgradeReinstall", "configPreserved",
                  "rillOptional", "uninstallCleanup", "reinstall", "noStaleState"],
    "resource-soak": ["exactPackagesInstalled", "rillPresent", "sampledResources", "noCoreRestart",
                      "idleObserveZero", "idleRuntimePersistenceZero", "idleJournalWritesZero",
                      "runtimeInvocationHealthy", "runtimeFailureZero", "runtimeStateBounded",
                      "journalMeasured", "stateBoundsPass", "historyBoundsPass"],
}
RILL_GATES = set(GATE_CHECKS) - {"target-core-only"}
PRIMARY_PACKAGE = "luci-app-performance-manager-all"
RUNTIME_PACKAGE = "rill-runtime"
PACKAGE_NAMES = ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", RUNTIME_PACKAGE, PRIMARY_PACKAGE)
CORE_PAYLOAD = ("/usr/sbin/performance-manager.uc", "/usr/share/performance-manager/contracts.uc")
ALL_IN_ONE_PAYLOAD = CORE_PAYLOAD + (
    "/etc/init.d/performance-manager",
    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
    "/usr/share/luci/menu.d/luci-app-performance-manager.json",
    "/www/luci-static/resources/view/performance-manager/overview.js",
    "/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo",
)

RESOURCE_METRICS = (
    "coreRssKiB", "coreMeanCpuPercent", "corePersistentWritesPerDay", "bindingHighWater", "interventionRequiredCount",
    "persistentHistoryGrowthBytes", "executionJournalFileCount", "executionJournalBytes",
    "retiredExecutionCount", "activeExecutionCount", "executingExecutionCount", "runtimeStateMaxBytes",
)


def _finite_nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value)) and float(value) >= 0


def _nonempty_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
    required = ("tool", "protocol", "durationSeconds", "direction", "clientIdentity",
                "endpointIdentity", "streamCount", "payloadMode")
    return isinstance(control, dict) and isinstance(candidate, dict) \
        and all(_nonempty_string(control.get(key)) or _finite_nonnegative_number(control.get(key)) for key in required) \
        and all(_nonempty_string(candidate.get(key)) or _finite_nonnegative_number(candidate.get(key)) for key in required) \
        and _same(control, candidate)


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
    changed_fields = mutation.get("changedFields")
    before = mutation.get("before")
    candidate_state = mutation.get("candidate")
    readback = mutation.get("readback")
    rollback = mutation.get("afterRollback")
    action = _dict(mutation.get("action"))
    checks = {
        "sameMethodology": _methodology_equal(benchmark),
        "oneVariable": isinstance(changed_fields, list) and len(changed_fields) == 1 and _nonempty_string(changed_fields[0]),
        "mutationVerified": _exit_ok(mutation.get("applyExitCode")) and _nonempty_dict(action)
            and action.get("actionId") == "nic.ring.floor" and action.get("authority") == "advisory-only"
            and action.get("mutationOwner") == "pm-core" and _nonempty_dict(before)
            and _nonempty_dict(candidate_state) and _nonempty_dict(readback) and _same(readback, candidate_state),
        "rollbackExact": _nonempty_dict(before) and _nonempty_dict(rollback) and _same(before, rollback),
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
    return present == {PRIMARY_PACKAGE, RUNTIME_PACKAGE}


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
            "coreConnectedExactRuntime": _sha(rill.get("runtimeSha256")) and rill.get("connectedToCore") is True,
            "rillStatusReady": _dict(rill.get("statusResponse")).get("ready") is True,
            "advisoryOnlyAuthority": facts.get("rillDirectMutationCount") == 0 and facts.get("mutationAuthority") == "pm-core",
        }
    elif gate == "target-mutation":
        mutation = _dict(facts.get("mutation"))
        candidate = _dict(mutation.get("candidate"))
        action_id = candidate.get("actionId")
        action_contracts = {
            "nic.ring.floor": {"authority": "advisory-only", "mutationOwner": "pm-core",
                                "required": ("targetStableId", "rx", "tx")},
        }
        contract = action_contracts.get(action_id)
        before = mutation.get("before")
        candidate_state = mutation.get("candidateState")
        readback = mutation.get("readback")
        after_rollback = mutation.get("afterRollback")
        checks = {
            "exactPackagesInstalled": package_layout,
            "legalCandidate": contract is not None and candidate.get("authority") == contract["authority"]
                and candidate.get("mutationOwner") == contract["mutationOwner"]
                and _nonempty_string(candidate.get("targetStableId"))
                and all(_finite_nonnegative_number(candidate.get(key)) for key in ("rx", "tx")),
            "beforeSnapshotExact": _nonempty_dict(before) and all(_finite_nonnegative_number(before.get(key)) for key in ("rx", "tx")),
            "applyExecuted": _exit_ok(mutation.get("applyExitCode")),
            "readbackExact": _nonempty_dict(readback) and _nonempty_dict(candidate_state) and _same(readback, candidate_state),
            "manualRollback": _exit_ok(mutation.get("rollbackExitCode")),
            "restorationExact": _nonempty_dict(after_rollback) and _same(before, after_rollback),
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
        firmware_before = _dict(before.get("firmware")); firmware_after = _dict(after.get("firmware"))
        firmware_changed = _nonempty_string(firmware_before.get("identity")) and _nonempty_string(firmware_after.get("identity")) \
            and firmware_before.get("identity") != firmware_after.get("identity")
        checks = {
            "exactPackagesInstalled": package_layout,
            "preIdentityRecorded": _nonempty_string(before.get("bootId")) and _sha(before.get("packageSha256"))
                and _sha(before.get("configSha256")) and _sha(before.get("policySha256")) and _nonempty_dict(firmware_before),
            "postIdentityRecorded": _nonempty_string(after.get("bootId")) and _sha(after.get("packageSha256"))
                and _sha(after.get("configSha256")) and _sha(after.get("policySha256")) and _nonempty_dict(firmware_after),
            "bootIdChanged": _nonempty_string(before.get("bootId")) and _nonempty_string(after.get("bootId"))
                and before.get("bootId") != after.get("bootId"),
            "configPreserved": _sha(before.get("configSha256")) and _sha(after.get("configSha256"))
                and before.get("configSha256") == after.get("configSha256"),
            "policyPreserved": _sha(before.get("policySha256")) and _sha(after.get("policySha256"))
                and before.get("policySha256") == after.get("policySha256"),
            "exactRuntimeAfterUpgrade": _sha(after.get("runtimeSha256")),
            "firmwareUpgradeProven": firmware_changed or (_nonempty_string(upgrade.get("transactionMarker"))
                and _sha(upgrade.get("intendedImageSha256")) and firmware_after.get("imageSha256") == upgrade.get("intendedImageSha256")),
            "noUnsafePendingMutation": after.get("pendingMutationCount") == 0,
            "coreStartedClean": after.get("coreStarted") is True and after.get("staleLocks") == 0,
        }
    elif gate == "lifecycle":
        lifecycle = _dict(facts.get("lifecycle")); phases = lifecycle.get("phases")
        phase_map = {p.get("name"): p for p in phases if isinstance(p, dict) and _nonempty_string(p.get("name"))} if isinstance(phases, list) else {}
        split = _dict(phase_map.get("split-install")); split_runtime = _dict(phase_map.get("split-runtime"))
        migration = _dict(phase_map.get("migration")); bundle_runtime = _dict(phase_map.get("bundle-runtime"))
        uninstall = _dict(phase_map.get("uninstall")); reinstall = _dict(phase_map.get("reinstall"))
        split_pkgs = _dict(split.get("installedPackages")); bundle_pkgs = _dict(migration.get("installedPackages"))
        split_names = {name for name, value in split_pkgs.items() if isinstance(value, dict)}
        bundle_names = {name for name, value in bundle_pkgs.items() if isinstance(value, dict)}
        checks = {
            "install": _exit_ok(split.get("exitCode")) and split_names == {"performance-manager", "luci-app-performance-manager", "performance-manager-rill", RUNTIME_PACKAGE},
            "serviceStart": _nonempty_string(split_runtime.get("corePid")) or (isinstance(split_runtime.get("corePid"), int) and split_runtime.get("corePid") > 0),
            "restart": _nonempty_string(bundle_runtime.get("corePid")) or (isinstance(bundle_runtime.get("corePid"), int) and bundle_runtime.get("corePid") > 0),
            "upgradeReinstall": _exit_ok(migration.get("removeExitCode")) and _exit_ok(migration.get("installBundleExitCode"))
                and bundle_names == {PRIMARY_PACKAGE, RUNTIME_PACKAGE},
            "configPreserved": _sha(split.get("configSha256")) and _sha(bundle_runtime.get("configSha256"))
                and split.get("configSha256") == bundle_runtime.get("configSha256"),
            "rillOptional": split_runtime.get("ubusReady") is True and bundle_runtime.get("ubusReady") is True,
            "uninstallCleanup": _exit_ok(uninstall.get("exitCode")) and uninstall.get("remainingOwnedPaths") == [],
            "reinstall": _exit_ok(reinstall.get("exitCode")) and _dict(reinstall.get("installedPackages")).keys() == {PRIMARY_PACKAGE, RUNTIME_PACKAGE}
                and reinstall.get("ubusReady") is True,
            "noStaleState": uninstall.get("staleLocks") == 0 and uninstall.get("stalePending") == 0
                and uninstall.get("staleSockets") == 0,
        }
    elif gate == "resource-soak":
        soak = _dict(facts.get("soak")); resources = _dict(soak.get("resources"))
        metrics_valid = all(key in resources and _finite_nonnegative_number(resources.get(key)) for key in RESOURCE_METRICS)
        checks = {
            "exactPackagesInstalled": package_layout,
            "rillPresent": soak.get("rillPresent") is True,
            "sampledResources": soak.get("sampleCount", 0) > 0 and metrics_valid,
            "noCoreRestart": soak.get("coreRestartCount") == 0,
            "idleObserveZero": soak.get("idleRillObserveAcceptedDelta") == 0,
            "idleRuntimePersistenceZero": soak.get("idleExpectedRuntimePersistenceEventsDelta") == 0,
            "idleJournalWritesZero": soak.get("idlePendingOutcomeJournalWrites") == 0 and soak.get("executingJournalDelta") == 0,
            "runtimeInvocationHealthy": soak.get("runtimeInvocationCount", 0) > 0
                and soak.get("runtimeSuccessfulInvocationCount", 0) > 0
                and soak.get("runtimeSuccessfulInvocationCount", 0) <= soak.get("runtimeInvocationCount", -1),
            "runtimeFailureZero": soak.get("runtimeInvocationFailureCount") == 0
                and soak.get("runtimeTimeoutCount") == 0
                and soak.get("runtimeMalformedResponseCount") == 0
                and soak.get("runtimeNonZeroExitCount") == 0,
            "runtimeStateBounded": metrics_valid and resources["runtimeStateMaxBytes"] <= 4194304,
            "journalMeasured": metrics_valid and resources["executionJournalFileCount"] <= 128
                and resources["executionJournalBytes"] <= 2097152 and resources["retiredExecutionCount"] <= 64,
            "stateBoundsPass": metrics_valid and resources["coreRssKiB"] <= 65536
                and resources["coreMeanCpuPercent"] <= 5.0
                and resources["corePersistentWritesPerDay"] <= 32
                and resources["bindingHighWater"] <= 64 and resources["interventionRequiredCount"] == 0
                and resources["activeExecutionCount"] >= resources["executingExecutionCount"],
            "historyBoundsPass": metrics_valid and resources["persistentHistoryGrowthBytes"] <= 262144,
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
                 "required", "properties", "items", "const", "enum", "pattern", "minimum",
                 "minLength", "minItems"}
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
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        errors.append(f"{location}: string is shorter than minimum length")
    if "minItems" in schema and isinstance(value, list) and len(value) < schema["minItems"]:
        errors.append(f"{location}: array has fewer than minimum items")
    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        errors.append(f"{location}: value is below schema minimum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        allowed_from_allof = set()
        if schema.get("allOf") or location.startswith("evidence.allOf["):
            # Gate schemas refine common.schema.json through allOf.  The
            # JSON-Schema additionalProperties rule is evaluated per schema;
            # include the common envelope here so a refinement does not
            # incorrectly reject the fields declared by its base schema.
            allowed_from_allof.update({
                "schemaVersion", "gate", "pmCommitSha", "buildRunId", "verdict", "passed",
                "controller", "buildArtifacts", "installedArtifacts", "subchecks", "rawFacts",
                "primaryPackage", "primaryPackageSha256", "runtimeSha256", "durationSeconds",
                "validationErrors",
            })
        allowed_from_allof.update(schema.get("required", []))
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{location}.{key}: required by schema")
        for key, child_value in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                errors.extend(_schema_errors(child_value, child_schema, schema_dir, f"{location}.{key}"))
            elif schema.get("additionalProperties") is False and key not in allowed_from_allof:
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
            elif gate != "lifecycle" and name not in {PRIMARY_PACKAGE, RUNTIME_PACKAGE}:
                if rec not in (None, "not-installed"):
                    errors.append(f"installedArtifacts.{name} must be absent")
            elif gate != "lifecycle" and name == RUNTIME_PACKAGE:
                errors.append(f"installedArtifacts.{name} missing")
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
    expected_schema_version = 2 if gate == "resource-soak" else 1
    if data.get("schemaVersion") != expected_schema_version or data.get("gate") != gate:
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
    if (require_rill or gate in RILL_GATES) and not _sha(data.get("runtimeSha256")):
        errors.append(f"runtimeSha256={data.get('runtimeSha256')!r}")
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
        if not _sha(after.get("packageSha256")):
            errors.append("sysupgrade after PM package identity is missing or invalid")
        elif build_metadata:
            expected = _dict(build_metadata.get("packages")).get(PRIMARY_PACKAGE, {}).get("apkSha256")
            if after.get("packageSha256") != expected:
                errors.append("sysupgrade after PM package identity does not match final all-in-one artifact")
        if not evaluate_raw_facts(data, gate).get("firmwareUpgradeProven"):
            errors.append("sysupgrade firmware identity/transaction proof missing")
    elif gate == "resource-soak":
        soak = _dict(_dict(data.get("rawFacts")).get("soak"))
        if int(data.get("durationSeconds", 0)) < 86400 or int(soak.get("sampleCount", 0)) <= 0:
            errors.append("24h soak duration/sample evidence invalid")
        for key in ("idleRillObserveAcceptedDelta", "idleExpectedRuntimePersistenceEventsDelta", "idlePendingOutcomeJournalWrites"):
            if soak.get(key) != 0:
                errors.append(f"soak {key} must be zero")
        for key in ("runtimeInvocationFailureCount", "runtimeTimeoutCount", "runtimeMalformedResponseCount", "runtimeNonZeroExitCount"):
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
    print(f"PASS: {args.gate} commit={args.expected_commit} runtime={data.get('runtimeSha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
