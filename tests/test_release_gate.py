import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import aggregate_stable_evidence as stable_evidence  # noqa: E402
class ReleaseGateSourceTests(unittest.TestCase):
    def test_four_packages_include_real_all_in_one(self):
        for p in ['performance-manager','luci-app-performance-manager','performance-manager-rill',
                  'luci-app-performance-manager-all']:
            self.assertTrue((ROOT/'package'/p/'Makefile').exists(),p)
        bundle=(ROOT/'package/luci-app-performance-manager-all/Makefile').read_text()
        self.assertIn('po2lmo',bundle)
        self.assertIn('/usr/sbin/performance-manager.uc',bundle)
        self.assertIn('/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo',bundle)
        self.assertIn('luci-app-performance-manager/htdocs',bundle)
        self.assertNotIn('performance-manager-rill/files',bundle)
        self.assertNotIn('+performance-manager ',bundle)
        self.assertNotIn('+luci-app-performance-manager',bundle)
    def test_core_independent(self):
        m=(ROOT/'package/performance-manager/Makefile').read_text()
        self.assertNotIn('+rpcd',m); self.assertNotIn('+luci-base',m); self.assertNotIn('+performance-manager-rill',m)
    def test_native_packet_steering_respected(self):
        s=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
        self.assertIn("policy: 'observe-respect'",s)
        self.assertIn('/usr/libexec/network/packet-steering.uc',s)
    def test_safe_direct_apply_is_ring_only(self):
        s=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text()
        self.assertIn("SAFE_ACTIONS = [ 'nic.ring.floor' ]",s)

    def test_portable_pass_never_authorizes_stable(self):
        gates = {name: {"status": "PASS"} for name in stable_evidence.EXTERNAL_GATES}
        self.assertFalse(stable_evidence.stable_authorization("portable-docker", "PASS", gates))
        self.assertFalse(stable_evidence.stable_authorization("hardware", "BLOCKED", gates))

    def test_hardware_authorization_requires_every_gate(self):
        gates = {name: {"status": "PASS"} for name in stable_evidence.EXTERNAL_GATES}
        self.assertTrue(stable_evidence.stable_authorization("hardware", "PASS", gates))
        gates["hyperV"]["status"] = "BLOCKED"
        self.assertFalse(stable_evidence.stable_authorization("hardware", "PASS", gates))
        gates["hyperV"]["status"] = "PASS"
        gates["resourceSoak24h"]["status"] = "FAIL"
        self.assertFalse(stable_evidence.stable_authorization("hardware", "PASS", gates))

    def test_portable_all_pass_is_not_a_stable_result(self):
        commit = "a" * 40
        runtime_sha = "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = {
                "source-audit.json": {"sourceCandidateVerdict": "PASS", "pmCommitSha": commit},
                "rill-provenance.json": {"provenanceVerdict": "PASS", "pmCommitSha": commit,
                                         "runtimeSha256": runtime_sha},
                "rill-runtime.json": {"overallVerdict": "PASS", "pmCommitSha": commit,
                                       "runtimeSha256": runtime_sha},
                "rill-core-integration.json": {"overallVerdict": "PASS", "pmCommitSha": commit,
                                                "runtimeSha256": runtime_sha},
                "build-metadata.json": {"verdicts": {"pmPackagesBuildVerdict": "PASS"},
                                         "repositoryCommitSha": commit},
                "apk-verification.json": {"verdict": "PASS", "pmCommitSha": commit},
                "portable-docker.json": {"verdict": "PASS", "pmCommitSha": commit},
                "package-composition.json": {"verdict": "PASS", "pmCommitSha": commit},
            }
            for filename, payload in fixtures.items():
                (root / filename).write_text(json.dumps(payload))
            output = root / "final-stable-evidence.json"
            result = stable_evidence.main([
                "--evidence-dir", str(root), "--expected-commit", commit,
                "--profile", "portable-docker", "--out", str(output),
            ])
            report = json.loads(output.read_text())
        self.assertEqual(result, 0)
        self.assertEqual(report["portableVerdict"], "PASS")
        self.assertEqual(report["stableReleaseVerdict"], "NOT_EVALUATED")
        self.assertEqual(report["hardwareCoverage"], "NOT_EVALUATED")
        self.assertFalse(report["stableReleaseAuthorized"])

    def test_stable_profile_routing_accepts_only_matching_target_workflow(self):
        aggregate = (ROOT / ".github/workflows/stable-aggregate.yml").read_text()
        self.assertIn('inputs.profile', aggregate)
        self.assertIn('portable-docker', aggregate)
        self.assertIn("target_workflow='Portable validation matrix'", aggregate)
        self.assertIn('hardware', aggregate)
        self.assertIn("target_workflow='Hardware validation matrix'", aggregate)
        self.assertIn("unsupported evidence profile", aggregate)
        self.assertIn("target_workflow_path='.github/workflows/stable-target-matrix.yml'", aggregate)
        self.assertIn("target_workflow_path='.github/workflows/hardware-validation.yml'", aggregate)

    def test_public_release_is_immutable_and_new_version_is_selected_from_source(self):
        release = (ROOT / ".github/workflows/stable-release.yml").read_text()
        self.assertIn("remote_tag=", release)
        self.assertIn("exists and is public; refusing mutation", release)
        self.assertIn("gh release upload \"$tag\" release-assets/* --clobber", release)
        self.assertIn("Hardware-validated", release)
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "1.0.4")
