import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/stable-testbed"))
from controller import RESERVED_TRANSPORT_FIELDS, evaluate_raw_facts  # noqa: E402


class StableTestbedControllerTests(unittest.TestCase):
    def test_transport_verdict_fields_are_reserved(self):
        hostile = {"subchecks": {"all": True}, "verdict": "PASS", "passed": True}
        self.assertTrue(RESERVED_TRANSPORT_FIELDS.intersection(hostile))

    def test_missing_raw_facts_cannot_become_pass(self):
        checks = evaluate_raw_facts({}, "target-core-only")
        self.assertTrue(checks)
        self.assertFalse(any(checks.values()))

    def test_hyperv_subchecks_are_derived_from_identity_and_observations(self):
        raw = {"rawFacts": {"environment": {"hypervisor": "Hyper-V", "vmbusId": "vmbus-1", "nicDriver": "hv_netvsc"},
                             "hotplug": {"before": "a", "after": "b"}, "targetRefStableId": True,
                             "replayCount": 1, "rollback": {"before": "x", "after": "x"}}}
        checks = evaluate_raw_facts(raw, "hyperv")
        self.assertTrue(all(checks.values()))

    def test_nested_verdict_map_cannot_become_a_non_core_pass(self):
        raw = {"rawFacts": {"observed": {name: True for name in ("install", "serviceStart", "restart")}}}
        checks = evaluate_raw_facts(raw, "lifecycle")
        self.assertFalse(any(checks.values()))


if __name__ == "__main__":
    unittest.main()
