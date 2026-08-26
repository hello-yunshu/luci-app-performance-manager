import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools/stable-testbed"))
from artifact_identity import ArtifactIdentityError, resolve_artifact  # noqa: E402
from validate_external_evidence import GATE_CHECKS, PIN  # noqa: E402


PACKAGE_NAMES = ("performance-manager", "luci-app-performance-manager",
                 "performance-manager-rill", "performance-manager-rill-adapter",
                 "luci-app-performance-manager-all")
GATES = ("target-core-only", "target-full", "target-mutation", "hyperv", "kvm",
         "lan-wan-ab", "router-local-ab", "sysupgrade", "lifecycle", "resource-soak")


class ReleaseClosureE2ETests(unittest.TestCase):
    commit = "a" * 40

    def _package_records(self, root: Path):
        records = {}
        for index, name in enumerate(PACKAGE_NAMES, 1):
            filename = f"{name}-1.0.0-r1.apk"
            source = root / "build" / "full" / filename
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f"exact-{name}".encode())
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            records[name] = {
                "apkFilename": filename, "apkSha256": digest, "pkgver": "1.0.0-r1",
                "installedPayload": {
                    "/usr/sbin/performance-manager.uc": "b" * 64,
                    "/usr/share/performance-manager/contracts.uc": "c" * 64,
                    "/etc/init.d/performance-manager": "d" * 64,
                    "/etc/init.d/performance-manager-rill": "e" * 64,
                    "/usr/share/rpcd/acl.d/luci-app-performance-manager.json": "f" * 64,
                    "/usr/share/luci/menu.d/luci-app-performance-manager.json": "1" * 64,
                    "/www/luci-static/resources/view/performance-manager/overview.js": "2" * 64,
                    "/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo": "3" * 64,
                } if name in {"performance-manager", "luci-app-performance-manager-all"} else {},
            }
        # This is the legal duplicate: dedicated and full workflow artifacts
        # contain byte-identical copies of the same public APK.
        dedicated = root / "build" / "dedicated" / records[PACKAGE_NAMES[-1]]["apkFilename"]
        dedicated.parent.mkdir(parents=True, exist_ok=True)
        dedicated.write_bytes((root / "build" / "full" / dedicated.name).read_bytes())
        return records

    def _raw_facts(self, gate, records):
        installed_name = "performance-manager" if gate == "target-core-only" else PACKAGE_NAMES[-1]
        raw = {"installedPackages": {installed_name: {
            "apkSha256": records[installed_name]["apkSha256"], "version": "1.0.0-r1",
            "installedPayload": records[installed_name]["installedPayload"],
        }}}
        if gate != "target-core-only":
            raw["installedPackages"]["performance-manager-rill-adapter"] = {
                "apkSha256": records["performance-manager-rill-adapter"]["apkSha256"],
                "version": "1.0.0-r1", "installedPayload": {},
            }
        if gate == "target-core-only":
            raw.update({"environment": {"release": "25.12.5", "target": "x86/64"},
                        "process": {"corePid": 1}, "ubusSocketReady": True,
                        "statusResponseValid": True, "analyzeResponseValid": True,
                        "topologyEvidenceValid": True, "capabilitiesEvidenceValid": True,
                        "staleLocks": 0})
        elif gate == "target-full":
            raw.update({"permissions": {"serviceUid": 5666, "serviceUserDedicated": True,
                                         "stateDirectoryMode": "0750",
                                         "stateDirectoryOwner": "performance-manager-rill:performance-manager-rill"},
                        "rill": {"adapterSha256": PIN, "connectedToCore": True,
                                 "statusResponse": {"ready": True}},
                        "rillDirectMutationCount": 0, "mutationAuthority": "pm-core"})
        elif gate == "target-mutation":
            raw["mutation"] = {"candidate": {"actionId": "nic.ring.floor", "authority": "advisory-only", "mutationOwner": "pm-core", "targetStableId": "stable-1", "rx": 1024, "tx": 1024},
                                "before": {"rx": 512, "tx": 512}, "applyExitCode": 0,
                                "readback": {"rx": 1024, "tx": 1024}, "candidateState": {"rx": 1024, "tx": 1024},
                                "rollbackExitCode": 0, "afterRollback": {"rx": 512, "tx": 512},
                                "secondApplyExitCode": 0, "staleLocks": 0, "stalePolicies": 0,
                                "ownershipAfter": "clean", "packetSteeringOwner": "native", "staleRuntimeState": 0}
        elif gate == "hyperv":
            raw.update({"environment": {"hypervisor": "Hyper-V", "vmbusId": "vmbus-1", "nicDriver": "hv_netvsc"},
                        "hotplug": {"before": "a", "after": "b"}, "targetRefStableId": True,
                        "replayCount": 1, "rollback": {"before": {"x": 1}, "after": {"x": 1}}})
        elif gate == "kvm":
            raw.update({"environment": {"hypervisor": "KVM", "pciId": "0000:00:03.0", "nicDriver": "virtio_net"},
                        "hotplug": {"before": "a", "after": "b"}, "targetRefStableId": True,
                        "replayCount": 1, "rollback": {"before": {"x": 1}, "after": {"x": 1}}})
        elif gate in {"lan-wan-ab", "router-local-ab"}:
            methodology = {"tool": "iperf3", "protocol": "tcp", "durationSeconds": 10, "direction": "forward",
                           "clientIdentity": "lan-client-1", "endpointIdentity": "wan-endpoint-1", "streamCount": 1, "payloadMode": "throughput"}
            benchmark = {"control": {"bitsPerSecond": 100, "methodology": methodology},
                         "candidate": {"bitsPerSecond": 110, "methodology": dict(methodology)},
                         "mutation": {"action": {"actionId": "nic.ring.floor", "authority": "advisory-only", "mutationOwner": "pm-core"},
                                       "changedFields": ["ring.rx"], "applyExitCode": 0,
                                       "before": {"rx": 512, "tx": 512}, "candidate": {"rx": 1024, "tx": 1024}, "readback": {"rx": 1024, "tx": 1024},
                                       "afterRollback": {"rx": 512, "tx": 512}},
                         "health": {"before": {"lan": True}, "after": {"lan": True}, "regressions": []},
                         "validated": True, "reward": 0.1,
                         "rill": {"outcome": {"response": {"ok": True, "accepted": True}}},
                         "client": {"role": "router-local-client" if gate == "router-local-ab" else "lan-client"},
                         "endpoint": {"kind": "router-local" if gate == "router-local-ab" else "wan"}}
            if gate == "lan-wan-ab":
                benchmark["route"] = {"resolved": True, "provider": "ip-full+rtnl-events"}
            raw["benchmark"] = benchmark
        elif gate == "sysupgrade":
            raw["upgrade"] = {"transactionMarker": "sysupgrade-1", "before": {"bootId": "boot-a", "packageSha256": "1" * 64,
                                           "configSha256": "2" * 64, "policySha256": "3" * 64, "firmware": {"identity": "fw-a"}},
                               "after": {"bootId": "boot-b", "packageSha256": records[PACKAGE_NAMES[-1]]["apkSha256"],
                                         "configSha256": "2" * 64, "policySha256": "3" * 64,
                                         "adapterSha256": PIN, "pendingMutationCount": 0,
                                         "coreStarted": True, "staleLocks": 0, "firmware": {"identity": "fw-b"}}}
        elif gate == "lifecycle":
            raw["lifecycle"] = {"phases": [
                {"name": "split-install", "exitCode": 0, "installedPackages": {"performance-manager": {}, "luci-app-performance-manager": {}, "performance-manager-rill": {}, "performance-manager-rill-adapter": {}}, "configSha256": "2" * 64},
                {"name": "split-runtime", "corePid": 1, "ubusReady": True, "rillAdapterSha256": PIN},
                {"name": "migration", "removeExitCode": 0, "installBundleExitCode": 0, "installedPackages": {PACKAGE_NAMES[-1]: {}, "performance-manager-rill-adapter": {}}},
                {"name": "bundle-runtime", "corePid": 2, "ubusReady": True, "configSha256": "2" * 64},
                {"name": "uninstall", "exitCode": 0, "remainingOwnedPaths": [], "staleLocks": 0, "stalePending": 0, "staleSockets": 0},
                {"name": "reinstall", "exitCode": 0, "installedPackages": {PACKAGE_NAMES[-1]: {}, "performance-manager-rill-adapter": {}}, "corePid": 3, "ubusReady": True},
            ]}
        elif gate == "resource-soak":
            raw["durationSeconds"] = 86400
            raw["soak"] = {"rillPresent": True, "sampleCount": 1440, "coreRestartCount": 0,
                           "rillRestartCount": 0, "idleRillObserveAcceptedDelta": 0,
                           "idleExpectedAdapterPersistenceEventsDelta": 0,
                           "idlePendingOutcomeJournalWrites": 0, "executingJournalDelta": 0,
                           "resources": {"coreRssKiB": 1000, "rillRssKiB": 1000,
                                         "bindingHighWater": 1, "interventionRequiredCount": 0,
                                         "persistentHistoryGrowthBytes": 1, "executionJournalFileCount": 1,
                                         "executionJournalBytes": 1024, "retiredExecutionCount": 1,
                                         "activeExecutionCount": 0, "executingExecutionCount": 0}}
        return raw

    def test_controller_validator_and_aggregate_use_one_rawfacts_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = self._package_records(root)
            build = {"repositoryCommitSha": self.commit, "workflowRunId": "77", "verdict": "PASS",
                     "verdicts": {"pmPackagesBuildVerdict": "PASS", "apkExactVerificationVerdict": "PASS"},
                     "openwrtVersion": "25.12.5", "packages": records}
            apk = {"pmCommitSha": self.commit, "verdict": "PASS",
                   "packages": {name: {"sha256": rec["apkSha256"], "status": "ok"}
                                 for name, rec in records.items()}}
            build_root = root / "build"
            build_root.mkdir(exist_ok=True)
            (build_root / "build-metadata.json").write_text(json.dumps(build))
            (build_root / "apk-verification.json").write_text(json.dumps(apk))
            facts = {gate: self._raw_facts(gate, records) for gate in GATES}
            facts_path = root / "facts.json"
            facts_path.write_text(json.dumps(facts))
            transport = root / "transport.py"
            transport.write_text(
                f"#!/usr/bin/env python3\nimport json,sys\nrequest=json.load(sys.stdin)\n"
                f"raw=json.load(open({str(facts_path)!r}))[request['gate']]\n"
                "print(json.dumps({'rawFacts':raw}))\n"
            )
            transport.chmod(transport.stat().st_mode | stat.S_IXUSR)
            evidence_root = root / "evidence"
            evidence_root.mkdir()
            for gate in GATES:
                env = {**os.environ, "PM_EXPECTED_SHA": self.commit,
                       "PM_BUILD_INPUT": str(build_root), "PM_CI_INPUT": str(root / "ci"),
                       "PM_EVIDENCE_OUT": str(evidence_root / f"{gate}.json"),
                       "PM_TESTBED_TRANSPORT": str(transport)}
                completed = subprocess.run([
                    sys.executable, str(ROOT / "tools/stable-testbed/controller.py"),
                    "--gate", gate, "--controller-path", "tools/stable-testbed/controller.py"],
                    env=env, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, f"{gate}: {completed.stderr}")
                self.assertEqual(json.loads((evidence_root / f"{gate}.json").read_text())["verdict"], "PASS")

            # Feed the real controller outputs, plus the non-target same-commit
            # evidence envelope, into the repository aggregate.
            support = {
                "source-audit.json": {"pmCommitSha": self.commit, "sourceCandidateVerdict": "PASS"},
                "core-runtime.json": {"pmCommitSha": self.commit, "verdict": "PASS"},
                "rill-provenance.json": {"pmCommitSha": self.commit, "provenanceVerdict": "PASS", "adapterSha256": PIN},
                "rill-runtime.json": {"pmCommitSha": self.commit, "overallVerdict": "PASS", "adapterSha256": PIN},
                "rill-core-integration.json": {"pmCommitSha": self.commit, "verdict": "PASS", "adapterSha256": PIN},
            }
            for name, value in support.items():
                (evidence_root / name).write_text(json.dumps(value))
            (evidence_root / "build-metadata.json").write_text(json.dumps(build))
            (evidence_root / "apk-verification.json").write_text(json.dumps(apk))
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/aggregate_stable_evidence.py"),
                "--evidence-dir", str(evidence_root), "--expected-commit", self.commit,
                "--out", str(root / "final-stable-evidence.json"),
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            final = json.loads((root / "final-stable-evidence.json").read_text())
            self.assertEqual(final["overallVerdict"], "PASS")
            self.assertTrue(final["stableReleaseAuthorized"])

    def test_conflicting_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "one" / "luci-app-performance-manager-all-1.0.0-r1.apk"
            second = root / "two" / first.name
            first.parent.mkdir(); second.parent.mkdir()
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            with self.assertRaises(ArtifactIdentityError):
                resolve_artifact("luci-app-performance-manager-all", hashlib.sha256(b"one").hexdigest(), [root], first.name)


if __name__ == "__main__":
    unittest.main()
