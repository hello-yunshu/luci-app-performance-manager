#!/usr/bin/env python3
"""Validate the PM consumer contract for the external generic Rill Runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from check_rill_dependency import SHA1, check_data

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()
RILL_MAKE = (ROOT / "package/performance-manager-rill/Makefile").read_text()
CONTRACT = ROOT / "contracts/rill-runtime.json"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def release_pin_structure(contract: dict) -> tuple[str, list[dict]]:
    """Check that the pin is structurally complete and independently readable.

    The final release evidence must be auditable without trusting a CI log, so
    every identity field the aggregator copies out is validated here first.
    """
    resolved = contract.get("resolved", {})
    package = contract.get("openwrtPackage", {})
    qualification = contract.get("qualification", {})
    checks = [
        ("schemaVersion is 1", contract.get("schemaVersion") == 1),
        ("package commit is a 40-hex SHA-1", bool(SHA1.fullmatch(str(package.get("commit", ""))))),
        ("package release is a positive integer",
         type(package.get("packageRelease")) is int and package.get("packageRelease") > 0),
        ("qualification runId is a positive integer and verdict is PASS",
         type(qualification.get("runId")) is int and qualification.get("runId") > 0
         and qualification.get("verdict") == "PASS"),
        ("upstream commit is a 40-hex SHA-1", bool(SHA1.fullmatch(str(resolved.get("upstreamCommit", ""))))),
    ]
    verdict = "PASS" if all(ok for _, ok in checks) else "FAIL"
    return verdict, [{"name": name, "ok": ok} for name, ok in checks]


def main() -> int:
    if not CONTRACT.is_file():
        fail("contracts/rill-runtime.json is missing")
    contract = json.loads(CONTRACT.read_text())
    resolved = contract.get("resolved", {})
    package = contract.get("openwrtPackage", {})
    qualification = contract.get("qualification", {})
    version = resolved.get("version", "")
    contract_errors = check_data(contract, None)
    for error in contract_errors:
        print(f"FAIL: pinned Runtime contract: {error}")
    pin_verdict, pin_checks = release_pin_structure(contract)
    for check in pin_checks:
        if not check["ok"]:
            print(f"FAIL: release pin structure: {check['name']}")
    checks = [
        ("canonical pinned Runtime contract", not contract_errors),
        ("release pin structure", pin_verdict == "PASS"),
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
        "releasePinStructureVerdict": pin_verdict,
        "releasePin": {
            "source": "contracts/rill-runtime.json",
            "schemaVersion": contract.get("schemaVersion"),
            "commit": package.get("commit"),
            "packageRelease": package.get("packageRelease"),
            "qualification": {"runId": qualification.get("runId"), "verdict": qualification.get("verdict")},
            "upstreamCommit": resolved.get("upstreamCommit"),
            "resolvedVersion": version,
        },
        "releasePinChecks": pin_checks,
        "functionalIntegrationVerdict": "NOT_EVALUATED",
        "resolvedRuntime": resolved,
        "openwrtPackage": package,
        "qualification": qualification,
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
    }
    (ROOT / "docs/rill-integration-status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(f"rill-contract (external Runtime v3): {passed}/{len(checks)} checks passed; "
          f"staticContractVerdict={verdict}; releasePinStructureVerdict={pin_verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
