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
    args = parser.parse_args(argv)
    out = Path(args.evidence_dir) / "final-stable-evidence.json"
    completed = subprocess.run([
        sys.executable, str(ROOT / "scripts/aggregate_stable_evidence.py"),
        "--evidence-dir", args.evidence_dir,
        "--expected-commit", args.expected_commit,
        "--out", str(out),
    ], cwd=ROOT)
    evidence = json.loads(out.read_text()) if out.exists() else {
        "overallVerdict": "BLOCKED", "requiredGates": {},
        "pmCommitSha": args.expected_commit,
    }
    verdict = evidence.get("overallVerdict", "BLOCKED")
    rows = [
        {"gate": name, **gate}
        for name, gate in evidence.get("requiredGates", {}).items()
    ]
    report = {
        "schemaVersion": 3,
        "project": "OpenWrt Performance Manager",
        "version": (ROOT / "VERSION").read_text().strip(),
        "pmCommitSha": args.expected_commit,
        "scope": "stable-release",
        "stableReleaseVerdict": verdict,
        "stableReleaseAuthorized": verdict == "PASS",
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
    (ROOT / "docs/FINAL_AUDIT.md").write_text(f"""# Stable Release Verdict — {verdict}

- Version: `{report['version']}`
- PM commit: `{args.expected_commit}`
- Exact Rill adapter SHA-256: `{evidence.get('adapterSha256')}`

## Required evidence

{lines}

Stable release authorization: **{'YES' if verdict == 'PASS' else 'NO'}**.
""")
    print(json.dumps({"stableReleaseVerdict": verdict, "authorized": verdict == "PASS"}, indent=2))
    return 0 if completed.returncode == 0 and verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
