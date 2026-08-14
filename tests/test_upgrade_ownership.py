import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
MAKE=(ROOT/'package/performance-manager/Makefile').read_text()
KEEP=(ROOT/'package/performance-manager/files/lib/upgrade/keep.d/performance-manager').read_text()
RILL_KEEP=(ROOT/'package/performance-manager-rill/files/lib/upgrade/keep.d/performance-manager-rill').read_text()

class UpgradeOwnershipTests(unittest.TestCase):
    def test_sysupgrade_keeps_only_intended_state_roots(self):
        self.assertIn('/etc/config/performance-manager',KEEP)
        self.assertIn('/etc/performance-manager/',KEEP)
        self.assertIn('/etc/performance-manager/rill/',RILL_KEEP)
        self.assertNotIn('/tmp/performance-manager',KEEP)

    def test_package_remove_invokes_root_cleanup(self):
        self.assertIn('define Package/performance-manager/prerm',MAKE)
        self.assertIn("ubus call performance-manager cleanup",MAKE)
        self.assertIn('$${IPKG_INSTROOT}',MAKE)
        self.assertIn('$${PKG_UPGRADE:-0}',MAKE)

    def test_prerm_is_fail_closed_on_remove(self):
        body=MAKE[MAKE.index('define Package/performance-manager/prerm'):MAKE.index('define Build/Compile')]
        self.assertIn('[ -x /usr/sbin/performance-manager.uc ] || exit 0',body)
        self.assertIn('grep -q \'"ok":true\'',body)
        self.assertIn('exit 1',body)
        self.assertNotIn('|| true\nexit 0',body)
        self.assertIn('start the service and retry removal',body)

    def test_cleanup_requires_current_owned_runtime_lease(self):
        body=CORE[CORE.index('function cleanup_owned'):CORE.index('function replay_policies')]
        self.assertIn("lease.bootId != boot_id()",body)
        self.assertIn("!ring_matches(ref,lease.ownedRing)",body)
        self.assertIn("live-drift-preserved-intent-removed",body)
        self.assertIn("ring_restore(ref,lease.beforeRing)",body)

    def test_replay_refreshes_runtime_lease(self):
        body=CORE[CORE.index('function replay_policies'):CORE.index('function benchmark_path')]
        self.assertIn('runtimeLease={bootId:boot_id()',body)
        self.assertIn('lease-persist-failed',body)
        self.assertIn('ring_restore(ref,before)',body)

    def test_sysupgrade_target_gate_requires_real_reboot(self):
        gate=(ROOT/'scripts/openwrt-sysupgrade-gate.sh').read_text()
        self.assertIn('prepare|verify', gate)
        self.assertIn('[ "$now_boot" != "$boot_id" ]', gate)
        self.assertIn('core-persistent-root-survived', gate)
        self.assertIn('rill-persistent-root-survived', gate)
        self.assertIn('no-stale-pending-marker', gate)


    def test_target_gate_can_require_core_only_and_mutation_candidate(self):
        gate=(ROOT/'scripts/openwrt-target-gate.sh').read_text()
        self.assertIn('PM_REQUIRE_CORE_ONLY', gate)
        self.assertIn('core-with-luci-absent', gate)
        self.assertIn('core-with-rill-absent', gate)
        self.assertIn('fail legal-conservative-ring-candidate', gate)


if __name__=='__main__': unittest.main()
