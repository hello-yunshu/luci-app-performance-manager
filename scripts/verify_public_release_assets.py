#!/usr/bin/env python3
"""Fail-closed whitelist for the user-facing GitHub Release inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TARGETS = json.loads((Path(__file__).resolve().parents[1] / "contracts/openwrt-native-targets.json").read_text())["targets"]
ARCHES = tuple(row["packageArch"] for row in TARGETS)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_public_assets(root: Path, version: str, expected_arches=None) -> list[str]:
    targets = TARGETS
    if expected_arches:
        targets = [row for row in TARGETS if row["packageArch"] in expected_arches]
    expected = {
        f"performance-manager-all-v{version}-openwrt-{row['openwrtVersion']}-{row['packageArch']}.{row['packageManagerFormat']}"
        for row in targets
    }
    files = {path.name for path in root.iterdir() if path.is_file()}
    actual_packages = {name for name in files if name.endswith((".apk", ".ipk"))}
    if files != expected | {"SHA256SUMS.txt"}:
        raise RuntimeError(f"public asset whitelist mismatch: expected {sorted(expected | {'SHA256SUMS.txt'})}, got {sorted(files)}")
    if actual_packages != expected or len(actual_packages) != len(targets):
        raise RuntimeError(f"public inventory must contain exactly {len(targets)} target-specific PM packages")
    checksum = root / "SHA256SUMS.txt"
    lines = checksum.read_text().splitlines()
    if len(lines) != len(targets):
        raise RuntimeError(f"SHA256SUMS.txt must contain exactly {len(targets)} PM package entries")
    seen = set()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+\.(?:apk|ipk))", line)
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
