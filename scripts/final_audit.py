#!/usr/bin/env python3
"""Source-only audit orchestrator.

This audit deliberately cannot promote runtime, hardware, soak, sysupgrade, or
Stable release status. It reruns local structural and model-level gates and
writes a source-candidate report. Only ``final_release_audit.py`` may combine
same-commit external evidence into a Stable decision.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()


def git_commit() -> str:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if dirty.returncode != 0 or dirty.stdout.strip():
        return "WORKTREE_UNCOMMITTED"
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.run(command, cwd=ROOT, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


steps = []


def step(name, command, evidence_class="source"):
    completed = run(command)
    steps.append({
        "name": name,
        "evidenceClass": evidence_class,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "outputTail": completed.stdout[-4000:],
    })
    return completed


unit = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
match = re.search(r"Ran (\d+) tests?", unit.stdout)
tests = {
    "status": "PASS" if unit.returncode == 0 else "FAIL",
    "count": int(match.group(1)) if match else None,
    "outputTail": unit.stdout[-4000:],
}
step("contract-validation", [sys.executable, "scripts/validate_contracts.py"])
step("host-syntax", [sys.executable, "scripts/host_syntax_check.py"])
step("source-gates", [sys.executable, "scripts/source_gates.py"])
step("rill-static-contract", [sys.executable, "scripts/rill_contract_check.py"])
step("resource-budget", [sys.executable, "scripts/resource_budget.py", "--source-tree", "."])

host = json.loads((ROOT / "docs/HOST_SYNTAX_REPORT.json").read_text())
source = json.loads((ROOT / "docs/SOURCE_GATES.json").read_text())
resource = json.loads((ROOT / "docs/RESOURCE_BUDGET.json").read_text())
rill_static = json.loads((ROOT / "docs/rill-integration-status.json").read_text())
local_pass = (
    tests["status"] == "PASS"
    and all(item["status"] == "PASS" for item in steps)
    and host.get("errorCount") == 0
    and source.get("allPassed") is True
    and rill_static.get("staticContractVerdict") == "PASS"
    and rill_static.get("releasePinStructureVerdict") == "PASS"
)

packages = {}
for name in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill"):
    root = ROOT / "package" / name
    files = [path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    packages[name] = {
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "makefileSha256": sha(root / "Makefile"),
    }

external = [
    {"gate": "same-commit official OpenWrt SDK/APK build", "status": "NOT_EVALUATED"},
    {"gate": "exact Rill release provenance and binary runtime", "status": "NOT_EVALUATED"},
    {"gate": "production Core to exact adapter Observe/Outcome lifecycle", "status": "NOT_EVALUATED"},
    {"gate": "booted OpenWrt Core-only, full, and mutation target gates", "status": "NOT_EVALUATED"},
    {"gate": "Hyper-V and KVM TargetRef/hotplug/replay/rollback", "status": "NOT_EVALUATED"},
    {"gate": "LAN-WAN and router-local controlled A/B", "status": "NOT_EVALUATED"},
    {"gate": "real sysupgrade preservation", "status": "NOT_EVALUATED"},
    {"gate": "24-hour resource, restart, idle-Observe, and persistence soak", "status": "NOT_EVALUATED"},
]

report = {
    "schemaVersion": 3,
    "project": "OpenWrt Performance Manager",
    "version": VERSION,
    "pmCommitSha": git_commit(),
    "scope": "source-only",
    "sourceCandidateVerdict": "PASS" if local_pass else "FAIL",
    "functionalIntegrationVerdict": "NOT_EVALUATED",
    "stableReleaseVerdict": "NOT_EVALUATED",
    "promotionPolicy": "This report is non-promotable. Runtime and Stable PASS are exclusively owned by final_release_audit.py with same-commit external evidence.",
    "orchestrationSteps": steps,
    "localEvidence": {
        "unitAndContractTests": tests,
        "hostSyntaxChecks": {
            "status": "PASS" if host.get("errorCount") == 0 else "FAIL",
            "count": len(host.get("checks", [])),
        },
        "sourceGates": source,
        "resourceBudget": resource,
        "rillStatic": rill_static,
    },
    "notEvaluatedExternalGates": external,
    "targetEvidenceScripts": [
        "scripts/openwrt-target-gate.sh",
        "scripts/openwrt-sysupgrade-gate.sh",
        "scripts/openwrt-resource-soak.sh",
    ],
    "packages": packages,
    "toolchainAvailability": {
        "cargo": shutil.which("cargo") is not None,
        "rustc": shutil.which("rustc") is not None,
        "ucode": shutil.which("ucode") is not None,
    },
    "decision": (
        f"{VERSION} source candidate PASS; functional integration and Stable release are NOT_EVALUATED"
        if local_pass else f"{VERSION} source audit FAILED"
    ),
}
(ROOT / "docs/FINAL_AUDIT.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)
(ROOT / "docs/source-audit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)

phase_lines = "\n".join(
    f"- Phase {number}: **{gate['status'].upper()}** — {gate['name']}"
    for number, gate in source["phases"].items()
)
step_lines = "\n".join(
    f"- {item['name']}: **{item['status']}** ({item['evidenceClass']})"
    for item in steps
)
external_lines = "\n".join(
    f"- {item['gate']}: **{item['status']}**" for item in external
)
markdown = f"""# Source Audit — {VERSION}

## Decision

**{'PASS' if local_pass else 'FAIL'} — {report['decision']}.**

This is a source-only, non-promotable audit. It does not consume old runtime
artifacts and cannot claim functional-integration or Stable-release PASS.

## Orchestrated local gates

{step_lines}

- Executable unit/contract tests: **{tests['count']}**, status **{tests['status']}**.
- Rill static contract: **{rill_static.get('staticContractVerdict')}**.
- Rill release-pin structure: **{rill_static.get('releasePinStructureVerdict')}**.
- Rill functional integration: **NOT_EVALUATED** in this report.

## Source phase gates

{phase_lines}

## External gates intentionally not evaluated

{external_lines}

The only authority for a Stable verdict is `scripts/final_release_audit.py`,
which requires same-commit build, runtime, target, hypervisor, testbed,
sysupgrade, lifecycle, and 24-hour soak evidence.
"""
(ROOT / "docs/FINAL_AUDIT.md").write_text(markdown)
print(json.dumps({
    "version": VERSION,
    "sourceCandidateVerdict": report["sourceCandidateVerdict"],
    "functionalIntegrationVerdict": "NOT_EVALUATED",
    "stableReleaseVerdict": "NOT_EVALUATED",
    "testCount": tests["count"],
}, ensure_ascii=False, indent=2))
if not local_pass:
    sys.exit(1)
