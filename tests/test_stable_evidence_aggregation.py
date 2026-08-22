import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from aggregate_stable_evidence import PINNED_ADAPTER_SHA, REQUIRED, RILL_PRESENT  # noqa: E402
from validate_external_evidence import GATE_CHECKS, validate_evidence  # noqa: E402


class StableEvidenceAggregationTests(unittest.TestCase):
    commit = "a" * 40

    def artifact(self, name):
        rec = {"apkSha256": {"performance-manager": "1", "luci-app-performance-manager": "2",
                             "performance-manager-rill": "3", "luci-app-performance-manager-all": "7"}[name] * 64,
               "version": "1.0.0_rc10-r1", "installedPayload": {}}
        if name == "performance-manager":
            rec["installedPayload"] = {"/usr/sbin/performance-manager.uc": "4" * 64,
                                       "/usr/share/performance-manager/contracts.uc": "5" * 64}
        return rec

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
            data["workflowRunId"] = "99"
            data["packages"] = {pkg: {"apkSha256": self.artifact(pkg)["apkSha256"],
                                      "pkgver": "1.0.0_rc10-r1",
                                      "installedPayload": self.artifact(pkg)["installedPayload"]}
                                for pkg in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", "luci-app-performance-manager-all")}
        elif name == "apkVerification":
            data["packages"] = {pkg: {"sha256": self.artifact(pkg)["apkSha256"]}
                                for pkg in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", "luci-app-performance-manager-all")}
        external = {
            "targetCoreOnly": "target-core-only", "targetFull": "target-full", "targetMutation": "target-mutation",
            "hyperV": "hyperv", "kvm": "kvm", "lanWanAb": "lan-wan-ab", "routerLocalAb": "router-local-ab",
            "sysupgrade": "sysupgrade", "lifecycle": "lifecycle", "resourceSoak24h": "resource-soak",
        }
        if name in external:
            gate = external[name]
            data.update({"schemaVersion": 1, "gate": gate, "buildRunId": "99",
                         "controller": {"source": "repository", "path": f"tools/stable-testbed/run-{gate}.sh", "sha256": "6" * 64},
                         "subchecks": {check: True for check in GATE_CHECKS[gate]},
                         "artifacts": {pkg: self.artifact(pkg) for pkg in ("performance-manager", "luci-app-performance-manager", "performance-manager-rill", "luci-app-performance-manager-all")}})
            if gate == "target-core-only":
                data["artifacts"]["luci-app-performance-manager"] = None
                data["artifacts"]["performance-manager-rill"] = None
                data["artifacts"]["luci-app-performance-manager-all"] = None
                data["primaryPackage"] = "performance-manager"
                data["primaryPackageSha256"] = data["artifacts"]["performance-manager"]["apkSha256"]
            else:
                data["primaryPackage"] = "luci-app-performance-manager-all"
                data["primaryPackageSha256"] = data["artifacts"]["luci-app-performance-manager-all"]["apkSha256"]
            if gate == "hyperv":
                data["environment"] = {"hypervisor": "Hyper-V", "nicDriver": "hv_netvsc", "vmbusId": "vmbus-1"}
            if gate == "kvm":
                data["environment"] = {"hypervisor": "KVM", "nicDriver": "virtio_net", "pciId": "0000:00:03.0"}
            if gate in {"lan-wan-ab", "router-local-ab"}:
                data["benchmark"] = {"controlMethodologyFingerprint": "method-1", "candidateMethodologyFingerprint": "method-1",
                                     "variableCount": 1, "validated": True, "reward": 0.1, "rillOutcome": "accepted",
                                     "routeResolved": True, "routeProvider": "ip-full+rtnl-events"}
            if gate == "sysupgrade":
                data["upgrade"] = {"beforeBootId": "boot-a", "afterBootId": "boot-b",
                                   "beforeVersion": "1.0.0_rc9-r1", "afterVersion": "1.0.0_rc10-r1"}
            if gate == "resource-soak":
                data["durationSeconds"] = 86400
                data["soak"] = {"sampleCount": 1440, "idleRillObserveAcceptedDelta": 0,
                                "idleExpectedAdapterPersistenceEventsDelta": 0, "idlePendingOutcomeJournalWrites": 0}
            raw = {"installedPackages": {"performance-manager": {}, "luci-app-performance-manager": {},
                                          "performance-manager-rill": {}, "luci-app-performance-manager-all": {}}}
            if gate == "target-core-only":
                raw = {"environment": {"release": "25.12.5", "target": "x86/64"},
                       "process": {"corePid": 1}, "ubusSocketReady": True,
                       "statusResponseValid": True, "analyzeResponseValid": True,
                       "topologyEvidenceValid": True, "capabilitiesEvidenceValid": True,
                       "staleLocks": 0, "installedPackages": {"performance-manager": {}}}
            elif gate == "target-full":
                raw.update({"permissions": {"serviceUid": 5666, "serviceUserDedicated": True,
                                             "stateDirectoryMode": "0750",
                                             "stateDirectoryOwner": "performance-manager-rill:performance-manager-rill"},
                            "rill": {"adapterSha256": PINNED_ADAPTER_SHA, "connectedToCore": True,
                                     "statusResponse": {"ready": True}},
                            "rillDirectMutationCount": 0, "mutationAuthority": "pm-core"})
            elif gate == "target-mutation":
                raw["mutation"] = {"candidate": {"actionId": "nic.ring.floor", "authority": "advisory-only", "mutationOwner": "pm-core"},
                                    "before": {"rx": 1}, "applyExitCode": 0,
                                    "readback": {"rx": 2}, "candidateState": {"rx": 2},
                                    "rollbackExitCode": 0, "afterRollback": {"rx": 1},
                                    "secondApplyExitCode": 0, "staleLocks": 0, "stalePolicies": 0,
                                    "ownershipAfter": "clean", "packetSteeringOwner": "native",
                                    "staleRuntimeState": 0}
            elif gate == "hyperv":
                raw.update({"environment": {"hypervisor": "Hyper-V", "vmbusId": "vmbus-1", "nicDriver": "hv_netvsc"},
                            "hotplug": {"before": "a", "after": "b"}, "targetRefStableId": True,
                            "replayCount": 1, "rollback": {"before": {"x": 1}, "after": {"x": 1}}})
            elif gate == "kvm":
                raw.update({"environment": {"hypervisor": "KVM", "pciId": "0000:00:03.0", "nicDriver": "virtio_net"},
                            "hotplug": {"before": "a", "after": "b"}, "targetRefStableId": True,
                            "replayCount": 1, "rollback": {"before": {"x": 1}, "after": {"x": 1}}})
            elif gate in {"lan-wan-ab", "router-local-ab"}:
                benchmark = {"control": {"bitsPerSecond": 100, "methodology": {"tool": "iperf3", "duration": 10}},
                             "candidate": {"bitsPerSecond": 110, "methodology": {"tool": "iperf3", "duration": 10}},
                             "mutation": {"changedFields": ["ring.rx"], "applyExitCode": 0, "before": {"x": 1},
                                           "candidate": {"x": 2}, "readback": {"x": 2}, "afterRollback": {"x": 1}},
                             "health": {"before": {"lan": True}, "after": {"lan": True}, "regressions": []},
                             "validated": True, "reward": 0.1,
                             "rill": {"outcome": {"response": {"ok": True, "accepted": True}}},
                             "client": {"role": "router-local-client" if gate == "router-local-ab" else "lan-client"},
                             "endpoint": {"kind": "router-local" if gate == "router-local-ab" else "wan"}}
                if gate == "lan-wan-ab": benchmark["route"] = {"resolved": True, "provider": "ip-full+rtnl-events"}
                raw["benchmark"] = benchmark
            elif gate == "sysupgrade":
                raw["upgrade"] = {"before": {"bootId": "boot-a", "packageSha256": "a", "configSha256": "c", "policySha256": "p"},
                                   "after": {"bootId": "boot-b", "packageSha256": "b", "configSha256": "c", "policySha256": "p",
                                             "adapterSha256": PINNED_ADAPTER_SHA, "pendingMutationCount": 0,
                                             "coreStarted": True, "staleLocks": 0}}
            elif gate == "lifecycle":
                raw["lifecycle"] = {"steps": {name: {"exitCode": 0, "observed": True} for name in GATE_CHECKS[gate]}}
            elif gate == "resource-soak":
                raw["durationSeconds"] = 86400
                raw["soak"] = {"rillPresent": True, "sampleCount": 1440, "coreRestartCount": 0, "rillRestartCount": 0,
                               "idleRillObserveAcceptedDelta": 0, "idleExpectedAdapterPersistenceEventsDelta": 0,
                               "idlePendingOutcomeJournalWrites": 0, "executingJournalDelta": 0,
                               "resources": {"coreRssKiB": 1000, "rillRssKiB": 1000, "bindingHighWater": 1,
                                             "interventionRequiredCount": 0, "persistentHistoryGrowthBytes": 1}}
            data["rawFacts"] = raw
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

    def test_minimal_pass_envelope_fails_every_external_gate(self):
        minimal = {"pmCommitSha": self.commit, "verdict": "PASS", "passed": True,
                   "adapterSha256": PINNED_ADAPTER_SHA}
        for gate in ("hyperv", "kvm", "lan-wan-ab", "router-local-ab", "sysupgrade", "lifecycle", "resource-soak"):
            with self.subTest(gate=gate):
                self.assertTrue(validate_evidence(minimal, gate, self.commit))

    def test_semantic_contradictions_fail(self):
        hyperv = self.evidence("hyperV")
        hyperv["environment"]["nicDriver"] = "virtio_net"
        self.assertIn("Hyper-V semantic identity invalid", validate_evidence(hyperv, "hyperv", self.commit))
        ab = self.evidence("lanWanAb")
        ab["benchmark"]["candidateMethodologyFingerprint"] = "other"
        self.assertIn("A/B methodology fingerprints differ", validate_evidence(ab, "lan-wan-ab", self.commit))
        upgrade = self.evidence("sysupgrade")
        upgrade["upgrade"]["afterBootId"] = "boot-a"
        self.assertIn("sysupgrade boot identity did not change", validate_evidence(upgrade, "sysupgrade", self.commit))
        soak = self.evidence("resourceSoak24h")
        soak["soak"]["sampleCount"] = 0
        self.assertIn("24h soak duration/sample evidence invalid", validate_evidence(soak, "resource-soak", self.commit))


if __name__ == "__main__":
    unittest.main()
