#!/usr/bin/env python3
"""Unit tests for the final release evidence aggregator (rc.7 prompt 25/27/29/43).

The aggregator turns per-job evidence files into the release verdict.  It must
fail closed on ANY uncertainty:

  - same-commit evidence chain: a job that ran on a different PM commit (or
    carries no commit SHA) FAILs the whole chain, because its verdicts cannot
    be attributed to this release.
  - combine_required: ANY FAIL -> FAIL; ALL PASS -> PASS; otherwise BLOCKED.
    A PASS + BLOCKED mix is BLOCKED, never silently upgraded to PASS.
  - scope isolation: ci.yml gates only the Rill chain (--scope rill) and
    build-openwrt.yml only the SDK/APK chain (--scope build), so neither
    workflow can falsely PASS what the other workflow alone can prove.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_final_evidence as agg  # noqa: E402

COMMIT = "9ba659a"  # any stable-ish sentinel; only internal consistency matters


def _prov(commit=COMMIT, tag="PASS", index="PASS", artifact="PASS"):
    return {
        "schemaVersion": 1,
        "contract": "pm<->rill-release-provenance",
        "pmCommitSha": commit,
        "tagIdentityVerdict": tag,
        "indexSignatureVerdict": index,
        "artifact": {"artifactIntegrityVerdict": artifact},
        "provenanceVerdict": "PASS" if tag == index == artifact == "PASS" else "FAIL",
    }


def _runtime(commit=COMMIT, verdicts=None, top_compat=None, top_func=None):
    v = verdicts or {
        "executableVerdict": "PASS", "versionVerdict": "PASS",
        "startupVerdict": "PASS", "statusVerdict": "PASS",
        "observeVerdict": "PASS", "outcomeVerdict": "PASS", "failClosedVerdict": "PASS",
    }
    return {
        "schemaVersion": 2,
        "contract": "pm<->rill-runtime",
        "pmCommitSha": commit,
        "verdicts": v,
        "runtimeCompatibilityVerdict": top_compat if top_compat is not None else
            "PASS" if all(v.get(k) == "PASS" for k in
                           ("executableVerdict", "versionVerdict", "startupVerdict", "statusVerdict"))
            else "BLOCKED",
        "functionalIntegrationVerdict": top_func if top_func is not None else
            "PASS" if all(v.get(k) == "PASS" for k in ("observeVerdict", "outcomeVerdict", "failClosedVerdict"))
            else "BLOCKED",
    }


def _core(commit=COMMIT, verdict="PASS"):
    return {"schemaVersion": 2, "contract": "pm<->rill-core-integration",
            "pmCommitSha": commit, "verdict": verdict, "ok": verdict == "PASS"}


def _build_meta(commit=COMMIT, build="PASS", apk="PASS"):
    return {"schemaVersion": 1, "repositoryCommitSha": commit,
            "verdicts": {"pmPackagesBuildVerdict": build,
                         "apkExactVerificationVerdict": apk, "rcVerdict": "BLOCKED"},
            "verdict": "PASS" if build == apk == "PASS" else "FAIL"}


def _apk(commit=COMMIT, verdict="PASS"):
    return {"schemaVersion": 1, "contract": "apk-exact-verification",
            "pmCommitSha": commit, "verdict": verdict}


class EvidenceAggregationTest(unittest.TestCase):
    def run_agg(self, scope, files, expected_commit=None, tmpdir=None):
        """Write evidence `files` into a temp dir and run the aggregator for
        `scope`, returning (exit_code, result_dict)."""
        td = Path(tmpdir) if tmpdir else tempfile.mkdtemp()
        for name, obj in files.items():
            (Path(td) / name).write_text(json.dumps(obj))
        argv = ["--evidence-dir", td, "--scope", scope,
                "--out", str(Path(td) / "final.json")]
        if expected_commit:
            argv += ["--expected-commit", expected_commit]
        code = agg.main(argv)
        result = json.loads((Path(td) / "final.json").read_text())
        return code, result

    def test_full_scope_all_pass_same_commit(self):
        files = {
            "rill-provenance.json": _prov(),
            "rill-runtime.json": _runtime(),
            "rill-core-integration.json": _core(),
            "build-metadata.json": _build_meta(),
            "apk-verification.json": _apk(),
        }
        code, r = self.run_agg("full", files, expected_commit=COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(r["overallVerdict"], "PASS")
        self.assertEqual(r["rcVerdict"], "PASS")
        self.assertEqual(r["evidenceChainVerdict"], "PASS")
        self.assertNotIn("missing", r["missingEvidence"])

    def test_rill_scope_isolates_build_gates(self):
        """--scope rill must NOT require (or gate on) build evidence; the
        build gates are recorded OUT_OF_SCOPE, not silently upgraded."""
        files = {
            "rill-provenance.json": _prov(),
            "rill-runtime.json": _runtime(),
            "rill-core-integration.json": _core(),
        }
        code, r = self.run_agg("rill", files, expected_commit=COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(r["overallVerdict"], "PASS")
        self.assertEqual(r["verdicts"]["apkPackagesBuildVerdict"], agg.OUT_OF_SCOPE)
        self.assertEqual(r["verdicts"]["apkExactVerificationVerdict"], agg.OUT_OF_SCOPE)

    def test_build_scope_isolates_rill_gates(self):
        """--scope build must NOT require the Rill runtime jobs' evidence."""
        files = {"build-metadata.json": _build_meta(), "apk-verification.json": _apk()}
        code, r = self.run_agg("build", files, expected_commit=COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(r["overallVerdict"], "PASS")
        self.assertEqual(r["verdicts"]["rillArtifactProvenanceVerdict"], agg.OUT_OF_SCOPE)
        self.assertEqual(r["verdicts"]["rillRuntimeCompatibilityVerdict"], agg.OUT_OF_SCOPE)
        self.assertEqual(r["verdicts"]["rillFunctionalIntegrationVerdict"], agg.OUT_OF_SCOPE)

    def test_supplementary_wire_snapshot_is_not_in_same_commit_chain(self):
        """A historical mock-wire snapshot is transparency-only.  Fresh real
        SDK evidence must not fail merely because that optional file is from a
        different commit."""
        files = {
            "build-metadata.json": _build_meta(),
            "apk-verification.json": _apk(),
            "rill-wire-harness.json": {
                "pmCommitSha": "historical-snapshot",
                "runtime": {"wireHarnessVerdict": "PASS"},
            },
        }
        code, r = self.run_agg("build", files, expected_commit=COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(r["evidenceChainVerdict"], "PASS")
        self.assertNotIn("rill-wire-harness.json", r["evidenceCommits"])
        self.assertEqual(r["verdicts"]["wireHarnessVerdict"], "PASS")

    def test_commit_mismatch_fails_chain(self):
        """A single evidence file produced at a different commit must FAIL the
        whole release — its verdicts cannot be attributed to this commit."""
        files = {
            "rill-provenance.json": _prov(),
            "rill-runtime.json": _runtime(commit="deadbeef"),
            "rill-core-integration.json": _core(),
        }
        code, r = self.run_agg("rill", files, expected_commit=COMMIT)
        self.assertEqual(code, 1)
        self.assertEqual(r["evidenceChainVerdict"], "FAIL")
        self.assertEqual(r["overallVerdict"], "FAIL")

    def test_missing_commit_sha_fails_closed(self):
        files = {
            "rill-provenance.json": _prov(),
            "rill-runtime.json": _runtime(commit=""),
            "rill-core-integration.json": _core(),
        }
        code, r = self.run_agg("rill", files)
        self.assertEqual(code, 1)
        self.assertEqual(r["evidenceChainVerdict"], "FAIL")

    def test_missing_required_evidence_fails(self):
        files = {"rill-provenance.json": _prov(), "rill-runtime.json": _runtime()}
        code, r = self.run_agg("rill", files, expected_commit=COMMIT)
        self.assertEqual(code, 1)
        self.assertEqual(r["evidenceChainVerdict"], "FAIL")
        self.assertIn("rill-core-integration.json", r["missingEvidence"])

    def test_top_level_pass_but_subgate_blocked_is_fail(self):
        """A runtime file claiming functionalIntegrationVerdict=PASS while a
        granular verdicts.* gate is BLOCKED must FAIL, never be trusted."""
        verdicts = {
            "executableVerdict": "PASS", "versionVerdict": "PASS",
            "startupVerdict": "PASS", "statusVerdict": "PASS",
            "observeVerdict": "PASS", "outcomeVerdict": "PASS", "failClosedVerdict": "BLOCKED",
        }
        files = {
            "rill-provenance.json": _prov(),
            "rill-runtime.json": _runtime(verdicts=verdicts,
                                          top_compat="PASS", top_func="PASS"),
            "rill-core-integration.json": _core(),
        }
        code, r = self.run_agg("rill", files, expected_commit=COMMIT)
        self.assertEqual(code, 1)
        self.assertEqual(r["verdicts"]["rillFunctionalIntegrationVerdict"], "FAIL")
        self.assertIn("contradicts", r["reasons"]["functionalIntegration"] or "")

    def test_provenance_subgate_fail_fails_release(self):
        files = {
            "rill-provenance.json": _prov(index="FAIL"),
            "rill-runtime.json": _runtime(),
            "rill-core-integration.json": _core(),
        }
        code, r = self.run_agg("rill", files, expected_commit=COMMIT)
        self.assertEqual(code, 1)
        self.assertEqual(r["verdicts"]["rillArtifactProvenanceVerdict"], "FAIL")

    def test_apk_verification_fail_fails_build_scope(self):
        files = {"build-metadata.json": _build_meta(), "apk-verification.json": _apk(verdict="FAIL")}
        code, r = self.run_agg("build", files, expected_commit=COMMIT)
        self.assertEqual(code, 1)
        self.assertEqual(r["verdicts"]["apkExactVerificationVerdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
