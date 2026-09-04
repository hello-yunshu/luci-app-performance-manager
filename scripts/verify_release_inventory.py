#!/usr/bin/env python3
"""Compatibility entry point for the public release whitelist gate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_public_release_assets import verify_public_assets  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--version", required=True)
    # Kept as an accepted identity argument for callers that already pass it;
    # commit/provenance belongs to the private release-evidence inventory.
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-arch", action="append")
    args = parser.parse_args(argv)
    files = verify_public_assets(args.assets.resolve(), args.version,
                                 tuple(args.expected_arch) if args.expected_arch else None
                                 or ("x86_64", "aarch64_generic", "aarch64_cortex-a53"))
    print({"verdict": "PASS", "publicFiles": files})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
