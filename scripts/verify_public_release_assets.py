#!/usr/bin/env python3
"""Fail-closed whitelist for the user-facing GitHub Release inventory."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


ARCHES = ("x86_64", "aarch64_generic", "aarch64_cortex-a53")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_public_assets(root: Path, version: str, expected_arches=ARCHES) -> list[str]:
    expected = {f"performance-manager-all-v{version}-{arch}.apk" for arch in expected_arches}
    files = {path.name for path in root.iterdir() if path.is_file()}
    actual_apks = {name for name in files if name.endswith(".apk")}
    if files != expected | {"SHA256SUMS.txt"}:
        raise RuntimeError(f"public asset whitelist mismatch: expected {sorted(expected | {'SHA256SUMS.txt'})}, got {sorted(files)}")
    if actual_apks != expected or len(actual_apks) != 3:
        raise RuntimeError("public inventory must contain exactly three architecture-specific full APKs")
    checksum = root / "SHA256SUMS.txt"
    lines = checksum.read_text().splitlines()
    if len(lines) != 3:
        raise RuntimeError("SHA256SUMS.txt must contain exactly three APK entries")
    seen = set()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+\.apk)", line)
        if not match or match.group(2) not in expected or match.group(2) in seen:
            raise RuntimeError(f"invalid checksum entry: {line!r}")
        if match.group(1) != digest(root / match.group(2)):
            raise RuntimeError(f"checksum mismatch: {match.group(2)}")
        seen.add(match.group(2))
    if seen != expected:
        raise RuntimeError("SHA256SUMS.txt does not cover all public APKs")
    return sorted(files)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    files = verify_public_assets(args.assets.resolve(), args.version)
    print(f"PASS: public release whitelist ({', '.join(files)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
