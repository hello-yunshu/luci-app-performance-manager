#!/usr/bin/env python3
"""Fail-closed validation of the assembled PM public package inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-arch", action="append", required=True)
    args = parser.parse_args()
    root = Path(args.assets).resolve()
    manifest = json.loads((root / "release-manifest.json").read_text())
    build = json.loads((root / "build-metadata.json").read_text())
    if manifest.get("commit") != args.expected_commit or not manifest.get("releaseAssemblyDryRun"):
        raise RuntimeError("dry-run manifest identity or mode mismatch")
    if manifest.get("stableReleaseAuthorized", False):
        raise RuntimeError("dry-run must never authorize Stable release")
    independent = manifest.get("architectureIndependentPackages") or []
    names = [item.get("package") for item in independent]
    if names != ["luci-app-performance-manager-all", "performance-manager-rill"]:
        raise RuntimeError(f"unexpected architecture-independent inventory: {names!r}")
    for item in independent:
        path = root / item["filename"]
        if not path.is_file() or digest(path) != item["sha256"] or item.get("arch") != "all":
            raise RuntimeError(f"invalid architecture-independent asset: {item}")
    targets = manifest.get("nativeTargets") or []
    expected = {
        "x86_64": ("x86/64", "x86_64-unknown-linux-musl"),
        "aarch64_generic": ("armsr/armv8", "aarch64-unknown-linux-musl"),
        "aarch64_cortex-a53": ("mediatek/filogic", "aarch64-unknown-linux-musl"),
    }
    if set(args.expected_arch) != set(expected) or {item.get("packageArch") for item in targets} != set(expected):
        raise RuntimeError("native architecture coverage mismatch")
    filenames = []
    for item in targets:
        arch = item.get("packageArch")
        if (item.get("target"), item.get("rustTarget")) != expected[arch]:
            raise RuntimeError(f"native target mapping mismatch: {item}")
        if not item.get("sdkIdentity") or not isinstance(item.get("sdkArchiveSha256"), str) \
                or len(item["sdkArchiveSha256"]) != 64:
            raise RuntimeError(f"native SDK provenance is incomplete: {item}")
        path = root / item["releaseFilename"]
        if not path.is_file() or digest(path) != item["sha256"]:
            raise RuntimeError(f"invalid native asset: {item}")
        filenames.append(path.name)
    if len(filenames) != len(set(filenames)):
        raise RuntimeError("duplicate native release filenames")
    if any(path.name.startswith("rill-runtime") for path in root.iterdir() if path.is_file()):
        raise RuntimeError("rill-runtime must not be copied into PM Release")
    if build.get("repositoryCommitSha") != args.expected_commit:
        raise RuntimeError("assembled build metadata commit mismatch")
    runtime = manifest.get("externalRuntime") or {}
    if runtime.get("package") != "rill-runtime" or runtime.get("repository") != "hello-yunshu/rill-openwrt-packages" \
            or not runtime.get("commit") or runtime.get("qualificationArtifact") != "qualification-evidence" \
            or runtime.get("publicReleaseIncluded") is not False:
        raise RuntimeError("external rill-runtime provenance or ownership is incomplete")
    print(json.dumps({"verdict": "PASS", "architectureIndependent": names,
                      "nativeArchitectures": sorted(expected), "rillRuntimeIncluded": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
