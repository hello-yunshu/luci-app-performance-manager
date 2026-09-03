#!/usr/bin/env python3
"""Exercise the published PM APK graph in a real OpenWrt rootfs.

The package verifier proves each APK's metadata and payload. This gate proves
the user-facing install combinations as a package manager sees them, including
the virtual ``performance-manager-core`` capability used by the optional Rill
glue package.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SPLIT = ("performance-manager", "luci-app-performance-manager",
         "performance-manager-rill", "rill-runtime")
ALL_IN_ONE = ("luci-app-performance-manager-all", "performance-manager-rill",
              "rill-runtime")


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


def run(rootfs: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["chroot", str(rootfs), "/bin/sh", "-c", command[0]],
                          text=True, capture_output=True)


def execute(rootfs: Path, packages: dict[str, Path], names: tuple[str, ...],
            openwrt_version: str, target: str, package_arch: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pm-composition-") as staging:
        staging = Path(staging)
        guest = rootfs / "tmp/pm-composition"
        guest.mkdir(parents=True, exist_ok=True)
        try:
            staged = []
            for name in names:
                src = packages[name]
                dst = guest / src.name
                shutil.copy2(src, dst)
                staged.append(f"/tmp/pm-composition/{src.name}")
            suffix = ".apk" if any(path.suffix == ".apk" for path in packages.values()) else ".ipk"
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
                "test -x /usr/sbin/performance-manager.uc; "
                "test -x /usr/bin/rill-runtime; "
                "test -f /usr/share/rpcd/acl.d/luci-app-performance-manager.json; "
                "apk del performance-manager-rill rill-runtime; "
                "test -x /usr/sbin/performance-manager.uc; "
                "else "
                f"test '{suffix}' = '.ipk'; "
                "opkg install " + " ".join(staged) + "; "
                "test -x /usr/sbin/performance-manager.uc; "
                "fi"
            )
            completed = run(rootfs, [command])
            return {
                "status": "PASS" if completed.returncode == 0 else "FAIL",
                "packages": list(names),
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
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
    packages = locate_packages(args.packages)
    missing = sorted(set(SPLIT + ALL_IN_ONE) - set(packages))
    if missing:
        raise SystemExit(f"missing package artifacts: {', '.join(missing)}")

    results = {}
    with tempfile.TemporaryDirectory(prefix="pm-composition-rootfs-") as temp:
        for label, names in (("split", SPLIT), ("all-in-one", ALL_IN_ONE)):
            clone = Path(temp) / label
            shutil.copytree(args.rootfs, clone, symlinks=True)
            results[label] = execute(clone, packages, names, args.openwrt_version,
                                     args.target, args.package_arch)
    report = {"schemaVersion": 1, "gate": "package-composition",
              "pmCommitSha": args.expected_commit,
              "verdict": "PASS" if all(x["status"] == "PASS" for x in results.values()) else "FAIL",
              "matrices": results,
              "dependencyGraph": {
                  "performance-manager-rill": ["performance-manager-core", "rill-runtime"],
                  "performance-manager": ["performance-manager-core"],
                  "luci-app-performance-manager-all": ["provides:performance-manager-core"],
              }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verdict": report["verdict"], "matrices": {k: v["status"] for k, v in results.items()}}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
