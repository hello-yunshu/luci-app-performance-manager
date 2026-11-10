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
