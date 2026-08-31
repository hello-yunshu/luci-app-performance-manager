#!/usr/bin/env python3
"""Validate the PM consumer contract for the external generic Rill Runtime."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()
RILL_MAKE = (ROOT / "package/performance-manager-rill/Makefile").read_text()
CONTRACT = ROOT / "contracts/rill-runtime.json"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    if not CONTRACT.is_file():
        fail("contracts/rill-runtime.json is missing")
    contract = json.loads(CONTRACT.read_text())
    resolved = contract.get("resolved", {})
    package = contract.get("openwrtPackage", {})
    qualification = contract.get("qualification", {})
    version = resolved.get("version", "")
    checks = [
        ("schemaVersion", contract.get("schemaVersion") == 1),
        ("stable policy", contract.get("policy") == {"major": 1, "track": "latest-qualified-stable"}),
        ("resolved semver", bool(re.fullmatch(r"1\.[0-9]+\.[0-9]+", version))),
        ("resolved tag", resolved.get("tag") == f"v{version}"),
        ("resolved commit", bool(re.fullmatch(r"[0-9a-f]{40}", resolved.get("upstreamCommit", "")))),
        ("resolved archive hash", bool(re.fullmatch(r"[0-9a-f]{64}", resolved.get("sourceArchiveSha256", "")))),
        ("package repository", package.get("repository") == "hello-yunshu/rill-openwrt-packages"),
        ("package commit", bool(re.fullmatch(r"[0-9a-f]{40}", package.get("commit", "")))),
        ("package identity", package.get("package") == "rill-runtime" and package.get("packageVersion") == version and package.get("packageRelease") == 1),
        ("canonical binary", package.get("binary") == "/usr/bin/rill-runtime"),
        ("qualification required", qualification.get("required") is True and qualification.get("verdict") == "PASS"),
        ("qualification run", bool(re.fullmatch(r"[0-9]+", str(qualification.get("runId", ""))))),
        ("consumer dependency", "+rill-runtime" in RILL_MAKE and "performance-manager-rill-adapter" not in RILL_MAKE),
        ("core v3", "const RILL_RUNTIME_API_VERSION = 3" in CORE and "/usr/bin/rill-runtime" in CORE),
        ("core exact version", f"const RILL_RESOLVED_VERSION = '{version}'" in CORE),
        ("no legacy resolver", all(token not in CORE for token in ("performance-manager-rill-adapter", "rill-pm-adapter"))),
    ]
    for name, ok in checks:
        if not ok:
            print(f"FAIL: {name}")
    passed = sum(ok for _, ok in checks)
    verdict = "PASS" if passed == len(checks) else "FAIL"
    status = {
        "schemaVersion": 1,
        "contract": "rill-integration-status",
        "scope": "PM consumer of external generic Rill Runtime v3",
        "staticContractVerdict": verdict,
        "functionalIntegrationVerdict": "NOT_EVALUATED",
        "resolvedRuntime": resolved,
        "openwrtPackage": package,
        "qualification": qualification,
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
    }
    (ROOT / "docs/rill-integration-status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(f"rill-contract (external Runtime v3): {passed}/{len(checks)} checks passed; staticContractVerdict={verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
