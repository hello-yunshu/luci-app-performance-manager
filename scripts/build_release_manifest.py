#!/usr/bin/env python3
"""Build the public release manifest from one exact verified APK identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"
ADAPTER_PACKAGE = "performance-manager-rill-adapter"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    root = Path(args.assets).resolve()
    build = json.loads((root / "build-metadata.json").read_text())
    rill = json.loads((root / "rill-consumed-manifest.json").read_text())
    final = json.loads((root / "final-stable-evidence.json").read_text())
    if build.get("repositoryCommitSha") != args.expected_commit:
        raise RuntimeError("build metadata commit mismatch")
    if final.get("pmCommitSha") != args.expected_commit or final.get("overallVerdict") != "PASS" \
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
    adapter_build = (build.get("packages") or {}).get(ADAPTER_PACKAGE) or {}
    adapter_records = adapter_build.get("targets") or []
    if not adapter_records:
        raise RuntimeError("build metadata lacks target-specific adapter identities")
    adapter_identities = []
    for record in adapter_records:
        adapter_expected = record.get("apkSha256")
        adapter_filename = record.get("releaseFilename") or record.get("apkFilename")
        if not adapter_expected or not adapter_filename:
            raise RuntimeError("build metadata lacks an exact target-specific adapter identity")
        try:
            adapter_identity = resolve_artifact(ADAPTER_PACKAGE, adapter_expected, [root], adapter_filename)
        except ArtifactIdentityError as exc:
            raise RuntimeError(str(exc)) from exc
        adapter_identities.append({
            "packageArch": record.get("packageArch"),
            "target": record.get("target"),
            "openwrtVersion": record.get("openwrtVersion"),
            "releaseFilename": record.get("releaseFilename") or adapter_filename,
            "sha256": sha256(Path(adapter_identity["canonicalPath"])),
            "identity": adapter_identity,
        })
    files = [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
             for path in sorted(root.iterdir()) if path.is_file()]
    manifest = {
        "schemaVersion": 1,
        "version": args.version,
        "commit": args.expected_commit,
        "tag": f"v{args.version}",
        "releaseProfile": final.get("releaseProfile", "hardware"),
        "hardwareCoverage": final.get("hardwareCoverage", "REQUIRED"),
        "primaryPackage": PACKAGE,
        "primaryPackageSha256": sha256(apk),
        "adapterPackage": ADAPTER_PACKAGE,
        "adapterPackageSha256": adapter_identities[0]["sha256"],
        "adapterPackageSha256s": [item["sha256"] for item in adapter_identities],
        "adapterArtifacts": adapter_identities,
        "artifactIdentity": primary_identity,
        "openwrtRelease": build.get("openwrtVersion"),
        "sdkArchiveSha256": build.get("sdkArchiveSha256"),
        "rill": {
            "releaseVersion": rill.get("rillMlVersion") or rill.get("releaseVersion"),
            "releaseTag": rill.get("releaseTag") or rill.get("historicalReleaseTag"),
            "releaseCommitSha": rill.get("releaseCommitSha") or rill.get("historicalReleaseCommitSha"),
            "artifactSha256": rill.get("artifactSha256") or rill.get("adapterSha256"),
            "adapterOwner": rill.get("adapterOwner"),
            "adapterVersion": rill.get("adapterVersion"),
        },
        "finalEvidenceSha256": sha256(root / "final-stable-evidence.json"),
        "sourceZipSha256": sha256(root / f"openwrt-performance-manager-{args.version}.zip"),
        "files": files,
    }
    (root / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
