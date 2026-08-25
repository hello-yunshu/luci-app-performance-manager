#!/usr/bin/env python3
"""Fail closed on forbidden GitHub Actions ref forms."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA_REF = re.compile(r"uses:\s*([^\s#]+)@([0-9a-fA-F]{40})(?:\s|$)")
FORBIDDEN = re.compile(r"uses:\s*([^\s#]+)@(latest|HEAD|main)(?:\s|$)")


def main() -> int:
    failures: list[str] = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SHA_REF.search(line) or FORBIDDEN.search(line):
                failures.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    if failures:
        print("FAIL: forbidden GitHub Actions refs")
        print("\n".join(failures))
        return 1
    print("PASS: all GitHub Actions refs are readable and non-dynamic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
