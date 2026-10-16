#!/usr/bin/env python3
"""Validate the PM consumer contract for the external generic Rill Runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from check_rill_dependency import check_data

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
    contract_errors = check_data(contract, None)
    for error in contract_errors:
        print(f"FAIL: pinned Runtime contract: {error}")
    checks = [
        ("canonical pinned Runtime contract", not contract_errors),
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
