#!/usr/bin/env python3
"""Build the public release manifest from one exact verified APK identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"
INTEGRATION_PACKAGE = "performance-manager-rill"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="validate package assembly without Stable evidence or source archive")
    args = parser.parse_args(argv)
    root = Path(args.assets).resolve()
    build = json.loads((root / "build-metadata.json").read_text())
    rill = build.get("externalRuntime") or {}
    final_path = root / "final-stable-evidence.json"
    final = json.loads(final_path.read_text()) if final_path.is_file() else None
    if build.get("repositoryCommitSha") != args.expected_commit:
        raise RuntimeError("build metadata commit mismatch")
    if not args.dry_run:
        if final is None or final.get("pmCommitSha") != args.expected_commit or final.get("overallVerdict") != "PASS" \
                or final.get("stableReleaseAuthorized") is not True:
            raise RuntimeError("Stable evidence is not authorized for the expected commit")
    primary_records = ((build.get("packages") or {}).get(PACKAGE) or {}).get("targets") or []
    primary_sha_values = {record.get("apkSha256") for record in primary_records}
    primary_sha_values.discard(None)
    if len(primary_sha_values) != 1:
        raise RuntimeError("build metadata lacks one stable all-in-one APK identity across targets")
    expected_sha = next(iter(primary_sha_values))
    expected_filename_values = {record.get("apkFilename") for record in primary_records}
    expected_filename_values.discard(None)
    expected_filename = next(iter(expected_filename_values)) if len(expected_filename_values) == 1 else None
    try:
        primary_identity = resolve_artifact(PACKAGE, expected_sha, [root], expected_filename)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    apk = Path(primary_identity["canonicalPath"])
    integration_records = ((build.get("packages") or {}).get(INTEGRATION_PACKAGE) or {}).get("targets") or []
    if not integration_records:
        raise RuntimeError("build metadata lacks performance-manager-rill identity")
    integration_sha_values = {record.get("apkSha256") for record in integration_records}
    integration_filename_values = {record.get("apkFilename") for record in integration_records}
    integration_sha_values.discard(None)
    integration_filename_values.discard(None)
    if len(integration_sha_values) != 1 or len(integration_filename_values) != 1:
        raise RuntimeError("performance-manager-rill identity differs across targets")
    integration_filename = next(iter(integration_filename_values))
    integration_sha = next(iter(integration_sha_values))
    try:
        integration_identity = resolve_artifact(INTEGRATION_PACKAGE, integration_sha, [root], integration_filename)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    integration_apk = Path(integration_identity["canonicalPath"])
    files = [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
             for path in sorted(root.iterdir()) if path.is_file()]
    manifest = {
        "schemaVersion": 1,
        "version": args.version,
        "commit": args.expected_commit,
        "tag": f"v{args.version}",
        "releaseProfile": final.get("releaseProfile", "assembly-dry-run") if final else "assembly-dry-run",
        "hardwareCoverage": final.get("hardwareCoverage", "NOT_RUN") if final else "NOT_RUN",
        "releaseAssemblyDryRun": args.dry_run,
        "stableReleaseAuthorized": (final.get("stableReleaseAuthorized") is True) if final else False,
        "primaryPackage": PACKAGE,
        "primaryPackageSha256": sha256(apk),
        "architectureIndependentPackages": [
            {"package": PACKAGE, "filename": apk.name, "sha256": sha256(apk), "arch": "all"},
            {"package": INTEGRATION_PACKAGE, "filename": integration_apk.name,
             "sha256": sha256(integration_apk), "arch": "all"},
        ],
        "externalRuntime": {
            **(build.get("externalRuntime") or {}),
            "publicReleaseIncluded": False,
            "binary": "/usr/bin/rill-runtime",
        },
        "artifactIdentity": primary_identity,
        "openwrtRelease": build.get("openwrtVersion"),
        "externalRuntime": {
            **(build.get("externalRuntime") or {}),
            "publicReleaseIncluded": False,
            "note": "Provision rill-runtime from hello-yunshu/rill-openwrt-packages; it is not copied into this PM Release.",
        },
        "rill": {
            "releaseVersion": rill.get("rillConsumedVersion"),
            "releaseTag": rill.get("releaseTag"),
            "releaseCommitSha": rill.get("releaseCommitSha"),
        },
        "finalEvidenceSha256": sha256(final_path) if final_path.is_file() else None,
        "sourceZipSha256": sha256(root / f"openwrt-performance-manager-{args.version}.zip") if (root / f"openwrt-performance-manager-{args.version}.zip").is_file() else None,
        "files": files,
    }
    (root / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
