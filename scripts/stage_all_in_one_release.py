#!/usr/bin/env python3
"""Stage the exact verified all-in-one APK for prerelease publication."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256  # noqa: E402


PACKAGE = "luci-app-performance-manager-all"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-dir", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    sdk_dir = Path(args.sdk_dir).resolve()
    verification_path = Path(args.verification).resolve()
    out = Path(args.out).resolve()
    report = json.loads(verification_path.read_text())
    if report.get("verdict") != "PASS":
        raise RuntimeError("APK verification verdict is not PASS")
    record = (report.get("packages") or {}).get(PACKAGE) or {}
    expected_name = record.get("filename")
    expected_sha = record.get("sha256")
    if record.get("status") != "ok" or not expected_name or not expected_sha:
        raise RuntimeError("all-in-one APK lacks exact verified identity")

    try:
        identity = resolve_artifact(PACKAGE, expected_sha, [sdk_dir], expected_name)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    source = Path(identity["canonicalPath"])

    out.mkdir(parents=True, exist_ok=True)
    target = out / expected_name
    shutil.copy2(source, target)
    manifest = {
        "schemaVersion": 1,
        "contract": "performance-manager-all-in-one-prerelease",
        "pmCommitSha": report.get("pmCommitSha"),
        "version": report.get("expectedVersion"),
        "architecture": report.get("arch"),
        "package": PACKAGE,
        "apk": {
            "filename": target.name,
            "sha256": expected_sha,
            "bytes": target.stat().st_size,
            "pkgver": record.get("pkgver"),
            "arch": record.get("arch"),
            "copies": identity["copies"],
            "copyCount": identity["copyCount"],
            "allCopiesIdentical": identity["allCopiesIdentical"],
        },
        "payloadVerification": {
            "core": (record.get("core") or {}).get("status"),
            "fileCount": len(record.get("installedPayload") or {}),
            "translation": (record.get("installedPayload") or {}).get(
                "/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo"
            ),
        },
        "externalRuntime": {
            "package": "rill-runtime",
            "binary": "/usr/bin/rill-runtime",
            "releaseIncluded": False,
        },
    }
    manifest_path = out / "all-in-one-release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    checksum_path = out / "all-in-one-checksums.txt"
    checksum_path.write_text(
        f"{sha256(target)}  {target.name}\n"
        f"{sha256(manifest_path)}  {manifest_path.name}\n"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
