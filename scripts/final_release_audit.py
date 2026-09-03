#!/usr/bin/env python3
"""Write the authoritative Stable audit from aggregated same-commit evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--profile", choices=("hardware", "portable-docker"), default="hardware")
    args = parser.parse_args(argv)
    out = Path(args.evidence_dir) / "final-stable-evidence.json"
    completed = subprocess.run([
        sys.executable, str(ROOT / "scripts/aggregate_stable_evidence.py"),
        "--evidence-dir", args.evidence_dir,
        "--expected-commit", args.expected_commit,
        "--profile", args.profile,
        "--out", str(out),
    ], cwd=ROOT)
    evidence = json.loads(out.read_text()) if out.exists() else {
        "overallVerdict": "BLOCKED", "requiredGates": {},
        "pmCommitSha": args.expected_commit,
    }
    verdict = evidence.get("overallVerdict", "BLOCKED")
    stable_verdict = evidence.get("stableReleaseVerdict", "NOT_EVALUATED")
    authorized = (
        args.profile == "hardware"
        and evidence.get("stableReleaseVerdict") == "PASS"
        and evidence.get("hardwareCoverage") == "PASS"
        and evidence.get("stableReleaseAuthorized") is True
    )
    rows = [
        {"gate": name, **gate}
        for name, gate in evidence.get("requiredGates", {}).items()
    ]
    report = {
        "schemaVersion": 3,
        "project": "OpenWrt Performance Manager",
        "version": (ROOT / "VERSION").read_text().strip(),
        "pmCommitSha": args.expected_commit,
        "scope": f"{args.profile}-release",
        "releaseProfile": args.profile,
        "portableVerdict": evidence.get("portableVerdict"),
        "stableReleaseVerdict": stable_verdict,
        "stableReleaseAuthorized": authorized,
        "hardwareCoverage": evidence.get("hardwareCoverage", "NOT_EVALUATED"),
        "gates": rows,
        "evidence": evidence,
    }
    (ROOT / "docs/FINAL_AUDIT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    lines = "\n".join(
        f"- {row['gate']}: **{row['status']}**"
        + (f" — {row['reason']}" if row.get("reason") else "")
        for row in rows
    )
    (ROOT / "docs/FINAL_AUDIT.md").write_text(f"""# Release Evidence — {args.profile}

- Version: `{report['version']}`
- PM commit: `{args.expected_commit}`
- Exact generic Runtime SHA-256: `{evidence.get('runtimeSha256')}`

## Required evidence

{lines}

Portable verdict: **{evidence.get('portableVerdict') or 'NOT_APPLICABLE'}**.
Hardware coverage: **{evidence.get('hardwareCoverage', 'NOT_EVALUATED')}**.
Stable release verdict: **{stable_verdict}**.
Stable release authorization: **{'YES' if authorized else 'NO'}**.
""")
    print(json.dumps({"overallVerdict": verdict, "stableReleaseVerdict": stable_verdict, "authorized": authorized}, indent=2))
    return 0 if completed.returncode == 0 and verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
