from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
RILL=(ROOT/'package/performance-manager-rill/src/src/main.rs').read_text()
CFG=(ROOT/'package/performance-manager/files/etc/config/performance-manager').read_text()
CONTRACTS=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text()

class Phase712Tests(unittest.TestCase):
    def function(self,name,next_name=None):
        start=CORE.index('function '+name+'(')
        if next_name: return CORE[start:CORE.index('function '+next_name+'(',start)]
        return CORE[start:]
    def test_controlled_ab_is_transactional_and_rollback_first(self):
        body=self.function('benchmark_start','benchmark_list')
        for call in ['companion_evidence_valid(', 'benchmark_apply_candidate(', 'rollback_transaction(session.transactionId', "measurementClass:'controlled_ab'"]:
            self.assertIn(call,body)
        candidate=body[body.index("phase == 'candidate'"):]
        self.assertLess(candidate.index("rollback_transaction(session.transactionId,'benchmark-complete')"),candidate.index('reward=(c1-c0)/c0'))
        self.assertIn("validated:true",candidate)
    def test_passive_measurements_never_claim_validation(self):
        body=self.function('benchmark_start','benchmark_list')
        passive=body[body.rindex('let snap=telemetry_snapshot()'):]
        self.assertIn('validated:false',passive)
        self.assertIn('changedSystemState:false',passive)
    def test_benchmark_inventory_and_provider_boundary(self):
        plan=self.function('benchmark_provider_plan','benchmark_provider_apply')
        actions=['service.irqbalance','network.backlog','network.budget','network.buffers','network.busy_poll','netdev.tx_queue_len','nic.coalescing','tcp.cc','qdisc.replace','fastpath.software_flow_offload','fastpath.hardware_flow_offload','fastpath.third_party_sfe','cpu.governor']
        for action in actions: self.assertIn(action,CORE+CONTRACTS)
        self.assertIn('exact-qdisc-restore-not-proven',plan)
        self.assertIn('no-generic-third-party-sfe-contract',plan)
        for action in set(actions)-{'qdisc.replace','fastpath.third_party_sfe'}: self.assertIn(action,plan)
    def test_rill_state_is_persistent_bounded_and_advisory(self):
        self.assertIn('DEFAULT_STATE_DIR: &str = "/etc/performance-manager/rill"',RILL)
        for token in ['MAX_OUTCOME_LINES','MAX_LEDGER_LINES','MAX_STATE_FILE_BYTES','bounded_append','decision-ledger.jsonl','authority\\\":\\\"none']:
            self.assertIn(token,RILL)
        self.assertNotIn('Command::new',RILL)
    def test_assisted_auto_is_double_opt_in(self):
        self.assertIn("option automation 'conservative'",CFG); self.assertIn("option assisted_auto '0'",CFG)
        body=self.function('assisted_auto_tick','status')
        for token in ["!= 'assisted'","bool_cfg('main.assisted_auto', false)",'in_maintenance_window()','system_guard()','index(SAFE_ACTIONS, action.id)']:
            self.assertIn(token,body)
        self.assertLess(body.index('let action = actions[0]'),body.index('assisted_low_traffic(current, target_ref?.runtimeName ?? null)'))
        self.assertIn('assisted_low_traffic(current, runtime)',CORE)
        self.assertIn('assisted-previous-',CORE)
        self.assertIn('resolve_target(action.applyTarget)',body)
    def test_topology_uses_route_evidence_and_rtnl_events(self):
        route=self.function('route_context','topology')
        self.assertIn("'-j', '-4', 'route'",route); self.assertIn("'-j', '-4', 'rule', 'show'",route)
        self.assertIn('rtnl.listener(',CORE); self.assertIn('RTM_NEWROUTE',CORE); self.assertIn('wanCandidates',CORE)
    def test_recovery_starts_after_uloop_init(self):
        self.assertLess(CORE.rindex('uloop.init();'),CORE.rindex('recover_pending();'))
        rec=self.function('recover_pending','replay_policies')
        self.assertIn("rollback_transaction(tx.transactionId, 'core-crash-recovery')",rec)
        self.assertIn('arm_tx_timer(tx)',rec)
if __name__=='__main__': unittest.main()
