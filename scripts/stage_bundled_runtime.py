#!/usr/bin/env python3
"""Stage the exact canonical Runtime binary for the full package build.

The input is the APK produced by the checked-out rill-openwrt-packages recipe.
Only its executable payload is copied into the temporary OpenWrt package
workspace; Runtime source ownership stays in the canonical feed repository.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_apks import apk_file_content, apk_pkginfo


ELF_MACHINES = {"x86_64": 62, "aarch64_generic": 183, "aarch64_cortex-a53": 183}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--package-arch", required=True, choices=sorted(ELF_MACHINES))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
        raise SystemExit("--sha256 must be a lowercase SHA-256")
    meta = apk_pkginfo(args.apk) or {}
    if meta.get("pkgname") != "rill-runtime":
        raise SystemExit(f"expected rill-runtime APK, got {meta.get('pkgname')!r}")
    if meta.get("pkgver", "").split("-r", 1)[0] != args.runtime_version:
        raise SystemExit(f"Runtime package version mismatch: {meta.get('pkgver')!r}")
    if meta.get("arch") != args.package_arch:
        raise SystemExit(f"Runtime package arch mismatch: {meta.get('arch')!r}")
    payload = apk_file_content(args.apk, "/usr/bin/rill-runtime")
    if not payload:
        raise SystemExit("canonical Runtime APK has no /usr/bin/rill-runtime payload")
    if sha256_bytes(payload) != args.sha256:
        raise SystemExit("Runtime payload SHA does not match the qualified identity")
    if payload[:4] != b"\x7fELF" or int.from_bytes(payload[18:20], "little") != ELF_MACHINES[args.package_arch]:
        raise SystemExit(f"Runtime ELF machine does not match {args.package_arch}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)
    args.out.chmod(args.out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"STAGED_RILL_RUNTIME={args.out} sha256={sha256_bytes(payload)} arch={args.package_arch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
