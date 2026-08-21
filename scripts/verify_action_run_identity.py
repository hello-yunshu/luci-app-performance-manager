#!/usr/bin/env python3
"""Reject GitHub Action run IDs that are not the exact successful workflow/SHA."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def validate_run_identity(data: Any, expected_sha: str, expected_workflow: str,
                          expected_workflow_path: str | None = None,
                          expected_repository: str | None = None) -> list[str]:
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
    if expected_workflow_path and data.get("path") != expected_workflow_path:
        errors.append(f"workflowPath={data.get('path')!r}")
    repository = data.get("repository")
    if isinstance(repository, dict):
        repository = repository.get("fullName") or repository.get("full_name")
    if expected_repository and repository != expected_repository:
        errors.append(f"repository={repository!r}")
    if expected_workflow_path or expected_repository:
        for field in ("workflowDatabaseId", "runAttempt", "event", "headBranch"):
            if field not in data or data.get(field) in (None, ""):
                errors.append(f"{field} missing")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-workflow", required=True)
    parser.add_argument("--expected-workflow-path", required=True)
    parser.add_argument("--expected-repository", default="hello-yunshu/luci-app-performance-manager")
    parser.add_argument("--metadata-json", help="Test/offline input instead of gh run view")
    args = parser.parse_args(argv)
    if args.metadata_json:
        data = json.loads(args.metadata_json)
    else:
        completed = subprocess.run(
            ["gh", "api", f"repos/{args.expected_repository}/actions/runs/{args.run_id}"],
            text=True, capture_output=True,
        )
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout, file=sys.stderr)
            return 1
        data = json.loads(completed.stdout)
    normalized = {
        **data,
        "headSha": data.get("head_sha", data.get("headSha")),
        "workflowName": data.get("name", data.get("workflowName")),
        "path": data.get("path"),
        "workflowDatabaseId": data.get("workflow_id", data.get("workflowDatabaseId")),
        "runAttempt": data.get("run_attempt", data.get("runAttempt")),
        "headBranch": data.get("head_branch", data.get("headBranch")),
        "repository": data.get("repository", data.get("repository")),
    }
    errors = validate_run_identity(normalized, args.expected_sha, args.expected_workflow,
                                   args.expected_workflow_path, args.expected_repository)
    if errors:
        print(f"FAIL run={args.run_id}: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"PASS run={args.run_id} sha={args.expected_sha} workflow={args.expected_workflow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
