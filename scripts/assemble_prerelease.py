#!/usr/bin/env python3
"""Assemble a prerelease from named workflow artifacts without path ambiguity."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


PACKAGE = "luci-app-performance-manager-all"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_root(root: Path, suffix: str) -> Path:
    matches = [path for path in root.iterdir() if path.is_dir() and path.name.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one artifact root ending {suffix!r}, found {matches}")
    return matches[0]


def unique(root: Path, name: str) -> Path:
    matches = [path for path in root.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} inside {root.name}, found {matches}")
    return matches[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source-dist", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)

    input_root = Path(args.input).resolve()
    output = Path(args.out).resolve()
    source_dist = Path(args.source_dist).resolve()
    dedicated = artifact_root(input_root, "-all-in-one-apk")
    build_root = artifact_root(input_root, "-packages-and-evidence")
    final_root = artifact_root(input_root, "final-release-evidence-build")

    manifest_path = unique(dedicated, "all-in-one-release-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    apk_info = manifest.get("apk") or {}
    apk = unique(dedicated, apk_info.get("filename") or "__missing_apk_filename__")
    apk_sha = sha256(apk)
    if manifest.get("pmCommitSha") != args.expected_sha:
        raise RuntimeError("all-in-one manifest commit mismatch")
    if manifest.get("package") != PACKAGE or apk_sha != apk_info.get("sha256"):
        raise RuntimeError("all-in-one manifest package or APK digest mismatch")

    verification_path = unique(build_root, "apk-verification.json")
    verification = json.loads(verification_path.read_text())
    verified = (verification.get("packages") or {}).get(PACKAGE) or {}
    if verification.get("verdict") != "PASS" or verification.get("pmCommitSha") != args.expected_sha:
        raise RuntimeError("APK verification verdict or commit mismatch")
    if verified.get("status") != "ok" or verified.get("sha256") != apk_sha:
        raise RuntimeError("dedicated APK does not match exact APK verification")

    metadata_path = unique(build_root, "build-metadata.json")
    metadata = json.loads(metadata_path.read_text())
    built = (metadata.get("packages") or {}).get(PACKAGE) or {}
    if metadata.get("verdict") != "PASS" or metadata.get("repositoryCommitSha") != args.expected_sha:
        raise RuntimeError("build metadata verdict or commit mismatch")
    if built.get("apkSha256") != apk_sha:
        raise RuntimeError("dedicated APK does not match build metadata")

    final_path = unique(final_root, "final-release-evidence.json")
    final = json.loads(final_path.read_text())
    if final.get("overallVerdict") != "PASS" or final.get("pmCommitSha") != args.expected_sha:
        raise RuntimeError("final build evidence verdict or commit mismatch")

    source_zip = source_dist / f"openwrt-performance-manager-{args.version}.zip"
    source_manifest = source_dist / f"openwrt-performance-manager-{args.version}.manifest.json"
    for path in (source_zip, source_manifest):
        if not path.is_file():
            raise RuntimeError(f"source artifact missing: {path}")

    output.mkdir(parents=True, exist_ok=True)
    owned = {
        apk.name: apk,
        manifest_path.name: manifest_path,
        "all-in-one-checksums.txt": unique(dedicated, "all-in-one-checksums.txt"),
        metadata_path.name: metadata_path,
        verification_path.name: verification_path,
        final_path.name: final_path,
        "FINAL_AUDIT.json": unique(build_root, "FINAL_AUDIT.json"),
        "FINAL_AUDIT.md": unique(build_root, "FINAL_AUDIT.md"),
        source_zip.name: source_zip,
        source_manifest.name: source_manifest,
    }
    for name, source in owned.items():
        shutil.copy2(source, output / name)
    checksum = output / "release-checksums.txt"
    checksum.write_text("".join(
        f"{sha256(path)}  {path.name}\n"
        for path in sorted(output.iterdir()) if path.is_file() and path != checksum
    ))
    print(json.dumps({"package": PACKAGE, "apk": apk.name, "sha256": apk_sha,
                      "commit": args.expected_sha, "assets": len(owned) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
