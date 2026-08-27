#!/usr/bin/env python3
"""Static PM-owned adapter, protocol, package, and fail-closed contract gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()
INIT = (ROOT / "package/performance-manager-rill/files/etc/init.d/performance-manager-rill").read_text()
RILL_MAKE = (ROOT / "package/performance-manager-rill/Makefile").read_text()
ADAPTER_MANIFEST = (ROOT / "integrations/performance-manager-rill-adapter/Cargo.toml").read_text()
DEP = json.loads((ROOT / "contracts/rill-dependency.json").read_text())
SCHEMA = json.loads((ROOT / "contracts/rill-ipc.schema.json").read_text())

checks: list[tuple[str, bool]] = []


def check(name: str, value: bool) -> None:
    checks.append((name, bool(value)))
    if not value:
        print("FAIL:", name)


def branch_props(op: str) -> dict:
    return SCHEMA["$defs"][f"{op}Request"]["properties"]


ops = {branch_props(op)["op"]["const"] for op in ("status", "observe", "outcome")}
check("schema contract const==pm-rill-shadow", branch_props("status")["contract"]["const"] == "pm-rill-shadow")
check("schema protocolVersion const==1", branch_props("status")["protocolVersion"]["const"] == 1)
check("dependency contract name", DEP["contract"] == "pm-rill-dependency")
check("dependency protocol owner", DEP["protocol"]["owner"] == "OpenWrt Performance Manager")
check("dependency protocol name/version", DEP["protocol"]["name"] == "pm-rill-shadow" and DEP["protocol"]["version"] == 1)
check("required operations match schema", set(DEP["protocol"]["requiredOps"]) == ops == {"status", "observe", "outcome"})
check("context key bounds match schema", DEP["protocol"]["contextKeyPattern"] == "^ctx-v1:" and DEP["protocol"]["contextKeyMaxLength"] == 512)
check("Core shadow protocol wiring", "const RILL_CONTRACT = 'pm-rill-shadow'" in CORE and "const RILL_PROTOCOL_VERSION = 1" in CORE)
check("Core exact linked versions", "RILL_LINKED_RILL_ML_VERSION = '1.5.3'" in CORE and "RILL_PINNED_ADAPTER_VERSION = '1.0.3'" in CORE)
check("Core fail-closed tokens", all(token in CORE for token in ("binary-invalid", "external-runtime-not-provisioned", "protocol-version-mismatch", "contract-mismatch", "missing-required-capability")))
check("Core canonical binary resolver", "/usr/sbin/performance-manager-rill-adapter" in CORE and "/usr/bin/performance-manager-rill-adapter" in CORE)
check("init canonical binary resolver", "/usr/sbin/performance-manager-rill-adapter" in INIT and "/usr/bin/performance-manager-rill-adapter" in INIT and "resolve_binary()" in INIT)
check("explicit binary fails closed", "source: 'explicit'" in CORE and "BINARY_STATE='binary-invalid'" in INIT)
adapter_dependency = next((line for line in ADAPTER_MANIFEST.splitlines() if line.strip().startswith("rill-ml =")), "")
check("PM adapter exact registry dependency", 'version = "=1.5.3"' in adapter_dependency and "git" not in adapter_dependency and "path" not in adapter_dependency)
check("PM adapter binary/package identity", DEP["adapter"]["owner"] == "hello-yunshu/luci-app-performance-manager" and DEP["adapter"]["binary"] == "performance-manager-rill-adapter" and DEP["adapter"]["version"] == "1.0.3")
check("RillML exact dependency identity", DEP["rillMl"] == {"package": "rill-ml", "registry": "crates.io", "version": "1.5.3", "resolution": "exact", "features": ["serde"]})
check("RillML exact release identity", DEP["rillRelease"] == {"tag": "v1.5.3", "commit": "621ed42bf6a4ea29b19f45a5dfa75f50f68173a9", "stableIndexSha256": "05b73e70ab4a58e2bf3f7e4b4ae1487b9e3a56cb9e2cea80a2730ca84ac52dde"})
check("integration package owns adapter", "+performance-manager-rill-adapter" in RILL_MAKE and "rill-pm-adapter" not in RILL_MAKE)
check("historical upstream fixture retained", (ROOT / "contracts/upstream/rill-pm-adapter-v1.5.1-contract.json").exists())
check("state path/schema contract", DEP["state"]["directory"] == "/etc/performance-manager/rill" and DEP["state"]["schemaVersion"] == 1)
check("advisory-only authority", DEP["security"]["authority"] == "advisory-only" and DEP["security"]["hostMutation"] is False)

ok = all(value for _, value in checks)
status = {
    "schemaVersion": 4,
    "contract": "rill-integration-status",
    "scope": "PM-owned adapter and pm-rill-shadow v1 static contract",
    "staticContractVerdict": "PASS" if ok else "FAIL",
    "functionalIntegrationVerdict": "NOT_EVALUATED",
    "upstreamReleaseVerification": "current rill-ml identity is contract-pinned; historical adapter fixture separately verified",
    "adapterOwner": DEP["adapter"]["owner"],
    "adapterBinary": DEP["adapter"]["binary"],
    "rillMlVersion": DEP["rillMl"]["version"],
    "checks": [{"name": name, "ok": value} for name, value in checks],
}
(ROOT / "docs/rill-integration-status.json").write_text(json.dumps(status, indent=2) + "\n")
print(f"rill-contract (PM-owned static): {sum(value for _, value in checks)}/{len(checks)} checks passed; staticContractVerdict={'PASS' if ok else 'FAIL'}")
if not ok:
    sys.exit(1)
