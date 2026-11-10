# Sync Rill Runtime: PR-first with a bounded contract scope

- Date: 2026-11-11
- Status: ADOPTED
- Supersedes: `sync-rill.yml` read-only policy (`ab1be05 ci(sync): keep qualified runtime sync read-only`)
- Related: PR #16 (GitHub Actions hardening), PR #18 (reaudit → main), PR #13 (stage 3)

## Background

Two lines of work touched the same workflow and encoded opposite intents:

- `main` (PR #16 / #14): `contents: write` + `pull-requests: write`, a `concurrency` group, and an
  idempotent job that creates `chore/rill-<version>`, pushes it, and opens a pull request.
- `yunshu/openwrt-reaudit` (`ab1be05`): `contents: read`, no branch creation, no PR creation, and a hard
  `::error::` failure as soon as `check_rill_dependency.py --sync` produced a diff.

Merging the reaudit line into `main` therefore produced a real conflict, and the read-only contract test
(`tests/test_contracts.py`) failed as soon as `main`'s automation was kept. That test, not the YAML alone,
was the load-bearing part of the old policy.

## Why read-only was chosen originally

The sync mutates the single immutable Runtime contract that every consumer package verifies against.
A scheduled job with write access that silently rewrites more than that contract is a supply-chain risk:
the diff would be reviewed, but only after the damage was already committed to a branch, and any file
outside the contract would be invisible in a quick review.

## Decision

Keep the automation, but make the pull request the only path, and bound what the automation may touch:

1. `contents: write` / `pull-requests: write` and the `concurrency` group stay (PR #16 behaviour).
2. `check_rill_dependency.py --sync` still resolves the latest qualified Stable 1.x.
3. A `Verify no contract drift` step runs **before** the PR is opened. It fails the job if any tracked
   file other than `contracts/rill-runtime.json` changed. Untracked files (nested checkouts, build
   leftovers) are ignored so the guard cannot be tripped by the workspace layout.
4. If the contract did not change, the job exits without opening anything. If it did, the job creates or
   reuses `chore/rill-<version>` and opens a PR. The required consumer integration checks gate the merge.

## Security boundary after the change

- The only file the automation may rewrite is `contracts/rill-runtime.json`; anything else fails the job.
- Nothing reaches `main` without a pull request and its required checks.
- No force push, no direct push to `main`, no deletion of existing branches.
- The job keeps the repository-scoped `github.token`; no additional secrets are introduced.
- `tests/test_contracts.py::test_sync_rill_is_pr_first_and_bounded_to_the_runtime_contract` executes the
  guard script in a throwaway git repository and asserts three cases: contract-only change passes,
  an out-of-scope tracked rewrite fails and names the offending file, untracked files do not trip it.

## What was relaxed

The workflow may once again create a branch and a pull request. The old guarantee "the sync can never
write" is gone; it is replaced by "the sync can only write one file, and only through review".

## What triggered this

The branch-topology cleanup that merged `yunshu/openwrt-reaudit` (84 commits) into `main` before stage 3,
where both sides had already shipped their version of this workflow. See PR #18.
