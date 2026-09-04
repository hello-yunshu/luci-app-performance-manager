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
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SPLIT = ("performance-manager", "luci-app-performance-manager",
         "performance-manager-rill", "rill-runtime")
ALL_IN_ONE = ("luci-app-performance-manager-all",)


def package_name(path: Path) -> str:
    name = path.name
    for package in sorted((*SPLIT, "luci-app-performance-manager-all"),
                          key=len, reverse=True):
        if name.startswith(package + "-") or name.startswith(package + "_"):
            return package
    return ""


def locate_packages(root: Path) -> dict[str, Path]:
    found: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.apk")) + sorted(root.rglob("*.ipk")):
        name = package_name(path)
        if name:
            found.setdefault(name, []).append(path)
    result = {}
    for name, paths in found.items():
        if len(paths) != 1:
            raise RuntimeError(f"expected one {name} artifact, found {paths}")
        result[name] = paths[0]
    return result


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
            post_apk_install = (
                "mv /usr/bin/rill-runtime /tmp/rill-runtime.full-fault; "
                "fault_status=$(ubus call performance-manager rill_status '{}'); "
                "printf '%s' \"$fault_status\" | jsonfilter -e '@.state' | grep -Eq 'not-provisioned|unavailable|blocked|error'; "
                "mv /tmp/rill-runtime.full-fault /usr/bin/rill-runtime; "
                "echo PM_FULL_RILL_FAULT_SMOKE=PASS; "
                "apk del luci-app-performance-manager-all; "
                "test ! -x /usr/sbin/performance-manager.uc; "
                "test ! -f /usr/share/rpcd/acl.d/luci-app-performance-manager.json; "
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
                "if command -v apk >/dev/null 2>&1; then "
                f"test '{suffix}' = '.apk'; "
                "if apk add --allow-untrusted --no-cache " + " ".join(staged) + "; then "
                "echo PM_APK_REPOSITORY_TRANSPORT=https; "
                "else "
                "printf '%s\\n' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/targets/{target}/packages/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/base/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/luci/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/packages/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/routing/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/telephony/packages.adb' "
                f"'http://downloads.openwrt.org/releases/{openwrt_version}/packages/{package_arch}/video/packages.adb' "
                "> /tmp/pm-repositories-http; "
                "apk --repositories-file /tmp/pm-repositories-http "
                "add --allow-untrusted --no-cache " + " ".join(staged) + "; "
                "echo PM_APK_REPOSITORY_TRANSPORT=http-fallback; "
                "fi; "
                "test -x /etc/init.d/performance-manager; "
                "test -x /usr/sbin/performance-manager.uc; "
                "test -x /usr/bin/rill-runtime; "
                "test -f /usr/share/rpcd/acl.d/luci-app-performance-manager.json; "
                "test -f /lib/upgrade/keep.d/performance-manager-rill; "
                "mkdir -p /var/run/ubus /run /var/lock /tmp/performance-manager /etc/performance-manager; "
                "rm -f /var/run/ubus/ubus.sock; "
                "core_pid=0; /sbin/ubusd >/tmp/pm-composition-ubusd.log 2>&1 & ubusd_pid=$!; "
                "trap 'kill $core_pid $ubusd_pid 2>/dev/null || true' EXIT; "
                "sleep 1; kill -0 $ubusd_pid; "
                "service_prog=$(sed -n 's/^PROG=//p' /etc/init.d/performance-manager); "
                "test \"$service_prog\" = /usr/sbin/performance-manager.uc; "
                "$service_prog >/tmp/pm-composition-core.log 2>&1 & core_pid=$!; "
                "i=0; while ! ubus -S list performance-manager >/dev/null 2>&1; do "
                "i=$((i+1)); test $i -lt 10; sleep 1; done; "
                "status=$(ubus call performance-manager status '{}'); "
                "printf '%s' \"$status\" | grep -q '\"running\": true'; "
                "rill_status=$(ubus call performance-manager rill_status '{}'); "
                "printf '%s' \"$rill_status\" | jsonfilter -e '@.mode' | grep -qx advisory; "
                "printf '%s' \"$rill_status\" | jsonfilter -e '@.protocolVersion' | grep -Eq '^[0-9]+$'; "
                "printf '%s' \"$rill_status\" | jsonfilter -e '@.state' | grep -q .; "
                "echo PM_SERVICE_SMOKE=PASS; echo PM_UBUS_STATUS=PASS; echo PM_RILL_STATUS=PASS; "
                + snapshot_command
                + ("if apk add --allow-untrusted --no-cache " + " ".join(conflict_staged)
                   + "; then exit 1; fi; echo PM_FULL_CONFLICT_SMOKE=PASS; "
                   if names == ALL_IN_ONE else
                   f"if apk add --allow-untrusted --no-cache {full_staged}; then exit 1; fi; echo PM_SPLIT_FULL_CONFLICT_SMOKE=PASS; ")
                + post_apk_install + "else "
                f"test '{suffix}' = '.ipk'; "
                "opkg install " + " ".join(staged) + "; "
                "test -x /usr/sbin/performance-manager.uc; "
                "fi"
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
            return {
                "status": "PASS" if completed.returncode == 0 and payload_ok else "FAIL",
                "packages": list(names),
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "serviceSmoke": service_smoke,
                "ubusStatusSmoke": ubus_status_smoke,
                "rillStatusSmoke": rill_status_smoke,
                "rillRemovalSmoke": rill_removal_smoke,
                "fullRuntimeFaultSmoke": "PM_FULL_RILL_FAULT_SMOKE=PASS" in completed.stdout,
                "fullUninstallSmoke": "PM_FULL_UNINSTALL_SMOKE=PASS" in completed.stdout,
                "packageConflictSmoke": ("PM_FULL_CONFLICT_SMOKE=PASS" in completed.stdout or
                                         "PM_SPLIT_FULL_CONFLICT_SMOKE=PASS" in completed.stdout),
                # Upgrade semantics require a real N -> N+1 package-manager run
                # on each target; do not infer that from install/uninstall.
                "upgradeSemantics": "NOT_EVALUATED",
                "installedPayload": installed_payload,
                "installedPayloadExact": payload_ok,
                "repositoryTransport": (
                    "http-fallback" if "PM_APK_REPOSITORY_TRANSPORT=http-fallback" in completed.stdout
                    else "https"
                ),
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
    packages = locate_packages(args.packages)
    missing = sorted(set(SPLIT + ALL_IN_ONE) - set(packages))
    if missing:
        raise SystemExit(f"missing package artifacts: {', '.join(missing)}")

    results = {}
    with tempfile.TemporaryDirectory(prefix="pm-composition-rootfs-") as temp:
        for label, names in (("split", SPLIT), ("all-in-one", ALL_IN_ONE)):
            clone = Path(temp) / label
            clone_rootfs(args.rootfs, clone)
            results[label] = execute(clone, packages, names, build, args.openwrt_version,
                                     args.target, args.package_arch)
    report = {"schemaVersion": 1, "gate": "package-composition",
              "pmCommitSha": args.expected_commit,
              "verdict": "PASS" if all(x["status"] == "PASS" for x in results.values()) else "FAIL",
              "matrices": results,
              "upgradeSemantics": "NOT_EVALUATED",
              "dependencyGraph": {
                  "performance-manager-rill": ["performance-manager", "rill-runtime"],
                  "performance-manager": ["performance-manager-core"],
                  "luci-app-performance-manager-all": ["provides:performance-manager-core"],
              }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verdict": report["verdict"], "matrices": {k: v["status"] for k, v in results.items()}}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
