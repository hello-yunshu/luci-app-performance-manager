#!/usr/bin/env python3
"""Reject GitHub Action run IDs that are not the exact successful workflow/SHA."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def validate_run_identity(data: Any, expected_sha: str, expected_workflow: str) -> list[str]:
    if not isinstance(data, dict):
        return ["run metadata is not an object"]
    errors = []
    if data.get("conclusion") != "success":
        errors.append(f"conclusion={data.get('conclusion')!r}")
    if data.get("headSha") != expected_sha:
        errors.append(f"headSha={data.get('headSha')!r}")
    actual_workflow = data.get("workflowName") or data.get("name")
    if actual_workflow != expected_workflow:
        errors.append(f"workflow={actual_workflow!r}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-workflow", required=True)
    parser.add_argument("--metadata-json", help="Test/offline input instead of gh run view")
    args = parser.parse_args(argv)
    if args.metadata_json:
        data = json.loads(args.metadata_json)
    else:
        completed = subprocess.run(
            ["gh", "run", "view", str(args.run_id), "--json", "conclusion,headSha,name,workflowName,event"],
            text=True, capture_output=True,
        )
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout, file=sys.stderr)
            return 1
        data = json.loads(completed.stdout)
    errors = validate_run_identity(data, args.expected_sha, args.expected_workflow)
    if errors:
        print(f"FAIL run={args.run_id}: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"PASS run={args.run_id} sha={args.expected_sha} workflow={args.expected_workflow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
