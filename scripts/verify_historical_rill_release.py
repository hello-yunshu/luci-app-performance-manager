#!/usr/bin/env python3
"""Verify the immutable v1.5.1 upstream adapter snapshot as historical input."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    fixture = ROOT / "contracts/upstream/rill-pm-adapter-v1.5.1-contract.json"
    if not fixture.is_file():
        raise SystemExit("FAIL: immutable v1.5.1 upstream fixture missing")
    data = json.loads(fixture.read_text())
    required = {
        "releaseTag": "v1.5.1",
        "releaseCommitSha": "cba9b3d2fb2c6a71cb9d4a02b18852171ad05a1b",
        "contract": "pm-rill-shadow",
        "protocolVersion": 1,
    }
    for key, value in required.items():
        if data.get(key) != value:
            raise SystemExit(f"FAIL: historical fixture {key}={data.get(key)!r} != {value!r}")
    print("PASS: immutable RillML v1.5.1 adapter fixture retained for historical verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
