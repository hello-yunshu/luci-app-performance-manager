import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/stable-testbed"))
from controller import RESERVED_TRANSPORT_FIELDS, evaluate_raw_facts  # noqa: E402
from validate_external_evidence import GATE_CHECKS, PIN  # noqa: E402


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

    def test_all_gate_evaluators_consume_raw_observations(self):
        package_names = ("performance-manager", "luci-app-performance-manager",
                         "performance-manager-rill", "luci-app-performance-manager-all")
        common = {"installedPackages": {name: {} for name in package_names}}
        raws = {
            "target-full": {**common, "permissions": {"serviceUid": 5666, "serviceUserDedicated": True,
                "stateDirectoryMode": "0750", "stateDirectoryOwner": "performance-manager-rill:performance-manager-rill"},
                "rill": {"adapterSha256": PIN, "connectedToCore": True, "statusResponse": {"ready": True}},
                "rillDirectMutationCount": 0, "mutationAuthority": "pm-core"},
            "target-mutation": {"mutation": {"candidate": {"actionId": "a", "authority": "advisory-only", "mutationOwner": "pm-core"},
                "before": {"x": 1}, "applyExitCode": 0, "readback": {"x": 2}, "candidateState": {"x": 2},
                "rollbackExitCode": 0, "afterRollback": {"x": 1}, "secondApplyExitCode": 0, "staleLocks": 0,
                "stalePolicies": 0, "ownershipAfter": "clean", "packetSteeringOwner": "native", "staleRuntimeState": 0}},
            "lifecycle": {"lifecycle": {"steps": {name: {"exitCode": 0, "observed": True} for name in GATE_CHECKS["lifecycle"]}}},
        }
        for gate, facts in raws.items():
            with self.subTest(gate=gate):
                checks = evaluate_raw_facts({"rawFacts": facts}, gate)
                self.assertEqual(set(checks), set(GATE_CHECKS[gate]))
                self.assertTrue(all(checks.values()))

    def test_forged_all_true_subchecks_do_not_override_raw_facts(self):
        raw = {"rawFacts": {"environment": {"release": "25.12.5", "target": "x86/64"},
                             "process": {"corePid": 1}, "ubusSocketReady": True,
                             "statusResponseValid": True, "analyzeResponseValid": True,
                             "topologyEvidenceValid": True, "capabilitiesEvidenceValid": False,
                             "staleLocks": 0},
               "subchecks": {name: True for name in GATE_CHECKS["target-core-only"]}}
        checks = evaluate_raw_facts(raw, "target-core-only")
        self.assertFalse(checks["capabilitiesValid"])
        self.assertTrue(all(value for name, value in checks.items() if name != "capabilitiesValid"))


if __name__ == "__main__":
    unittest.main()
