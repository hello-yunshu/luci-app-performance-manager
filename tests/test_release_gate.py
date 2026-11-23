import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import aggregate_stable_evidence as stable_evidence  # noqa: E402
class ReleaseGateSourceTests(unittest.TestCase):
    def test_resolve_jobs_get_repository_without_checkout(self):
        for name in ("stable-target-matrix", "stable-aggregate", "stable-release"):
            text = (ROOT / ".github/workflows" / f"{name}.yml").read_text()
            match = re.search(r"(?ms)^  resolve:\n(.*?)(?=^  \S|\Z)", text)
            self.assertIsNotNone(match, name)
            resolve = match.group(1)
            self.assertIn("gh run list", resolve, name)
            self.assertIn("GH_REPO: ${{ github.repository }}", resolve, name)

    def test_four_packages_include_real_all_in_one(self):
        for p in ['performance-manager','luci-app-performance-manager','performance-manager-rill',
                  'luci-app-performance-manager-all']:
            self.assertTrue((ROOT/'package'/p/'Makefile').exists(),p)
        bundle=(ROOT/'package/luci-app-performance-manager-all/Makefile').read_text()
        self.assertIn('po2lmo',bundle)
        self.assertIn('/usr/sbin/performance-manager.uc',bundle)
        self.assertIn('/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo',bundle)
        self.assertIn('luci-app-performance-manager/htdocs',bundle)
        self.assertIn('performance-manager-rill/files',bundle)
        self.assertIn('+rill-runtime', bundle)
        self.assertNotIn('+rill-runtime-preview', bundle)
        self.assertIn('PKG_RELEASE:=15', bundle)
        split_glue = (ROOT/'package/performance-manager-rill/Makefile').read_text()
        self.assertIn('PKG_RELEASE:=2', split_glue)
        self.assertNotIn('RILL_RUNTIME_BINARY', bundle)
        self.assertNotIn('PKGARCH:=all', bundle)
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

    def test_package_matcher_does_not_confuse_manager_with_runtime(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        from package_composition_gate import package_name
        self.assertEqual(package_name(Path('rill-runtime-v25.12.6-x86_64.apk')), 'rill-runtime')
        self.assertEqual(package_name(Path('rill-runtime-manager-1.0.0-r2.apk')), 'rill-runtime-manager')
        self.assertEqual(
            package_name(Path('luci-app-performance-manager-all-v1.0.7-openwrt-25.12.6-x86_64.apk')),
            'luci-app-performance-manager-all')

    def test_portable_pass_authorizes_stable_without_claiming_hardware(self):
        gates = {name: {"status": "PASS"} for name in stable_evidence.PORTABLE_REQUIRED}
        self.assertTrue(stable_evidence.stable_authorization("portable-docker", "PASS", gates))
        gates["portableDocker"]["status"] = "BLOCKED"
        self.assertFalse(stable_evidence.stable_authorization("portable-docker", "PASS", gates))
        hardware = {name: {"status": "PASS"} for name in stable_evidence.EXTERNAL_GATES}
        self.assertFalse(stable_evidence.stable_authorization("hardware", "BLOCKED", hardware))

    def test_hardware_authorization_requires_every_gate(self):
        gates = {name: {"status": "PASS"} for name in stable_evidence.EXTERNAL_GATES}
        self.assertTrue(stable_evidence.stable_authorization("hardware", "PASS", gates))
        gates["hyperV"]["status"] = "BLOCKED"
        self.assertFalse(stable_evidence.stable_authorization("hardware", "PASS", gates))
        gates["hyperV"]["status"] = "PASS"
        gates["resourceSoak12h"]["status"] = "FAIL"
        self.assertFalse(stable_evidence.stable_authorization("hardware", "PASS", gates))

    def test_portable_all_pass_authorizes_stable_with_hardware_not_evaluated(self):
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
        self.assertEqual(report["stableReleaseVerdict"], "PASS")
        self.assertEqual(report["hardwareCoverage"], "NOT_EVALUATED")
        self.assertTrue(report["stableReleaseAuthorized"])

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
        self.assertIn("gh release upload \"$tag\" release-public/* --clobber", release)
        self.assertIn("release-notes.md", release)
        self.assertNotIn("Hardware-validated", release)
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "1.0.7")
