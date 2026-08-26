import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/stable-testbed"))
from controller import INSTALL_PLANS, RESERVED_TRANSPORT_FIELDS, evaluate_raw_facts  # noqa: E402
from validate_external_evidence import GATE_CHECKS, PIN  # noqa: E402


class StableTestbedControllerTests(unittest.TestCase):
    def test_transport_verdict_fields_are_reserved(self):
        hostile = {"subchecks": {"all": True}, "verdict": "PASS", "passed": True}
        self.assertTrue(RESERVED_TRANSPORT_FIELDS.intersection(hostile))

    def test_controller_install_plans_are_explicit_and_mutually_exclusive(self):
        self.assertEqual(INSTALL_PLANS["target-core-only"]["requiredPackages"], ["performance-manager"])
        self.assertEqual(INSTALL_PLANS["target-full"]["requiredPackages"], ["luci-app-performance-manager-all", "performance-manager-rill-adapter"])
        lifecycle = {phase["name"]: phase["requiredPackages"] for phase in INSTALL_PLANS["lifecycle"]["phases"]}
        self.assertEqual(set(lifecycle["split"]), {"performance-manager", "luci-app-performance-manager", "performance-manager-rill", "performance-manager-rill-adapter"})
        self.assertEqual(lifecycle["bundle"], ["luci-app-performance-manager-all", "performance-manager-rill-adapter"])

    def test_missing_raw_facts_cannot_become_pass(self):
        checks = evaluate_raw_facts({}, "target-core-only")
        self.assertTrue(checks)
        self.assertFalse(any(checks.values()))

    def test_hyperv_subchecks_are_derived_from_identity_and_observations(self):
        raw = {"rawFacts": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}, "environment": {"hypervisor": "Hyper-V", "vmbusId": "vmbus-1", "nicDriver": "hv_netvsc"},
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
        common = {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}}
        raws = {
            "target-full": {**common, "permissions": {"serviceUid": 5666, "serviceUserDedicated": True,
                "stateDirectoryMode": "0750", "stateDirectoryOwner": "performance-manager-rill:performance-manager-rill"},
                "rill": {"adapterSha256": PIN, "connectedToCore": True, "statusResponse": {"ready": True}},
                "rillDirectMutationCount": 0, "mutationAuthority": "pm-core"},
            "target-mutation": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}, "mutation": {"candidate": {"actionId": "nic.ring.floor", "authority": "advisory-only", "mutationOwner": "pm-core", "targetStableId": "stable-1", "rx": 1024, "tx": 1024},
                "before": {"rx": 512, "tx": 512}, "applyExitCode": 0, "readback": {"rx": 1024, "tx": 1024}, "candidateState": {"rx": 1024, "tx": 1024},
                "rollbackExitCode": 0, "afterRollback": {"rx": 512, "tx": 512}, "secondApplyExitCode": 0, "staleLocks": 0,
                "stalePolicies": 0, "ownershipAfter": "clean", "packetSteeringOwner": "native", "staleRuntimeState": 0}},
            "lifecycle": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}, "lifecycle": {"phases": [
                {"name": "split-install", "exitCode": 0, "installedPackages": {"performance-manager": {}, "luci-app-performance-manager": {}, "performance-manager-rill": {}, "performance-manager-rill-adapter": {}}, "configSha256": "a" * 64},
                {"name": "split-runtime", "corePid": 1, "ubusReady": True, "rillAdapterSha256": PIN},
                {"name": "migration", "removeExitCode": 0, "installBundleExitCode": 0, "installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}},
                {"name": "bundle-runtime", "corePid": 2, "ubusReady": True, "configSha256": "a" * 64},
                {"name": "uninstall", "exitCode": 0, "remainingOwnedPaths": [], "staleLocks": 0, "stalePending": 0, "staleSockets": 0},
                {"name": "reinstall", "exitCode": 0, "installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}, "corePid": 3, "ubusReady": True},
            ]}},
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
                             "installedPackages": {"performance-manager": {}},
                             "staleLocks": 0},
               "subchecks": {name: True for name in GATE_CHECKS["target-core-only"]}}
        checks = evaluate_raw_facts(raw, "target-core-only")
        self.assertFalse(checks["capabilitiesValid"])
        self.assertTrue(all(value for name, value in checks.items() if name != "capabilitiesValid"))

    def test_resource_missing_release_metric_fails_closed(self):
        raw = {"rawFacts": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}},
                             "durationSeconds": 86400,
                             "soak": {"rillPresent": True, "sampleCount": 1, "coreRestartCount": 0,
                                       "rillRestartCount": 0, "idleRillObserveAcceptedDelta": 0,
                                       "idleExpectedAdapterPersistenceEventsDelta": 0,
                                       "idlePendingOutcomeJournalWrites": 0, "executingJournalDelta": 0,
                                       "resources": {}}}}
        checks = evaluate_raw_facts(raw, "resource-soak")
        self.assertFalse(checks["journalMeasured"])
        self.assertFalse(checks["stateBoundsPass"])

    def test_sysupgrade_same_pm_sha_with_changed_firmware_passes(self):
        sha = "a" * 64
        raw = {"rawFacts": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}}, "upgrade": {
            "transactionMarker": "sysupgrade-1", "before": {"bootId": "boot-a", "packageSha256": sha,
                "configSha256": "b" * 64, "policySha256": "c" * 64, "firmware": {"identity": "fw-a"}},
            "after": {"bootId": "boot-b", "packageSha256": sha, "configSha256": "b" * 64,
                "policySha256": "c" * 64, "adapterSha256": PIN, "pendingMutationCount": 0,
                "coreStarted": True, "staleLocks": 0, "firmware": {"identity": "fw-b"}}}}}
        checks = evaluate_raw_facts(raw, "sysupgrade")
        self.assertTrue(checks["firmwareUpgradeProven"])
        self.assertTrue(checks["configPreserved"])

    def test_lifecycle_observed_boolean_only_fails(self):
        raw = {"rawFacts": {"installedPackages": {"luci-app-performance-manager-all": {}, "performance-manager-rill-adapter": {}},
                             "lifecycle": {"steps": {name: {"exitCode": 0, "observed": True}
                                                        for name in GATE_CHECKS["lifecycle"]}}}}
        self.assertFalse(any(evaluate_raw_facts(raw, "lifecycle").values()))


if __name__ == "__main__":
    unittest.main()
