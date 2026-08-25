#!/usr/bin/env python3
"""Generate the PM-owned adapter consumption manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commit() -> str:
    return os.environ.get("GITHUB_SHA") or subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "rill-consumed-manifest.json"))
    args = parser.parse_args()
    dep = json.loads((ROOT / "contracts/rill-dependency.json").read_text())
    adapter = dep["adapter"]
    rill = dep["rillMl"]
    manifest = {
        "schemaVersion": 3,
        "contract": "pm-owned-rill-consumption",
        "pmCommitSha": commit(),
        "pmVersion": (ROOT / "VERSION").read_text().strip(),
        "adapterOwner": adapter["owner"],
        "adapterBinary": adapter["binary"],
        "adapterVersion": adapter["version"],
        "adapterInstallPath": adapter["canonicalPath"],
        "rillMlPackage": rill["package"],
        "rillMlRegistry": rill["registry"],
        "rillMlVersion": rill["version"],
        "rillMlResolution": rill["resolution"],
        "protocolContract": dep["protocol"]["name"],
        "protocolVersion": dep["protocol"]["version"],
        "stateSchemaVersion": dep["state"]["schemaVersion"],
        "artifactName": f'{adapter["binary"]}-x86_64-linux-musl',
        "artifactSha256": None,
        "artifactSize": None,
        "status": "pm-owned",
        "upstreamPmAdapterRequired": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalV151Fixture": "contracts/upstream/rill-pm-adapter-v1.5.1-contract.json",
        "historicalReleaseTag": "v1.5.1",
        "historicalReleaseCommitSha": "cba9b3d2fb2c6a71cb9d4a02b18852171ad05a1b",
    }
    binary = ROOT / "package/performance-manager-rill-adapter/files/usr/sbin/performance-manager-rill-adapter"
    if binary.exists():
        manifest["artifactSha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        manifest["artifactSize"] = binary.stat().st_size
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
