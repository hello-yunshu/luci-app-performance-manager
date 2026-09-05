#!/usr/bin/env python3
"""Run and validate a real full-package apk N -> N+1 upgrade.

The gate intentionally operates on two real APK files inside an OpenWrt
rootfs.  A synthetic prior fixture is acceptable for package-manager semantics
when it is explicitly marked as such; it is never treated as a historical
release compatibility result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path


PACKAGE = "luci-app-performance-manager-all"
CORE_PATH = "/usr/sbin/performance-manager.uc"
RUNTIME_PATH = "/usr/bin/rill-runtime"
LUCi_PATHS = (
    "/www/luci-static/resources/view/performance-manager/overview.js",
    "/usr/share/luci/menu.d/luci-app-performance-manager.json",
    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
)
REMOVE_PATHS = (
    CORE_PATH,
    RUNTIME_PATH,
    "/www/luci-static/resources/view/performance-manager/overview.js",
    "/usr/share/luci/menu.d/luci-app-performance-manager.json",
    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
    "/lib/upgrade/keep.d/performance-manager",
    "/lib/upgrade/keep.d/performance-manager-rill",
    "/usr/share/performance-manager",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UPGRADE_BOOLEAN_KEYS = (
    "priorVersionLessCurrent", "priorInstall", "packageManagerUpgrade",
    "versionAdvanced", "configPreserved", "coreUpdated", "runtimeUpdated",
    "luciUpdated", "installedPayloadExact", "oldPayloadRemoved",
    "serviceSmoke", "ubusSmoke", "rillSmoke", "postUpgradeUninstall",
)


def evaluate_upgrade_flags(flags: dict[str, object]) -> str:
    """Return the fail-closed verdict for a completed upgrade observation."""
    return "PASS" if all(flags.get(key) is True for key in UPGRADE_BOOLEAN_KEYS) else "FAIL"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(rootfs: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["chroot", str(rootfs), "/bin/sh", "-c", command],
        text=True,
        capture_output=True,
    )


def apk_version_key(value: str) -> tuple[tuple[int, object], ...]:
    """Provide deterministic ordering for the versions used by this gate."""
    version = value.split("-r", 1)[0].replace("_rc", "rc")
    parts: list[tuple[int, object]] = []
    for token in re.findall(r"\d+|[A-Za-z]+", version):
        parts.append((0, int(token)) if token.isdigit() else (1, token))
    return tuple(parts)


def payload_sha(record: object) -> str | None:
    if isinstance(record, str):
        return record if SHA256.fullmatch(record) else None
    if isinstance(record, dict):
        for key in ("sha256", "apkSha256", "expectedSha256", "sourceSha256"):
            value = record.get(key)
            if isinstance(value, str) and SHA256.fullmatch(value):
                return value
    return None


def current_payload(build: dict) -> dict[str, str]:
    record = (build.get("packages") or {}).get(PACKAGE) or {}
    payload = record.get("installedPayload") or {}
    result = {}
    for path in (CORE_PATH, RUNTIME_PATH, *LUCi_PATHS):
        digest = payload_sha(payload.get(path))
        if digest:
            result[path] = digest
    runtime = payload_sha((record.get("runtimeBinary") or {}).get("sha256"))
    if runtime:
        result[RUNTIME_PATH] = runtime
    return result


def rootfs_path(rootfs: Path, absolute: str) -> Path:
    return rootfs / absolute.lstrip("/")


def transport_status(completed: subprocess.CompletedProcess[str]) -> str:
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode == 0:
        return "https"
    if any(token in output for token in ("certificate", "x509", "tls", "ssl", "bad signature")):
        return "tls-failure"
    return "unavailable"


def _package_version_shell() -> str:
    return r'''package_version() {
  awk -v wanted="$1" '
    /^P:/ { package=substr($0, 3) }
    /^V:/ && package == wanted { print substr($0, 3); exit }
  ' /lib/apk/db/installed 2>/dev/null || true
}'''


def _service_shell() -> str:
    return r'''start_core() {
  mkdir -p /var/run/ubus /run /var/lock /tmp/performance-manager /etc/performance-manager
  rm -f /var/run/ubus/ubus.sock
  /sbin/ubusd >/tmp/pm-full-upgrade-ubusd.log 2>&1 & ubusd_pid=$!
  i=0
  while ! test -S /var/run/ubus/ubus.sock; do
    i=$((i + 1)); test "$i" -lt 20; sleep 1
  done
  /usr/sbin/performance-manager.uc >/tmp/pm-full-upgrade-core.log 2>&1 & core_pid=$!
  i=0
  while ! ubus -S list performance-manager >/dev/null 2>&1; do
    i=$((i + 1)); test "$i" -lt 20; sleep 1
  done
}
stop_core() {
  kill "$core_pid" "$ubusd_pid" 2>/dev/null || true
  wait "$core_pid" "$ubusd_pid" 2>/dev/null || true
}'''


def execute(
    rootfs: Path,
    prior_apk: Path,
    current_apk: Path,
    prior: dict,
    build: dict,
    expected_commit: str,
) -> dict:
    current_record = (build.get("packages") or {}).get(PACKAGE) or {}
    prior_pkgver = str(prior.get("pkgver") or prior.get("version") or "")
    current_pkgver = str(current_record.get("pkgver") or "")
    errors: list[str] = []
    if not prior.get("syntheticPriorFixture") is True:
        errors.append("prior fixture is not explicitly marked syntheticPriorFixture=true")
    if prior.get("historicalReleaseUpgrade") is not False:
        errors.append("historicalReleaseUpgrade must be false for a synthetic fixture")
    if not prior_pkgver or not current_pkgver or apk_version_key(prior_pkgver) >= apk_version_key(current_pkgver):
        errors.append(f"prior pkgver {prior_pkgver!r} is not lower than current {current_pkgver!r}")
    current_sha = sha256_file(current_apk)
    prior_sha = sha256_file(prior_apk)
    if current_record.get("apkSha256") != current_sha:
        errors.append("current APK SHA does not match build metadata")
    if prior.get("sha256") != prior_sha:
        errors.append("prior APK SHA does not match fixture metadata")
    expected = current_payload(build)
    if any(path not in expected for path in (CORE_PATH, RUNTIME_PATH, *LUCi_PATHS)):
        errors.append("current build metadata lacks exact Core/Runtime/LuCI payload SHA")

    result = {
        "schemaVersion": 1,
        "gate": "full-upgrade",
        "pmCommitSha": expected_commit,
        "openwrtVersion": "25.12.5",
        "target": "x86/64",
        "packageArch": "x86_64",
        "prior": {
            "version": prior.get("version"),
            "pkgver": prior_pkgver,
            "sha256": prior_sha,
            "syntheticPriorFixture": prior.get("syntheticPriorFixture") is True,
            "historicalReleaseUpgrade": prior.get("historicalReleaseUpgrade") is True,
            "marker": prior.get("marker"),
        },
        "current": {
            "version": current_record.get("pkgver"),
            "pkgver": current_pkgver,
            "sha256": current_sha,
            "repositoryCommitSha": expected_commit,
        },
        "installPrior": "NOT_EVALUATED",
        "userConfigWritten": False,
        "packageManagerUpgrade": "NOT_EVALUATED",
        "versionAdvanced": False,
        "configPreserved": False,
        "coreUpdated": False,
        "runtimeUpdated": False,
        "luciUpdated": False,
        "installedPayloadExact": False,
        "oldPayloadRemoved": False,
        "serviceSmoke": "NOT_EVALUATED",
        "ubusSmoke": "NOT_EVALUATED",
        "rillSmoke": "NOT_EVALUATED",
        "postUpgradeUninstall": "NOT_EVALUATED",
        "repositoryTransport": "NOT_EVALUATED",
        "transportVerdict": "NOT_EVALUATED",
        "verdict": "FAIL" if errors else "BLOCKED",
        "errors": errors,
    }
    if errors:
        return result

    root_tmp = "/tmp/pm-full-upgrade"
    prior_guest = f"{root_tmp}/{prior_apk.name}"
    current_guest = f"{root_tmp}/{current_apk.name}"
    prior_marker = str(prior.get("marker") or "")
    command = "set -eu; "
    command += f"mkdir -p {shlex.quote(root_tmp)}; "
    command += f"{_package_version_shell()}; {_service_shell()}; "
    command += f"apk add --allow-untrusted --no-cache {shlex.quote(prior_guest)}; "
    command += f"test \"$(package_version {PACKAGE})\" = {shlex.quote(prior_pkgver)}; "
    command += "echo PM_PRIOR_INSTALL=PASS; "
    command += "uci set performance-manager.core.goal='synthetic-upgrade-user-value'; "
    command += "uci commit performance-manager; "
    command += "test \"$(uci get performance-manager.core.goal)\" = synthetic-upgrade-user-value; "
    command += "echo PM_CONFIG_WRITTEN=PASS; "
    command += "start_core; "
    command += "status=$(ubus call performance-manager status '{}'); printf '%s' \"$status\" | grep -q '\"running\": true'; "
    command += "rill=$(ubus call performance-manager rill_status '{}'); printf '%s' \"$rill\" | jsonfilter -e '@.mode' | grep -qx advisory; "
    command += "echo PM_PRIOR_SERVICE=PASS; "
    command += "for payload_path in /usr/sbin/performance-manager.uc /usr/bin/rill-runtime /www/luci-static/resources/view/performance-manager/overview.js; do sha256sum \"$payload_path\"; done > /tmp/pm-full-upgrade/prior-payload-sha256; "
    command += "stop_core; "
    command += f"apk add --allow-untrusted --no-cache --upgrade {shlex.quote(current_guest)}; "
    command += f"test \"$(package_version {PACKAGE})\" = {shlex.quote(current_pkgver)}; "
    command += "echo PM_PACKAGE_UPGRADE=PASS; "
    command += "test \"$(uci get performance-manager.core.goal)\" = synthetic-upgrade-user-value; echo PM_CONFIG_PRESERVED=PASS; "
    command += "for payload_path in /usr/sbin/performance-manager.uc /usr/bin/rill-runtime /www/luci-static/resources/view/performance-manager/overview.js /usr/share/luci/menu.d/luci-app-performance-manager.json /usr/share/rpcd/acl.d/luci-app-performance-manager.json; do sha256sum \"$payload_path\"; done > /tmp/pm-full-upgrade/installed-payload-sha256; "
    command += "start_core; "
    command += "status=$(ubus call performance-manager status '{}'); printf '%s' \"$status\" | grep -q '\"running\": true'; echo PM_POST_UPGRADE_SERVICE=PASS; echo PM_UBUS=PASS; "
    command += "rill=$(ubus call performance-manager rill_status '{}'); printf '%s' \"$rill\" | jsonfilter -e '@.mode' | grep -qx advisory; printf '%s' \"$rill\" | jsonfilter -e '@.protocolVersion' | grep -qx 3; echo PM_RILL=PASS; "
    command += "stop_core; "
    command += f"apk del {PACKAGE}; "
    for path in REMOVE_PATHS:
        command += f"test ! -e {shlex.quote(path)}; "
    if prior_marker:
        command += f"if grep -R -F -- {shlex.quote(prior_marker)} /usr/share 2>/dev/null; then exit 1; fi; "
    command += "echo PM_POST_UPGRADE_UNINSTALL=PASS; "
    completed = run(rootfs, command)
    output = f"{completed.stdout}\n{completed.stderr}"
    result["stdout"] = completed.stdout[-6000:]
    result["stderr"] = completed.stderr[-6000:]
    result["repositoryTransport"] = transport_status(completed)
    result["transportVerdict"] = (
        "PASS" if result["repositoryTransport"] == "https" else
        "FAIL" if result["repositoryTransport"] == "tls-failure" else "BLOCKED"
    )
    result["installPrior"] = "PASS" if "PM_PRIOR_INSTALL=PASS" in output else "FAIL"
    result["userConfigWritten"] = "PM_CONFIG_WRITTEN=PASS" in output
    result["packageManagerUpgrade"] = "PASS" if "PM_PACKAGE_UPGRADE=PASS" in output else "FAIL"
    result["versionAdvanced"] = "PM_PACKAGE_UPGRADE=PASS" in output and prior_pkgver != current_pkgver
    result["configPreserved"] = "PM_CONFIG_PRESERVED=PASS" in output
    result["serviceSmoke"] = "PASS" if "PM_PRIOR_SERVICE=PASS" in output and "PM_POST_UPGRADE_SERVICE=PASS" in output else "FAIL"
    result["ubusSmoke"] = "PASS" if "PM_UBUS=PASS" in output else "FAIL"
    result["rillSmoke"] = "PASS" if "PM_RILL=PASS" in output else "FAIL"
    result["postUpgradeUninstall"] = "PASS" if "PM_POST_UPGRADE_UNINSTALL=PASS" in output else "FAIL"

    prior_payload = prior.get("payload") or {}
    # The rootfs is intentionally observed after the command: package removal
    # removes the payload, so the command's explicit current hashes are the
    # authoritative installed-state check captured before uninstall below.
    prior_identity = rootfs_path(rootfs, "/tmp/pm-full-upgrade/prior-payload-sha256")
    installed_identity = rootfs_path(rootfs, "/tmp/pm-full-upgrade/installed-payload-sha256")
    prior_text = prior_identity.read_text() if prior_identity.is_file() else ""
    identity = installed_identity.read_text() if installed_identity.is_file() else ""
    result["installedPayload"] = {}
    if not identity:
        result["installedPayloadExact"] = False
    else:
        observed = {}
        for line in identity.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1].startswith("/"):
                observed[fields[1]] = fields[0]
        result["installedPayload"] = {
            path: {"expectedSha256": digest, "observedAfterUpgrade": observed.get(path),
                   "match": observed.get(path) == digest}
            for path, digest in expected.items()
        }
        result["installedPayloadExact"] = all(item["match"] for item in result["installedPayload"].values())
    prior_observed = {}
    for line in prior_text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].startswith("/"):
            prior_observed[fields[1]] = fields[0]
    result["priorPayload"] = {
        path: {"expectedSha256": payload_sha(prior_payload.get(path)),
               "observedBeforeUpgrade": prior_observed.get(path)}
        for path in expected
    }
    result["coreUpdated"] = (
        result["installedPayload"].get(CORE_PATH, {}).get("match") is True and
        prior_observed.get(CORE_PATH) and prior_observed.get(CORE_PATH) != expected.get(CORE_PATH)
    )
    result["runtimeUpdated"] = (
        result["installedPayload"].get(RUNTIME_PATH, {}).get("match") is True and
        prior_observed.get(RUNTIME_PATH) and prior_observed.get(RUNTIME_PATH) != expected.get(RUNTIME_PATH)
    )
    result["luciUpdated"] = (
        result["installedPayload"].get(LUCi_PATHS[0], {}).get("match") is True and
        prior_observed.get(LUCi_PATHS[0]) and prior_observed.get(LUCi_PATHS[0]) != expected.get(LUCi_PATHS[0])
    )
    result["oldPayloadRemoved"] = "PM_POST_UPGRADE_UNINSTALL=PASS" in output
    flags = {
        "priorVersionLessCurrent": apk_version_key(prior_pkgver) < apk_version_key(current_pkgver),
        "priorInstall": result["installPrior"] == "PASS",
        "packageManagerUpgrade": result["packageManagerUpgrade"] == "PASS",
        "versionAdvanced": result["versionAdvanced"],
        "configPreserved": result["configPreserved"],
        "coreUpdated": result["coreUpdated"],
        "runtimeUpdated": result["runtimeUpdated"],
        "luciUpdated": result["luciUpdated"],
        "installedPayloadExact": result["installedPayloadExact"],
        "oldPayloadRemoved": result["oldPayloadRemoved"],
        "serviceSmoke": result["serviceSmoke"] == "PASS",
        "ubusSmoke": result["ubusSmoke"] == "PASS",
        "rillSmoke": result["rillSmoke"] == "PASS",
        "postUpgradeUninstall": result["postUpgradeUninstall"] == "PASS",
    }
    result["upgradeAssertions"] = flags
    required = evaluate_upgrade_flags(flags) == "PASS" and result["transportVerdict"] == "PASS"
    result["verdict"] = "PASS" if completed.returncode == 0 and required else (
        "BLOCKED" if result["transportVerdict"] == "BLOCKED" else "FAIL"
    )
    if not required:
        result["errors"].append("one or more real N->N+1 upgrade assertions failed")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--prior-apk", required=True, type=Path)
    parser.add_argument("--prior-metadata", required=True, type=Path)
    parser.add_argument("--current-apk", required=True, type=Path)
    parser.add_argument("--build-metadata", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_commit):
        parser.error("--expected-commit must be one full lowercase Git SHA")
    prior = json.loads(args.prior_metadata.read_text())
    build = json.loads(args.build_metadata.read_text())
    result = execute(args.rootfs, args.prior_apk, args.current_apk, prior, build, args.expected_commit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "errors": result["errors"]}, indent=2))
    return 0 if result["verdict"] == "PASS" else (2 if result["verdict"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
