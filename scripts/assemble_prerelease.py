#!/usr/bin/env python3
"""Assemble a prerelease with the same four-file public inventory as Stable."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble_public_release import PACKAGE, TARGETS, assemble_public_apk, read_one_json  # noqa: E402
from artifact_identity import ArtifactIdentityError  # noqa: E402
from verify_public_release_assets import verify_public_assets  # noqa: E402


def artifact_roots(root: Path, suffix: str) -> list[Path]:
    matches = sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith(suffix))
    if not matches:
        raise RuntimeError(f"expected an artifact root ending {suffix!r}")
    return matches


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source-dist", help="accepted for CLI compatibility; source archives stay private")
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    input_root = Path(args.input).resolve()
    output = Path(args.out).resolve()
    dedicated = artifact_roots(input_root, "-all-in-one-apk")
    artifact_roots(input_root, "-packages-and-evidence")
    final_roots = artifact_roots(input_root, "final-release-evidence-build")
    if len(dedicated) != len(TARGETS) or len(final_roots) != 1:
        raise RuntimeError("prerelease requires three dedicated full APK artifacts and one final evidence artifact")
    for root in dedicated:
        _, manifest = read_one_json(root, "all-in-one-release-manifest.json")
        if manifest.get("pmCommitSha") != args.expected_sha or manifest.get("package") != PACKAGE:
            raise RuntimeError("all-in-one manifest identity mismatch")
    _, final = read_one_json(final_roots[0], "final-release-evidence.json")
    if final.get("overallVerdict") != "PASS" or final.get("expectedCommitSha") != args.expected_sha:
        raise RuntimeError("final build evidence verdict or commit mismatch")
    try:
        result = assemble_public_apk(input_root=input_root, output_root=output,
                                     expected_commit=args.expected_sha, version=args.version)
    except ArtifactIdentityError as exc:
        raise RuntimeError(str(exc)) from exc
    files = verify_public_assets(output, args.version)
    print(json.dumps({"package": PACKAGE, "commit": args.expected_sha, "assets": files,
                      "portableValidated": True, "hardwareStable": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
