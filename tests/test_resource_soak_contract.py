import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_external_evidence import GATE_CHECKS, evaluate_raw_facts, validate_evidence  # noqa: E402


class ResourceSoakContractTests(unittest.TestCase):
    def setUp(self):
        self.commit = "a" * 40
        self.evidence = json.loads((ROOT / "tests/fixtures/resource-soak-pass.json").read_text())
        self.evidence["pmCommitSha"] = self.commit
        self.evidence["controller"]["sha256"] = hashlib.sha256(
            (ROOT / self.evidence["controller"]["path"]).read_bytes()
        ).hexdigest()
        self.evidence["subchecks"] = evaluate_raw_facts(self.evidence, "resource-soak")

    def test_complete_positive_fixture_passes_end_to_end(self):
        self.assertEqual(validate_evidence(self.evidence, "resource-soak", self.commit), [])
        self.assertEqual(set(self.evidence["subchecks"]), set(GATE_CHECKS["resource-soak"]))

    def test_duration_below_24_hours_fails(self):
        broken = copy.deepcopy(self.evidence)
        broken["durationSeconds"] = broken["rawFacts"]["durationSeconds"] = 86399
        self.assertTrue(validate_evidence(broken, "resource-soak", self.commit))

    def test_runtime_failures_and_timeouts_fail(self):
        for field in ("runtimeInvocationFailureCount", "runtimeTimeoutCount", "runtimeMalformedResponseCount", "runtimeNonZeroExitCount"):
            with self.subTest(field=field):
                broken = copy.deepcopy(self.evidence)
                broken["rawFacts"]["soak"][field] = 1
                broken["subchecks"] = evaluate_raw_facts(broken, "resource-soak")
                errors = validate_evidence(broken, "resource-soak", self.commit)
                self.assertTrue(errors)
                self.assertIn("runtimeFailureZero", " ".join(errors))

    def test_core_restart_history_and_journal_budgets_fail(self):
        cases = {
            "coreRestartCount": ("noCoreRestart", 1),
            "corePersistentWritesPerDay": ("stateBoundsPass", 33),
            "persistentHistoryGrowthBytes": ("historyBoundsPass", 262145),
            "executionJournalBytes": ("journalMeasured", 2097153),
        }
        for field, (subcheck, value) in cases.items():
            with self.subTest(field=field):
                broken = copy.deepcopy(self.evidence)
                target = broken["rawFacts"]["soak"] if field == "coreRestartCount" else broken["rawFacts"]["soak"]["resources"]
                target[field] = value
                broken["subchecks"] = evaluate_raw_facts(broken, "resource-soak")
                errors = validate_evidence(broken, "resource-soak", self.commit)
                self.assertTrue(errors)
                self.assertIn(subcheck, " ".join(errors))

    def test_missing_runtime_metric_fails_closed(self):
        broken = copy.deepcopy(self.evidence)
        del broken["rawFacts"]["soak"]["resources"]["runtimeStateMaxBytes"]
        broken["subchecks"] = evaluate_raw_facts(broken, "resource-soak")
        self.assertTrue(validate_evidence(broken, "resource-soak", self.commit))

    def test_old_adapter_field_is_rejected_by_schema(self):
        broken = copy.deepcopy(self.evidence)
        soak = broken["rawFacts"]["soak"]
        soak["idleExpectedAdapterPersistenceEventsDelta"] = soak.pop("idleExpectedRuntimePersistenceEventsDelta")
        errors = validate_evidence(broken, "resource-soak", self.commit)
        self.assertTrue(any("additional property forbidden" in error or "required by schema" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
