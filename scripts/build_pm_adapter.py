#!/usr/bin/env python3
"""Build and stage the PM-owned native adapter for OpenWrt packaging."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integrations/performance-manager-rill-adapter/Cargo.toml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="x86_64-unknown-linux-musl")
    parser.add_argument("--profile", default="release")
    args = parser.parse_args()
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(MANIFEST),
            "--locked",
            "--target",
            args.target,
            "--profile",
            args.profile,
        ],
        cwd=ROOT,
        check=True,
    )
    source = MANIFEST.parent / "target" / args.target / args.profile / "performance-manager-rill-adapter"
    destination = ROOT / "package/performance-manager-rill-adapter/files/usr/sbin/performance-manager-rill-adapter"
    if not source.is_file():
        raise SystemExit(f"missing adapter binary: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    destination.chmod(0o755)
    print(f"staged {destination} from {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
