#!/usr/bin/env python3
"""Collect uniquely named Stable evidence files from downloaded run trees."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from aggregate_stable_evidence import PORTABLE_REQUIRED, REQUIRED
from aggregate_build_matrix_evidence import main as aggregate_build_matrix


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-root", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--profile", choices=("hardware", "portable-docker"), default="hardware")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    build_root = Path(args.build_root)
    build_metadata = list(build_root.rglob("build-metadata.json"))
    verification = list(build_root.rglob("apk-verification.json"))
    if len(build_metadata) > 1 or len(verification) > 1:
        matrix_out = out / ".build-matrix"
        aggregate_build_matrix([
            "--input", str(build_root), "--out", str(matrix_out),
            "--expected-commit", args.expected_commit,
            "--expected-arch", "x86_64", "--expected-arch", "aarch64_generic",
        ])
        build_root = matrix_out
    required = PORTABLE_REQUIRED if args.profile == "portable-docker" else REQUIRED
    roots = {
        "source": Path(args.ci_root),
        "coreRuntime": Path(args.ci_root),
        "rillProvenance": Path(args.ci_root),
        "rillRuntime": Path(args.ci_root),
        "rillCoreFunctional": Path(args.ci_root),
        "openwrtSdk": build_root,
        "apkVerification": build_root,
        "packageComposition": Path(args.target_root),
    }
    missing = []
    for name, filename in required.items():
        root = roots.get(name, Path(args.target_root))
        candidates = [path for path in root.rglob(filename) if path.is_file()]
        if not candidates:
            missing.append(filename)
            continue
        hashes = {digest(path) for path in candidates}
        if len(hashes) != 1:
            print(f"FAIL: conflicting copies of {filename}: {candidates}", file=sys.stderr)
            return 1
        shutil.copy2(candidates[0], out / filename)
        print(f"collected {filename} <- {candidates[0]}")
    if missing:
        print("BLOCKED: missing " + ", ".join(missing), file=sys.stderr)
    # Missing inputs are intentionally left for aggregate_stable_evidence.py,
    # which records them as BLOCKED in the authoritative output.
    return 0


if __name__ == "__main__":
    sys.exit(main())
