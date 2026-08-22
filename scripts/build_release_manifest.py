#!/usr/bin/env python3
"""Build the public release manifest from one exact verified APK identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"


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
    expected_sha = ((build.get("packages") or {}).get(PACKAGE) or {}).get("apkSha256")
    expected_filename = ((build.get("packages") or {}).get(PACKAGE) or {}).get("apkFilename")
    try:
        identity = resolve_artifact(PACKAGE, expected_sha, [root], expected_filename)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    apk = Path(identity["canonicalPath"])
    files = [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
             for path in sorted(root.iterdir()) if path.is_file()]
    manifest = {
        "schemaVersion": 1,
        "version": args.version,
        "commit": args.expected_commit,
        "tag": f"v{args.version}",
        "primaryPackage": PACKAGE,
        "primaryPackageSha256": sha256(apk),
        "artifactIdentity": identity,
        "openwrtRelease": build.get("openwrtVersion"),
        "sdkArchiveSha256": build.get("sdkArchiveSha256"),
        "rill": {
            "releaseVersion": rill.get("releaseVersion"),
            "releaseTag": rill.get("releaseTag"),
            "releaseCommitSha": rill.get("releaseCommitSha"),
            "artifactSha256": rill.get("artifactSha256"),
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
