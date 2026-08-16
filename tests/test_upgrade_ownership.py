import unittest
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
MAKE=(ROOT/'package/performance-manager/Makefile').read_text()
KEEP=(ROOT/'package/performance-manager/files/lib/upgrade/keep.d/performance-manager').read_text()
RILL_KEEP=(ROOT/'package/performance-manager-rill/files/lib/upgrade/keep.d/performance-manager-rill').read_text()

def function_body(src,name):
    # Single-function body extraction by brace matching (skipping strings and
    # comments).  The shipped Core is reordered callee-before-caller, so
    # neighbouring-function slicing would be unstable.
    m=re.search(r'function '+re.escape(name)+r'\s*\(',src)
    if not m: raise KeyError('function '+name+' not found')
    start=m.start(); i=src.index('{',start); depth=0
    while i<len(src):
        c=src[i]
        if c=='`':
            i+=1
            while i<len(src):
                if src[i]=='\\': i+=2; continue
                if src[i]=='`': break
                i+=1
            i+=1; continue
        if c in "'\"":
            q=c; i+=1
            while i<len(src):
                if src[i]=='\\': i+=2; continue
                if src[i]==q: break
                i+=1
            i+=1; continue
        if c=='/' and src[i:i+2]=='//':
            i=src.index('\n',i); continue
        if c=='/' and src[i:i+2]=='/*':
            j=src.find('*/',i); i=(j+2) if j>=0 else len(src); continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return src[start:i+1]
        i+=1
    return src[start:]

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
        body=function_body(CORE,'cleanup_owned')
        self.assertIn("lease.bootId != boot_id()",body)
        self.assertIn("!ring_matches(ref,lease.ownedRing)",body)
        self.assertIn("live-drift-preserved-intent-removed",body)
        self.assertIn("ring_restore(ref,lease.beforeRing)",body)

    def test_replay_refreshes_runtime_lease(self):
        body=function_body(CORE,'replay_policies')
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
