import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ReleaseGateSourceTests(unittest.TestCase):
    def test_three_packages(self):
        for p in ['performance-manager','luci-app-performance-manager','performance-manager-rill']:
            self.assertTrue((ROOT/'package'/p/'Makefile').exists(),p)
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
