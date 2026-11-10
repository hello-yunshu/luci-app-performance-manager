#!/usr/bin/env python3
"""Create private release evidence for an already-whitelisted public set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_identity import sha256
from verify_public_release_assets import verify_public_assets


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, help="release-public directory")
    parser.add_argument("--input", help="private input artifacts containing build evidence")
    parser.add_argument("--evidence-dir", help="private release-evidence output directory")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    public = Path(args.assets).resolve()
    files = verify_public_assets(public, args.version)
    evidence = Path(args.evidence_dir or args.assets).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    input_root = Path(args.input).resolve() if args.input else evidence
    metadata_paths = sorted(p for p in input_root.rglob("build-metadata.json") if p.is_file())
    if len(metadata_paths) != 3:
        raise RuntimeError(f"expected three target build metadata records, found {metadata_paths}")
    metadata = json.loads(metadata_paths[0].read_text())
    if metadata.get("repositoryCommitSha") != args.expected_commit:
        raise RuntimeError("build metadata commit mismatch")
    targets = []
    for path in sorted(input_root.rglob("build-metadata.json")):
        build = json.loads(path.read_text())
        if build.get("repositoryCommitSha") != args.expected_commit:
            raise RuntimeError(f"target build commit mismatch: {path}")
        targets.append({
            "packageArch": build.get("architecture"), "target": build.get("target"),
            "openwrtVersion": build.get("openwrtVersion"), "sdkIdentity": build.get("sdkIdentity"),
            "sdkArchiveSha256": build.get("sdkArchiveSha256"),
            "fullPackage": build.get("fullPackage"),
        })
    if len(targets) != 3:
        raise RuntimeError(f"expected three target build evidence records, found {len(targets)}")
    first = metadata.get("externalRuntime") or {}
    manifest = {
        "schemaVersion": 2,
        "version": args.version,
        "commit": args.expected_commit,
        "tag": f"v{args.version}",
        "releaseAssemblyDryRun": args.dry_run,
        "stableReleaseAuthorized": False,
        "hardwareCoverage": "NOT_EVALUATED",
        "publicAssets": [{"name": name, "sha256": sha256(public / name), "bytes": (public / name).stat().st_size}
                         for name in files],
        "targets": targets,
        "externalRuntime": {
            **first,
            "package": "rill-runtime",
            "repository": "hello-yunshu/rill-openwrt-packages",
            "bundledInFullAllInOne": True,
            "standalonePublicReleaseIncluded": False,
        },
    }
    output = evidence / "release-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verdict": "PASS", "output": str(output), "publicFiles": files}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
