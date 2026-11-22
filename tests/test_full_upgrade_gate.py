import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from full_upgrade_gate import (UPGRADE_BOOLEAN_KEYS, apk_version_key,
                                evaluate_upgrade_flags, transport_status)


class FullUpgradeGateTests(unittest.TestCase):
    def flags(self):
        return {key: True for key in UPGRADE_BOOLEAN_KEYS}

    def test_lower_prior_version_is_required(self):
        self.assertLess(apk_version_key("1.0.3-r1"), apk_version_key("1.0.4-r1"))
        self.assertEqual(evaluate_upgrade_flags(self.flags()), "PASS")

    def test_every_upgrade_assertion_fails_closed(self):
        for key in UPGRADE_BOOLEAN_KEYS:
            flags = self.flags()
            flags[key] = False
            self.assertEqual(evaluate_upgrade_flags(flags), "FAIL", key)

    def test_missing_upgrade_assertion_is_not_a_pass(self):
        flags = self.flags()
        del flags["runtimeUpdated"]
        self.assertEqual(evaluate_upgrade_flags(flags), "FAIL")

    def test_same_version_is_not_lower(self):
        self.assertGreaterEqual(apk_version_key("1.0.4-r1"), apk_version_key("1.0.4-r1"))

    def test_package_validation_baseline_matches_supported_apk_release(self):
        workflow_paths = (
            ROOT / ".github/workflows/stable-target-matrix.yml",
            ROOT / ".github/workflows/hardware-validation.yml",
        )
        for path in workflow_paths:
            with self.subTest(path=path.name):
                self.assertIn('OPENWRT_VERSION: "25.12.6"', path.read_text())
        self.assertIn('"openwrtVersion": "25.12.6"',
                      (ROOT / "scripts/full_upgrade_gate.py").read_text())

    def test_exact_apks_are_staged_inside_the_chroot(self):
        import hashlib
        import tempfile

        import full_upgrade_gate

        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            rootfs = temp / "rootfs"
            rootfs.mkdir()
            prior_apk = temp / "luci-app-performance-manager-all-1.0.3-r1.apk"
            current_apk = temp / "luci-app-performance-manager-all-1.0.7-r7.apk"
            prior_apk.write_bytes(b"prior")
            current_apk.write_bytes(b"current")
            digest = "b" * 64
            luci_paths = (
                "/www/luci-static/resources/view/performance-manager/overview.js",
                "/usr/share/luci/menu.d/luci-app-performance-manager.json",
                "/usr/share/rpcd/acl.d/luci-app-performance-manager.json",
            )
            build = {"packages": {full_upgrade_gate.PACKAGE: {
                "pkgver": "1.0.7-r7",
                "apkSha256": sha(current_apk),
                "installedPayload": {
                    path: digest
                    for path in (full_upgrade_gate.CORE_PATH, *luci_paths)
                },
                "runtimeBinary": {"sha256": digest},
            }}}
            prior = {
                "pkgver": "1.0.3-r1",
                "sha256": sha(prior_apk),
                "syntheticPriorFixture": True,
                "historicalReleaseUpgrade": False,
            }
            original_run = full_upgrade_gate.run
            full_upgrade_gate.run = lambda root, command: subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="")
            try:
                full_upgrade_gate.execute(rootfs, prior_apk, current_apk, prior,
                                          build, "0" * 40)
            finally:
                full_upgrade_gate.run = original_run
            staged = rootfs / "tmp/pm-full-upgrade"
            # apk resolves package paths inside the chroot; both exact APKs
            # must exist there or the solver reports "(no such package)".
            self.assertTrue((staged / prior_apk.name).is_file())
            self.assertTrue((staged / current_apk.name).is_file())

    def test_generic_wget_ssl_transport_error_is_unavailable(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=4, stdout="",
            stderr="wgetSSL error: ERROR - Generic error\nunexpected end of file",
        )
        self.assertEqual(transport_status(completed), "unavailable")

    def test_explicit_certificate_failure_is_tls_failure(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=4, stdout="",
            stderr="certificate verify failed: unable to get local issuer certificate",
        )
        self.assertEqual(transport_status(completed), "tls-failure")


if __name__ == "__main__":
    unittest.main()
