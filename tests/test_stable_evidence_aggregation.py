import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from aggregate_stable_evidence import PINNED_ADAPTER_SHA, REQUIRED, RILL_PRESENT  # noqa: E402


class StableEvidenceAggregationTests(unittest.TestCase):
    commit = "a" * 40

    def evidence(self, name):
        data = {"pmCommitSha": self.commit, "verdict": "PASS", "passed": True}
        if name == "source":
            data["sourceCandidateVerdict"] = "PASS"
        elif name == "rillProvenance":
            data["provenanceVerdict"] = "PASS"
        elif name == "rillRuntime":
            data["overallVerdict"] = "PASS"
        elif name == "openwrtSdk":
            data.pop("pmCommitSha")
            data["repositoryCommitSha"] = self.commit
            data["verdicts"] = {"pmPackagesBuildVerdict": "PASS"}
        if name in RILL_PRESENT:
            data["adapterSha256"] = PINNED_ADAPTER_SHA
        return data

    def run_aggregate(self, mutate=None, omit=None):
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = Path(temp) / "evidence"
            evidence_dir.mkdir()
            for name, filename in REQUIRED.items():
                if name == omit:
                    continue
                data = self.evidence(name)
                if mutate and name == mutate[0]:
                    data.update(mutate[1])
                (evidence_dir / filename).write_text(json.dumps(data))
            output = Path(temp) / "final.json"
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/aggregate_stable_evidence.py"),
                "--evidence-dir", str(evidence_dir),
                "--expected-commit", self.commit,
                "--out", str(output),
            ], capture_output=True, text=True)
            return completed.returncode, json.loads(output.read_text())

    def test_all_required_same_commit_exact_adapter_passes(self):
        code, result = self.run_aggregate()
        self.assertEqual(code, 0)
        self.assertEqual(result["overallVerdict"], "PASS")
        self.assertTrue(result["stableReleaseAuthorized"])

    def test_missing_required_evidence_is_blocked(self):
        code, result = self.run_aggregate(omit="hyperV")
        self.assertNotEqual(code, 0)
        self.assertEqual(result["overallVerdict"], "BLOCKED")
        self.assertEqual(result["requiredGates"]["hyperV"]["status"], "BLOCKED")

    def test_commit_identity_mismatch_is_fail(self):
        code, result = self.run_aggregate(mutate=("kvm", {"pmCommitSha": "b" * 40}))
        self.assertNotEqual(code, 0)
        self.assertEqual(result["overallVerdict"], "FAIL")
        self.assertEqual(result["requiredGates"]["kvm"]["status"], "FAIL")

    def test_rill_artifact_identity_mismatch_is_fail(self):
        code, result = self.run_aggregate(mutate=("resourceSoak24h", {"adapterSha256": "0" * 64}))
        self.assertNotEqual(code, 0)
        self.assertEqual(result["overallVerdict"], "FAIL")

    def test_not_evaluated_never_promotes(self):
        code, result = self.run_aggregate(mutate=("lifecycle", {"verdict": "NOT_EVALUATED", "passed": False}))
        self.assertNotEqual(code, 0)
        self.assertEqual(result["overallVerdict"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
