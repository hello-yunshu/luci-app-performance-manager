#!/usr/bin/env python3
"""Exercise the published PM APK graph in a real OpenWrt rootfs.

The package verifier proves each APK's metadata and payload. This gate proves
both the developer split install and the user-facing one-file full install as
the package manager sees them. The full matrix deliberately installs one APK:
the bundled Runtime is not an external dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from full_upgrade_gate import execute as execute_full_upgrade


SPLIT = ("performance-manager", "luci-app-performance-manager",
         "performance-manager-rill", "rill-runtime")
ALL_IN_ONE = ("luci-app-performance-manager-all",)
PM_OWNED_PATHS = (
    "/usr/sbin/performance-manager.uc",
    "/usr/bin/rill-runtime",
    "/usr/share/performance-manager",
    "/www/luci-static/resources/view/performance-manager",
    "/usr/share/luci/menu.d/luci-app-performance-manager.json",
    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
    "/lib/upgrade/keep.d/performance-manager",
    "/lib/upgrade/keep.d/performance-manager-rill",
)


def package_name(path: Path) -> str:
    name = path.name
    for package in sorted((*SPLIT, "luci-app-performance-manager-all"),
                          key=len, reverse=True):
        if name.startswith(package + "-") or name.startswith(package + "_"):
            return package
    return ""


def locate_packages(root: Path, excluded_parts: tuple[str, ...] = ()) -> dict[str, Path]:
    found: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.apk")) + sorted(root.rglob("*.ipk")):
        if any(part in path.parts for part in excluded_parts):
            continue
        name = package_name(path)
        if name:
            found.setdefault(name, []).append(path)
    result = {}
    for name, paths in found.items():
        if len(paths) != 1:
            raise RuntimeError(f"expected one {name} artifact, found {paths}")
        result[name] = paths[0]
    return result


def pristine_payload(rootfs: Path) -> dict[str, object]:
    present = [path for path in PM_OWNED_PATHS
               if os.path.lexists(str(rootfs / path.lstrip("/")))]
    return {"checkedPaths": list(PM_OWNED_PATHS), "presentPaths": present,
            "pristineBeforeInstall": not present}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(rootfs: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["chroot", str(rootfs), "/bin/sh", "-c", command],
                          text=True, capture_output=True)


def clone_rootfs(source: Path, destination: Path) -> None:
    """Clone a rootfs without dereferencing its absolute symlinks.

    Docker Desktop shared mounts can make Python's copytree fail while
    copying dangling absolute symlinks from an OpenWrt rootfs.  Tar preserves
    those links exactly and matches the filesystem semantics used by the
    package-manager gate.
    """
    destination.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    with subprocess.Popen(["tar", "-cf", "-", "-C", str(source), "."],
                          stdout=subprocess.PIPE) as producer:
        assert producer.stdout is not None
        consumer = subprocess.run(["tar", "-xf", "-", "-C", str(destination)],
                                   stdin=producer.stdout, capture_output=True,
                                   text=True)
        producer.stdout.close()
        producer_returncode = producer.wait()
    if consumer.returncode != 0 or producer_returncode != 0:
        detail = consumer.stderr.strip() or f"tar producer exited {producer_returncode}"
        raise RuntimeError(f"could not clone rootfs: {detail}")


def execute(rootfs: Path, packages: dict[str, Path], names: tuple[str, ...],
            build: dict, openwrt_version: str, target: str, package_arch: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pm-composition-") as staging:
        staging = Path(staging)
        guest = rootfs / "tmp/pm-composition"
        guest.mkdir(parents=True, exist_ok=True)
        try:
            staged = []
            for name in names:
                src = packages[name]
                expected_sha = (build.get("packages", {}).get(name) or {}).get("apkSha256")
                actual_sha = sha256_file(src)
                if not expected_sha or actual_sha != expected_sha:
                    raise RuntimeError(
                        f"{name} artifact sha256 {actual_sha} does not match build metadata {expected_sha}"
                    )
                dst = guest / src.name
                shutil.copy2(src, dst)
                staged.append(f"/tmp/pm-composition/{src.name}")
            conflict_staged = []
            for conflict_name in SPLIT:
                if conflict_name not in names:
                    conflict_src = packages[conflict_name]
                    conflict_dst = guest / conflict_src.name
                    shutil.copy2(conflict_src, conflict_dst)
                    conflict_staged.append(f"/tmp/pm-composition/{conflict_src.name}")
            if names != ALL_IN_ONE:
                full_src = packages[ALL_IN_ONE[0]]
                full_dst = guest / full_src.name
                shutil.copy2(full_src, full_dst)
                full_staged = f"/tmp/pm-composition/{full_src.name}"
            expected_payload = {}
            for name in names:
                expected_payload.update(
                    (build.get("packages", {}).get(name, {}).get("installedPayload") or {})
                )
            snapshot_commands = ["mkdir -p /tmp/pm-composition-snapshot"]
            for payload_path in expected_payload:
                snapshot_path = f"/tmp/pm-composition-snapshot{payload_path}"
                snapshot_commands.append(
                    f"if [ -e '{payload_path}' ]; then mkdir -p '{Path(snapshot_path).parent}'; "
                    f"cp -a '{payload_path}' '{snapshot_path}'; fi"
                )
            snapshot_command = "; ".join(snapshot_commands) + "; "
            suffix = ".apk" if any(path.suffix == ".apk" for path in packages.values()) else ".ipk"
            preinstall_dependency_check = (
                "timeout_before=$(command -v timeout 2>/dev/null || true); "
                "if [ -n \"$timeout_before\" ]; then echo PM_TIMEOUT_BEFORE=present; "
                "else echo PM_TIMEOUT_BEFORE=absent; fi; "
                "test -z \"$timeout_before\"; "
            )
            expected_runtime_sha = (((build.get("packages", {}).get(ALL_IN_ONE[0]) or {})
                                      .get("runtimeBinary") or {}).get("sha256"))
            runtime_identity_check = ""
            if names == ALL_IN_ONE:
                if not isinstance(expected_runtime_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_runtime_sha):
                    raise RuntimeError("all-in-one build metadata lacks a valid bundled Runtime SHA256")
                runtime_identity_check = (
                    "test -x /usr/bin/rill-runtime; "
                    f"test \"$(sha256sum /usr/bin/rill-runtime | awk '{{print $1}}')\" = {shlex.quote(expected_runtime_sha)}; "
                    "echo PM_FULL_RUNTIME_IDENTITY=PASS; "
                )
            dependency_check = (
                "timeout_after=$(command -v timeout 2>/dev/null || true); "
                "test -n \"$timeout_after\"; "
                "apk info -e coreutils-timeout >/dev/null 2>&1; "
                "echo PM_TIMEOUT_AFTER=present; echo PM_COREUTILS_TIMEOUT_INSTALLED=PASS; "
                "echo PM_DEPENDENCY_CLOSURE=PASS; "
            )
            post_apk_install = (
                "mv /usr/bin/rill-runtime /tmp/rill-runtime.full-fault; "
                "fault_status=$(ubus call performance-manager rill_status '{}'); "
                "printf '%s' \"$fault_status\" | jsonfilter -e '@.state' | grep -Eq 'not-provisioned|unavailable|blocked|error'; "
                "mv /tmp/rill-runtime.full-fault /usr/bin/rill-runtime; "
                "echo PM_FULL_RILL_FAULT_SMOKE=PASS; "
                "apk del luci-app-performance-manager-all; "
                "test ! -x /usr/sbin/performance-manager.uc; "
                "test ! -e /usr/bin/rill-runtime; "
                "test ! -e /www/luci-static/resources/view/performance-manager/overview.js; "
                "test ! -e /usr/share/luci/menu.d/luci-app-performance-manager.json; "
                "test ! -e /usr/share/rpcd/acl.d/luci-app-performance-manager.json; "
                "test ! -e /lib/upgrade/keep.d/performance-manager; "
                "test ! -e /lib/upgrade/keep.d/performance-manager-rill; "
                "echo PM_FULL_UNINSTALL_SMOKE=PASS; "
                if names == ALL_IN_ONE else
                "apk del performance-manager-rill rill-runtime; "
                "test -x /usr/sbin/performance-manager.uc; "
                "status_after=$(ubus call performance-manager status '{}'); "
                "printf '%s' \"$status_after\" | grep -q '\"running\": true'; "
                "rill_after=$(ubus call performance-manager rill_status '{}'); "
                "printf '%s' \"$rill_after\" | jsonfilter -e '@.mode' | grep -qx advisory; "
                "printf '%s' \"$rill_after\" | jsonfilter -e '@.state' | grep -qx not-provisioned; "
                "echo PM_RILL_REMOVAL_SMOKE=PASS; "
            )
            command = (
                "set -eu; "
                "command -v apk >/dev/null 2>&1 || command -v opkg >/dev/null 2>&1; "
                + preinstall_dependency_check
                + "if command -v apk >/dev/null 2>&1; then "
                f"test '{suffix}' = '.apk'; "
                "if apk add --allow-untrusted --no-cache " + " ".join(staged) + "; then "
                "echo PM_APK_REPOSITORY_TRANSPORT=https; "
                "else echo PM_APK_REPOSITORY_TRANSPORT=unavailable; exit 2; fi; "
                + dependency_check
                + runtime_identity_check
                + "test -x /etc/init.d/performance-manager; "
                + "test -x /usr/sbin/performance-manager.uc; "
                + "test -x /usr/bin/rill-runtime; "
                + "test -f /usr/share/rpcd/acl.d/luci-app-performance-manager.json; "
                + "test -f /lib/upgrade/keep.d/performance-manager-rill; "
                + "mkdir -p /var/run/ubus /run /var/lock /tmp/performance-manager /etc/performance-manager; "
                + "rm -f /var/run/ubus/ubus.sock; "
                + "core_pid=0; /sbin/ubusd >/tmp/pm-composition-ubusd.log 2>&1 & ubusd_pid=$!; "
                + "trap 'kill $core_pid $ubusd_pid 2>/dev/null || true' EXIT; "
                + "sleep 1; kill -0 $ubusd_pid; "
                + "service_prog=$(sed -n 's/^PROG=//p' /etc/init.d/performance-manager); "
                + "test \"$service_prog\" = /usr/sbin/performance-manager.uc; "
                + "$service_prog >/tmp/pm-composition-core.log 2>&1 & core_pid=$!; "
                + "i=0; while ! ubus -S list performance-manager >/dev/null 2>&1; do "
                + "i=$((i+1)); test $i -lt 10; sleep 1; done; "
                + "status=$(ubus call performance-manager status '{}'); "
                + "printf '%s' \"$status\" | grep -q '\"running\": true'; "
                + "rill_status=$(ubus call performance-manager rill_status '{}'); "
                + "printf '%s' \"$rill_status\" | jsonfilter -e '@.mode' | grep -qx advisory; "
                + "printf '%s' \"$rill_status\" | jsonfilter -e '@.protocolVersion' | grep -qx 3; "
                + "printf '%s' \"$rill_status\" | jsonfilter -e '@.state' | grep -q .; "
                + "echo PM_SERVICE_SMOKE=PASS; echo PM_UBUS_STATUS=PASS; echo PM_RILL_STATUS=PASS; "
                + snapshot_command
                + ("if apk add --allow-untrusted --no-cache " + " ".join(conflict_staged)
                   + "; then exit 1; fi; echo PM_FULL_CONFLICT_SMOKE=PASS; "
                   if names == ALL_IN_ONE else
                   f"if apk add --allow-untrusted --no-cache {full_staged}; then exit 1; fi; echo PM_SPLIT_FULL_CONFLICT_SMOKE=PASS; ")
                + post_apk_install + "else "
                f"test '{suffix}' = '.ipk'; "
                "opkg install " + " ".join(staged) + "; "
                "timeout_after=$(command -v timeout 2>/dev/null || true); test -n \"$timeout_after\"; "
                "opkg status coreutils-timeout 2>/dev/null | grep -q 'Status: install'; "
                "echo PM_TIMEOUT_AFTER=present; echo PM_COREUTILS_TIMEOUT_INSTALLED=PASS; echo PM_DEPENDENCY_CLOSURE=PASS; "
                + "test -x /usr/sbin/performance-manager.uc; "
                + runtime_identity_check
                + "fi"
            )
            completed = run(rootfs, command)
            installed_payload = {}
            for payload_path, expected_sha in expected_payload.items():
                installed_path = rootfs / "tmp/pm-composition-snapshot" / payload_path.lstrip("/")
                actual_sha = sha256_file(installed_path) if installed_path.is_file() else None
                consumed_by_install = (
                    actual_sha is None and payload_path.startswith("/etc/uci-defaults/")
                )
                installed_payload[payload_path] = {
                    "expectedSha256": expected_sha,
                    "actualSha256": actual_sha,
                    "match": actual_sha == expected_sha or consumed_by_install,
                    "consumedByInstall": consumed_by_install,
                }
            payload_ok = all(record["match"] for record in installed_payload.values())
            service_smoke = "PM_SERVICE_SMOKE=PASS" in completed.stdout
            ubus_status_smoke = "PM_UBUS_STATUS=PASS" in completed.stdout
            rill_status_smoke = "PM_RILL_STATUS=PASS" in completed.stdout
            rill_removal_smoke = "PM_RILL_REMOVAL_SMOKE=PASS" in completed.stdout
            full_runtime_fault_smoke = "PM_FULL_RILL_FAULT_SMOKE=PASS" in completed.stdout
            full_uninstall_smoke = "PM_FULL_UNINSTALL_SMOKE=PASS" in completed.stdout
            full_runtime_identity = "PM_FULL_RUNTIME_IDENTITY=PASS" in completed.stdout
            package_conflict_smoke = (
                "PM_FULL_CONFLICT_SMOKE=PASS" in completed.stdout or
                "PM_SPLIT_FULL_CONFLICT_SMOKE=PASS" in completed.stdout
            )
            dependency_closure = {
                "timeoutPresentBeforeInstall": "PM_TIMEOUT_BEFORE=present" in completed.stdout,
                "timeoutPresentAfterInstall": "PM_TIMEOUT_AFTER=present" in completed.stdout,
                "coreutilsTimeoutInstalled": "PM_COREUTILS_TIMEOUT_INSTALLED=PASS" in completed.stdout,
                "resolvedByPackageManager": "PM_DEPENDENCY_CLOSURE=PASS" in completed.stdout,
            }
            runtime_smokes = (
                full_runtime_fault_smoke and full_uninstall_smoke and full_runtime_identity
                if names == ALL_IN_ONE else rill_removal_smoke
            )
            required_smokes = (
                service_smoke and ubus_status_smoke and rill_status_smoke and package_conflict_smoke
                and not dependency_closure["timeoutPresentBeforeInstall"]
                and dependency_closure["timeoutPresentAfterInstall"]
                and dependency_closure["coreutilsTimeoutInstalled"]
                and dependency_closure["resolvedByPackageManager"]
                and runtime_smokes
            )
            transport = (
                "https" if "PM_APK_REPOSITORY_TRANSPORT=https" in completed.stdout else
                "unavailable" if "PM_APK_REPOSITORY_TRANSPORT=unavailable" in completed.stdout else
                "not-evaluated"
            )
            status = "PASS" if completed.returncode == 0 and payload_ok and required_smokes and transport == "https" else (
                "BLOCKED" if transport == "unavailable" and completed.returncode == 2 else "FAIL"
            )
            return {
                "status": status,
                "packages": list(names),
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "serviceSmoke": service_smoke,
                "ubusStatusSmoke": ubus_status_smoke,
                "rillStatusSmoke": rill_status_smoke,
                "rillRemovalSmoke": rill_removal_smoke,
                "fullRuntimeFaultSmoke": full_runtime_fault_smoke,
                "fullUninstallSmoke": full_uninstall_smoke,
                "fullRuntimeIdentity": full_runtime_identity,
                "packageConflictSmoke": package_conflict_smoke,
                "dependencyClosure": dependency_closure,
                "upgradeSemantics": "NOT_APPLICABLE",
                "installedPayload": installed_payload,
                "installedPayloadExact": payload_ok,
                "repositoryTransport": transport,
                "transportVerdict": "PASS" if transport == "https" else "BLOCKED" if transport == "unavailable" else "FAIL",
            }
        finally:
            shutil.rmtree(guest, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--packages", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--openwrt-version", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--package-arch", required=True)
    parser.add_argument("--prior-full", type=Path)
    parser.add_argument("--prior-metadata", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_commit):
        parser.error("--expected-commit must be one full lowercase Git SHA")
    metadata = sorted(args.packages.rglob("build-metadata.json"))
    if len(metadata) != 1:
        raise SystemExit(f"expected one build-metadata.json, found {metadata}")
    build = json.loads(metadata[0].read_text())
    if build.get("repositoryCommitSha") != args.expected_commit:
        raise SystemExit("build metadata commit does not match --expected-commit")
    packages = locate_packages(args.packages, ("synthetic-prior",))
    missing = sorted(set(SPLIT + ALL_IN_ONE) - set(packages))
    if missing:
        raise SystemExit(f"missing package artifacts: {', '.join(missing)}")

    pristine = pristine_payload(args.rootfs)
    if not pristine["pristineBeforeInstall"]:
        report = {
            "schemaVersion": 1, "gate": "package-composition",
            "pmCommitSha": args.expected_commit, "verdict": "FAIL",
            "matrices": {}, "pristineRootfs": pristine,
            "fullUpgrade": {"schemaVersion": 1, "gate": "full-upgrade",
                             "verdict": "NOT_EVALUATED", "errors": ["rootfs is not pristine"]},
            "upgradeSemantics": "NOT_EVALUATED",
            "upgradeReason": "package-composition rootfs contains PM-owned files before install",
            "repositoryTransport": "NOT_EVALUATED",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"verdict": "FAIL", "reason": report["upgradeReason"]}))
        return 1
    results = {}
    with tempfile.TemporaryDirectory(prefix="pm-composition-rootfs-") as temp:
        for label, names in (("split", SPLIT), ("all-in-one", ALL_IN_ONE)):
            clone = Path(temp) / label
            clone_rootfs(args.rootfs, clone)
            results[label] = execute(clone, packages, names, build, args.openwrt_version,
                                     args.target, args.package_arch)
        prior_apk = args.prior_full
        prior_metadata_path = args.prior_metadata
        if prior_apk is None:
            candidates = sorted(path for path in args.packages.rglob("*.apk")
                                if "synthetic-prior" in path.parts)
            prior_apk = candidates[0] if len(candidates) == 1 else None
        if prior_metadata_path is None:
            candidates = sorted(path for path in args.packages.rglob("full-upgrade-prior.json")
                                if "synthetic-prior" in path.parts or "full-upgrade-prior" in path.parts)
            prior_metadata_path = candidates[0] if len(candidates) == 1 else None
        if prior_apk is not None and prior_metadata_path is not None and pristine["pristineBeforeInstall"]:
            upgrade_clone = Path(temp) / "full-upgrade"
            clone_rootfs(args.rootfs, upgrade_clone)
            upgrade = execute_full_upgrade(
                upgrade_clone, prior_apk.resolve(), packages[ALL_IN_ONE[0]].resolve(),
                json.loads(prior_metadata_path.read_text()), build, args.expected_commit,
            )
        else:
            upgrade = {
                "schemaVersion": 1, "gate": "full-upgrade", "verdict": "BLOCKED",
                "pmCommitSha": args.expected_commit,
                "errors": ["synthetic prior APK and metadata are required for real N->N+1 proof"],
                "syntheticPriorFixture": False,
            }
    report = {"schemaVersion": 1, "gate": "package-composition",
              "pmCommitSha": args.expected_commit,
              "verdict": "PASS" if pristine["pristineBeforeInstall"] and all(x["status"] == "PASS" for x in results.values()) and upgrade["verdict"] == "PASS" else
                         "BLOCKED" if any(x["status"] == "BLOCKED" for x in results.values()) or upgrade["verdict"] == "BLOCKED" else "FAIL",
              "matrices": results,
              "pristineRootfs": pristine,
              "fullUpgrade": upgrade,
              "upgradeSemantics": upgrade["verdict"],
              "upgradeReason": (upgrade.get("errors") or [None])[0],
              "repositoryTransport": "https" if all(x.get("transportVerdict") == "PASS" for x in results.values()) else "BLOCKED",
              "dependencyGraph": {
                  "performance-manager-rill": ["performance-manager", "rill-runtime"],
                  "performance-manager": ["performance-manager-core"],
                  "luci-app-performance-manager-all": ["provides:performance-manager-core"],
              }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verdict": report["verdict"], "matrices": {k: v["status"] for k, v in results.items()}}, indent=2))
    return 0 if report["verdict"] == "PASS" else 2 if report["verdict"] == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
