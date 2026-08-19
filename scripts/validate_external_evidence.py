#!/usr/bin/env python3
"""Validate a self-hosted target/testbed evidence envelope."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "contracts/rill-dependency.json").read_text())["upstream"]["adapter"]["sha256"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--require-rill", action="store_true")
    parser.add_argument("--minimum-duration", type=int, default=0)
    args = parser.parse_args(argv)
    data = json.loads(Path(args.file).read_text())
    errors = []
    if data.get("gate") != args.gate:
        errors.append(f"gate={data.get('gate')!r}")
    if data.get("pmCommitSha") != args.expected_commit:
        errors.append(f"pmCommitSha={data.get('pmCommitSha')!r}")
    if str(data.get("verdict", "")).upper() != "PASS" or data.get("passed") is not True:
        errors.append(f"verdict={data.get('verdict')!r} passed={data.get('passed')!r}")
    if args.require_rill and data.get("adapterSha256") != PIN:
        errors.append(f"adapterSha256={data.get('adapterSha256')!r}")
    if int(data.get("durationSeconds", 0)) < args.minimum_duration:
        errors.append(f"durationSeconds={data.get('durationSeconds')!r}")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: {args.gate} commit={args.expected_commit} adapter={data.get('adapterSha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
