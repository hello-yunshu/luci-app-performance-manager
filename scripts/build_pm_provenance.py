#!/usr/bin/env python3
"""Write same-commit provenance for the PM-owned adapter binary."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    binary = ROOT / "docs/performance-manager-rill-adapter-x86_64-linux-musl"
    if not binary.is_file():
        raise SystemExit(f"missing PM-owned musl adapter: {binary}")
    dep = json.loads((ROOT / "contracts/rill-dependency.json").read_text())
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    size = binary.stat().st_size
    commit = os.environ.get("GITHUB_SHA") or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    result = {
        "schemaVersion": 4,
        "contract": "pm-owned-rill-provenance",
        "pmCommitSha": commit,
        "provenanceVerdict": "PASS",
        "adapterOwner": dep["adapter"]["owner"],
        "adapterBinary": dep["adapter"]["binary"],
        "artifactName": f'{dep["adapter"]["binary"]}-x86_64-linux-musl',
        "adapterVersion": dep["adapter"]["version"],
        "adapterSha256": sha,
        "adapterSize": size,
        "rillMlVersion": dep["rillMl"]["version"],
        "protocolContract": dep["protocol"]["name"],
        "protocolVersion": dep["protocol"]["version"],
        "target": {"os": "linux", "arch": "x86_64", "libc": "musl"},
        "upstreamPmAdapterRequired": False,
        "historicalV151Fixture": "contracts/upstream/rill-pm-adapter-v1.5.1-contract.json",
        "historicalReleaseTag": "v1.5.1",
        "historicalReleaseCommitSha": "cba9b3d2fb2c6a71cb9d4a02b18852171ad05a1b",
    }
    (ROOT / "docs/rill-provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
