#!/usr/bin/env python3
"""Assemble a prerelease using the shared exact artifact identity resolver."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_identity import ArtifactIdentityError, sha256  # noqa: E402
from assemble_public_release import PACKAGE, assemble_public_apk, read_one_json  # noqa: E402


def artifact_root(root: Path, suffix: str) -> Path:
    matches = [path for path in root.iterdir() if path.is_dir() and path.name.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one artifact root ending {suffix!r}, found {matches}")
    return matches[0]


def artifact_roots(root: Path, suffix: str) -> list[Path]:
    matches = sorted(path for path in root.iterdir() if path.is_dir() and path.name.endswith(suffix))
    if not matches:
        raise RuntimeError(f"expected an artifact root ending {suffix!r}")
    return matches


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
    dedicated = artifact_roots(input_root, "-all-in-one-apk")[0]
    artifact_roots(input_root, "-packages-and-evidence")
    final_root = artifact_root(input_root, "final-release-evidence-build")

    _, manifest = read_one_json(dedicated, "all-in-one-release-manifest.json")
    _, final = read_one_json(final_root, "final-release-evidence.json")
    if manifest.get("pmCommitSha") != args.expected_sha or manifest.get("package") != PACKAGE:
        raise RuntimeError("all-in-one manifest identity mismatch")
    if final.get("overallVerdict") != "PASS" or final.get("expectedCommitSha") != args.expected_sha:
        raise RuntimeError("final build evidence verdict or commit mismatch")

    try:
        identity = assemble_public_apk(input_root=input_root, output_root=output,
                                       expected_commit=args.expected_sha)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    apk = Path(identity["canonicalPath"])

    source_zip = source_dist / f"openwrt-performance-manager-{args.version}.zip"
    source_manifest = source_dist / f"openwrt-performance-manager-{args.version}.manifest.json"
    for path in (source_zip, source_manifest):
        if not path.is_file():
            raise RuntimeError(f"source artifact missing: {path}")

    output.mkdir(parents=True, exist_ok=True)
    owned = {
        "all-in-one-checksums.txt": dedicated / "all-in-one-checksums.txt",
        "final-release-evidence.json": next(path for path in final_root.rglob("final-release-evidence.json") if path.is_file()),
        "FINAL_AUDIT.json": next(path for path in input_root.rglob("FINAL_AUDIT.json") if path.is_file()),
        "FINAL_AUDIT.md": next(path for path in input_root.rglob("FINAL_AUDIT.md") if path.is_file()),
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
    print(json.dumps({"package": PACKAGE, "apk": apk.name, "sha256": sha256(apk),
                      "copies": identity["copies"], "commit": args.expected_sha,
                      "assets": len(owned) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
