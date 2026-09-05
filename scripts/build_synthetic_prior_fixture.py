#!/usr/bin/env python3
"""Build a private, lower-version full APK fixture with the official SDK.

This helper mutates only a temporary SDK package tree, builds one real APK,
records the old payload identities, and restores the SDK tree before returning.
The fixture is deliberately not a release artifact and is labelled as
synthetic so it cannot be confused with a historical public package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


PACKAGE = "luci-app-performance-manager-all"
CORE = "package/openwrt-performance-manager/performance-manager/files/usr/sbin/performance-manager.uc"
LUCi = "package/openwrt-performance-manager/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/overview.js"
RUNTIME = "package/openwrt-performance-manager/luci-app-performance-manager-all/files/usr/bin/rill-runtime"
NOTICES = "package/THIRD_PARTY_NOTICES"
PAYLOAD_PATHS = {
    CORE: "/usr/sbin/performance-manager.uc",
    LUCi: "/www/luci-static/resources/view/performance-manager/overview.js",
    RUNTIME: "/usr/bin/rill-runtime",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release", default="1")
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    sdk = args.sdk_dir.resolve()
    out = args.out.resolve()
    package_paths = [sdk / relative for relative in (*PAYLOAD_PATHS, NOTICES)]
    if any(not path.is_file() for path in package_paths):
        missing = [str(path) for path in package_paths if not path.is_file()]
        raise SystemExit(f"synthetic fixture source missing: {missing}")

    marker = f"pm-synthetic-prior-fixture:{args.version}-{args.release}:{args.commit}"
    backups: dict[Path, bytes] = {path: path.read_bytes() for path in package_paths}
    try:
        (sdk / CORE).write_bytes(backups[sdk / CORE] + f"\n// {marker}\n".encode())
        (sdk / LUCi).write_bytes(backups[sdk / LUCi] + f"\n// {marker}\n".encode())
        # Appending a byte keeps a valid ELF executable while making the prior
        # Runtime identity observably different from the current build.
        (sdk / RUNTIME).write_bytes(backups[sdk / RUNTIME] + b"\n")
        (sdk / NOTICES).write_bytes(backups[sdk / NOTICES] + f"\n{marker}\n".encode())
        # Keep the SDK's already-qualified dependency closure warm.  Cleaning
        # this package also forces unrelated feed sources back through their
        # fallback download path on cold runners, where upstream tarball hashes
        # can legitimately be unavailable.
        run([
            "make", f"package/{PACKAGE}/compile", "V=s",
            f"PKG_VERSION={args.version}", f"PKG_RELEASE={args.release}",
        ], sdk)
        matches = sorted(sdk.glob(f"bin/**/{PACKAGE}_{args.version}-{args.release}_*.apk"))
        if len(matches) != 1:
            raise SystemExit(f"expected one synthetic prior APK, found {matches}")
        apk = matches[0]
        out.mkdir(parents=True, exist_ok=True)
        target = out / apk.name
        shutil.copy2(apk, target)
        payload = {
            payload_path: sha256(sdk / source_relative)
            for source_relative, payload_path in PAYLOAD_PATHS.items()
        }
        metadata = {
            "schemaVersion": 1,
            "gate": "full-upgrade-prior-fixture",
            "package": PACKAGE,
            "version": args.version,
            "pkgver": f"{args.version}-r{args.release}",
            "sha256": sha256(target),
            "syntheticPriorFixture": True,
            "historicalReleaseUpgrade": False,
            "marker": marker,
            "payload": payload,
            "publicRelease": False,
            "stableReleaseAsset": False,
            "sourceCommitSha": args.commit,
            "note": "Private test fixture only; not a historical released-version artifact.",
        }
        (out / "full-upgrade-prior.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2))
        return 0
    finally:
        for path, content in backups.items():
            path.write_bytes(content)


if __name__ == "__main__":
    raise SystemExit(main())
