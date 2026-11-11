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
TEMP_PATH = re.compile(r"/(?:private/)?(?:tmp|var/folders)/[^\s\"']+")

# These files are rewritten by this audit itself.  They must not make the
# source tree look dirty, and a commit that only changes them is a snapshot
# commit rather than a new source revision.
GENERATED_EVIDENCE_PATHS = frozenset({
    "docs/FINAL_AUDIT.json",
    "docs/FINAL_AUDIT.md",
    "docs/source-audit.json",
    "docs/SOURCE_GATES.json",
    "docs/HOST_SYNTAX_REPORT.json",
    "docs/RESOURCE_BUDGET.json",
    "docs/rill-integration-status.json",
    "docs/apk-verification.json",
})


def stable_output_tail(output: str) -> str:
    """Keep generated audit evidence stable across temporary directories."""
    return TEMP_PATH.sub("<temporary-path>", output[-4000:])


def git_output(args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def head_sha() -> str:
    completed = git_output(["rev-parse", "HEAD"])
    value = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SystemExit("ERROR: unable to resolve a real HEAD commit SHA")
    return value


def changed_paths(parent: str, child: str) -> list[str]:
    completed = git_output(["diff", "--name-only", parent, child])
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line]


def source_commit(head: str) -> str:
    """Return the audited source commit, skipping snapshot-only children.

    A commit cannot contain its own SHA, so a snapshot that is committed after
    generation necessarily lives in a child commit.  When HEAD is such a
    snapshot-only child, the snapshot must keep identifying its source parent;
    otherwise every regeneration after committing the snapshot would rewrite
    pmCommitSha and make the audit non-idempotent.
    """
    candidate = head
    for _ in range(10):
        parent = git_output(["rev-parse", f"{candidate}^"])
        if parent.returncode != 0:
            break
        parent_sha = parent.stdout.strip()
        paths = changed_paths(parent_sha, candidate)
        if not paths or not set(paths).issubset(GENERATED_EVIDENCE_PATHS):
            break
        candidate = parent_sha
    return candidate


def dirty_source_paths() -> list[str]:
    completed = git_output(["status", "--porcelain", "--untracked-files=no"])
    if completed.returncode != 0:
        raise SystemExit("ERROR: unable to inspect git worktree state")
    dirty = []
    for line in completed.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path and path not in GENERATED_EVIDENCE_PATHS:
            dirty.append(path)
    return dirty


HEAD_SHA = head_sha()
DIRTY_SOURCE = dirty_source_paths()
if DIRTY_SOURCE:
    print("ERROR: source worktree is dirty; refusing to write an audit snapshot.",
          file=sys.stderr)
    print("A snapshot written now would identify a commit that does not contain these changes.",
          file=sys.stderr)
    for path in DIRTY_SOURCE:
        print(f"  dirty: {path}", file=sys.stderr)
    print("Commit or stash the source changes, then rerun make audit.", file=sys.stderr)
    raise SystemExit(2)
SOURCE_COMMIT = source_commit(HEAD_SHA)


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
        "outputTail": stable_output_tail(completed.stdout),
    })
    return completed


unit = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
match = re.search(r"Ran (\d+) tests?", unit.stdout)
tests = {
    "status": "PASS" if unit.returncode == 0 else "FAIL",
    "count": int(match.group(1)) if match else None,
    "outputTail": stable_output_tail(unit.stdout),
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
)

packages = {}
for name in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill",
             "luci-app-performance-manager-all"):
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
    {"gate": "production Core to exact generic Runtime Observe/Outcome lifecycle", "status": "NOT_EVALUATED"},
    {"gate": "booted OpenWrt Core-only, full, and mutation target gates", "status": "NOT_EVALUATED"},
    {"gate": "Hyper-V and KVM TargetRef/hotplug/replay/rollback", "status": "NOT_EVALUATED"},
    {"gate": "LAN-WAN and router-local controlled A/B", "status": "NOT_EVALUATED"},
    {"gate": "real sysupgrade preservation", "status": "NOT_EVALUATED"},
    {"gate": "12-hour resource, restart, idle-Observe, and persistence soak", "status": "NOT_EVALUATED"},
]

report = {
    "schemaVersion": 3,
    "project": "OpenWrt Performance Manager",
    "version": VERSION,
    "pmCommitSha": SOURCE_COMMIT,
    "scope": "source-only",
    "sourceTreeClean": True,
    "sourceTreeDirtyPaths": [],
    "snapshotIdentity": "source-commit",
    "snapshotCommitPolicy": "pmCommitSha identifies the audited source commit. A commit that changes only GENERATED_EVIDENCE_PATHS is a snapshot-only child and is skipped, so regenerating after committing the snapshot is byte-identical.",
    "sourceCandidateVerdict": "PASS" if local_pass else "FAIL",
    "functionalIntegrationVerdict": "NOT_EVALUATED",
    "stableReleaseVerdict": "NOT_EVALUATED",
    "testEvidenceScope": "checked-in source-audit snapshot; current same-SHA CI artifacts are authoritative",
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
if head_sha() != HEAD_SHA:
    print("ERROR: HEAD changed while the audit was running; refusing to write an unattributable snapshot.",
          file=sys.stderr)
    raise SystemExit(3)
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

Snapshot source commit: **{report['pmCommitSha']}**. A commit that only changes
generated audit files is treated as a snapshot child, not a new source revision.

## Orchestrated local gates

{step_lines}

- Executable unit/contract tests in this checked-in source-audit snapshot: **{tests['count']}**, status **{tests['status']}**.
- Current test counts and conclusions come from the same-SHA CI artifacts, not this historical/generated snapshot.
- Rill static contract: **{rill_static.get('staticContractVerdict')}**.
- Rill release-pin structure: **{rill_static.get('releasePinStructureVerdict')}**.
- Rill functional integration: **NOT_EVALUATED** in this report.

## Source phase gates

{phase_lines}

## External gates intentionally not evaluated

{external_lines}

The only authority for a Stable verdict is `scripts/final_release_audit.py`,
which requires same-commit build, runtime, target, hypervisor, testbed,
sysupgrade, lifecycle, and 12-hour soak evidence.
"""
(ROOT / "docs/FINAL_AUDIT.md").write_text(markdown)
print(json.dumps({
    "version": VERSION,
    "pmCommitSha": report["pmCommitSha"],
    "sourceCandidateVerdict": report["sourceCandidateVerdict"],
    "functionalIntegrationVerdict": "NOT_EVALUATED",
    "stableReleaseVerdict": "NOT_EVALUATED",
    "testCount": tests["count"],
}, ensure_ascii=False, indent=2))
if not local_pass:
    sys.exit(1)
