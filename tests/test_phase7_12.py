from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
CFG=(ROOT/'package/performance-manager/files/etc/config/performance-manager').read_text()
CONTRACTS=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text()

class Phase712Tests(unittest.TestCase):
    def function(self,name):
        # Extract a single function body by brace matching (skipping strings and
        # comments).  The shipped Core is reordered callee-before-caller to
        # remove forward references, so neighbouring-function slicing would be
        # unstable; each body is located and balanced independently.
        m=re.search(r'function '+re.escape(name)+r'\s*\(',CORE)
        self.assertIsNotNone(m,'function '+name+' not found in Core')
        start=m.start(); i=CORE.index('{',start); depth=0
        while i<len(CORE):
            c=CORE[i]
            if c=='`':
                i+=1
                while i<len(CORE):
                    if CORE[i]=='\\': i+=2; continue
                    if CORE[i]=='`': break
                    i+=1
                i+=1; continue
            if c in "'\"":
                q=c; i+=1
                while i<len(CORE):
                    if CORE[i]=='\\': i+=2; continue
                    if CORE[i]==q: break
                    i+=1
                i+=1; continue
            if c=='/' and CORE[i:i+2]=='//':
                i=CORE.index('\n',i); continue
            if c=='/' and CORE[i:i+2]=='/*':
                j=CORE.find('*/',i); i=(j+2) if j>=0 else len(CORE); continue
            if c=='{': depth+=1
            elif c=='}':
                depth-=1
                if depth==0: return CORE[start:i+1]
            i+=1
        return CORE[start:]
    def test_controlled_ab_is_transactional_and_rollback_first(self):
        body=self.function('benchmark_start')
        for call in ['companion_evidence_valid(', 'benchmark_apply_candidate(', 'rollback_transaction(session.transactionId', "measurementClass:'controlled_ab'"]:
            self.assertIn(call,body)
        candidate=body[body.index("phase == 'candidate'"):]
        self.assertLess(candidate.index("rollback_transaction(session.transactionId,'benchmark-complete')"),candidate.index('reward=(c1-c0)/c0'))
        self.assertIn("validated:true",candidate)
    def test_passive_measurements_never_claim_validation(self):
        body=self.function('benchmark_start')
        passive=body[body.rindex('let snap=telemetry_snapshot()'):]
        self.assertIn('validated:false',passive)
        self.assertIn('changedSystemState:false',passive)
    def test_benchmark_inventory_and_provider_boundary(self):
        plan=self.function('benchmark_provider_plan')
        actions=['service.irqbalance','network.backlog','network.budget','network.buffers','network.busy_poll','netdev.tx_queue_len','nic.coalescing','tcp.cc','qdisc.replace','fastpath.software_flow_offload','fastpath.hardware_flow_offload','fastpath.third_party_sfe','cpu.governor']
        for action in actions: self.assertIn(action,CORE+CONTRACTS)
        self.assertIn('exact-qdisc-restore-not-proven',plan)
        self.assertIn('no-generic-third-party-sfe-contract',plan)
        for action in set(actions)-{'qdisc.replace','fastpath.third_party_sfe'}: self.assertIn(action,plan)
    def test_rill_integration_is_external_and_fail_closed(self):
        # Rill is an external runtime: the Core never compiles/bundles it and
        # only drives it through a bounded capability/protocol gate.  A missing
        # runtime or contract/protocol mismatch is fail-closed, never assumed OK.
        self.assertIn("const RILL_RUNTIME_API_VERSION = 3",CORE)
        self.assertIn('RILL_RUNTIME_CAPABILITIES',CORE)
        self.assertIn('preview-serve',CORE)
        self.assertIn('external-runtime-not-provisioned',CORE)
        self.assertIn('runtime-version-mismatch',CORE)
        self.assertIn("state: RILL_STATES.incompatible",CORE)
        self.assertNotIn('cargo',(ROOT/'package/performance-manager-rill/Makefile').read_text())
        self.assertNotIn('rust',(ROOT/'package/performance-manager-rill/Makefile').read_text())
    def test_assisted_auto_is_double_opt_in(self):
        self.assertIn("option automation 'conservative'",CFG); self.assertIn("option assisted_auto '0'",CFG)
        body=self.function('assisted_auto_tick')
        for token in ["!= 'assisted'","bool_cfg('main.assisted_auto', false)",'in_maintenance_window()','system_guard()','index(SAFE_ACTIONS, action.id)']:
            self.assertIn(token,body)
        self.assertLess(body.index('let action = actions[0]'),body.index('assisted_low_traffic(current, target_ref?.runtimeName ?? null)'))
        self.assertIn('assisted_low_traffic(current, runtime)',CORE)
        self.assertIn('assisted-previous-',CORE)
        self.assertIn('resolve_target(action.applyTarget)',body)
    def test_topology_uses_route_evidence_and_rtnl_events(self):
        route=self.function('route_context')
        self.assertIn("'-j', '-4', 'route'",route); self.assertIn("'-j', '-4', 'rule', 'show'",route)
        self.assertIn('rtnl.listener(',CORE); self.assertIn('[ 16, 17, 24, 25 ]',CORE); self.assertIn('wanCandidates',CORE)
    def test_recovery_starts_after_uloop_init(self):
        self.assertLess(CORE.rindex('uloop.init();'),CORE.rindex('recover_pending();'))
        rec=self.function('recover_pending')
        self.assertIn("rollback_transaction(tx.transactionId, 'core-crash-recovery')",rec)
        self.assertIn('arm_tx_timer(tx)',rec)
if __name__=='__main__': unittest.main()
