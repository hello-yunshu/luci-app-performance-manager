import json
import sys
import unittest
from pathlib import Path
import jsonschema

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from contract_model import recovery_decision, validate_companion_evidence, controlled_ab_reward, health_regressions, ownership_cleanup_decision

class RuntimeContractModelTests(unittest.TestCase):
    def test_commit_confirm_recovery_matrix(self):
        base={"bootId":"boot-a"}
        self.assertEqual(recovery_decision({**base,"state":"pending"},"boot-a",1000),"rollback-core-crash")
        self.assertEqual(recovery_decision({**base,"state":"applied"},"boot-a",1000),"rollback-core-crash")
        self.assertEqual(recovery_decision({**base,"state":"verified"},"boot-a",1000),"rollback-core-crash")
        self.assertEqual(recovery_decision({**base,"state":"awaiting_confirm","deadlineMonotonicMs":2000},"boot-a",1000),"rearm-timer")
        self.assertEqual(recovery_decision({**base,"state":"awaiting_confirm","deadlineMonotonicMs":1000},"boot-a",1000),"rollback-timeout")
        self.assertEqual(recovery_decision({**base,"state":"awaiting_confirm","deadlineMonotonicMs":None},"boot-a",1000),"rollback-missing-deadline")
        self.assertEqual(recovery_decision({**base,"state":"pending"},"boot-b",1000),"cross-boot-clear-marker-no-stale-replay")

    def _session(self, role="lan-client"):
        return {"sessionId":"s1","actionId":"network.backlog","evaluationPath":"path:lan-to-wan","topologyGeneration":9,
                "routeIdentity":"route-v2:abc","capabilityHash":"fnv1a32:def","companion":{"requiredRole":role}}

    def _evidence(self, phase="control", role="lan-client"):
        return {"contract":"pm-companion/v2","role":role,"ok":True,"bitsPerSecond":1_000_000,"sessionId":"s1","phase":phase,
                "actionId":"network.backlog","pathId":"path:lan-to-wan","topologyGeneration":9,"routeIdentity":"route-v2:abc","capabilityHash":"fnv1a32:def"}

    def test_companion_evidence_exact_context(self):
        ok,err=validate_companion_evidence(self._evidence(),self._session(),"control")
        self.assertTrue(ok); self.assertIsNone(err)
        e=self._evidence(); e["routeIdentity"]="route-v2:changed"
        self.assertEqual(validate_companion_evidence(e,self._session(),"control"),(False,"companion-context-drift"))
        e=self._evidence(); e["sessionId"]="other"
        self.assertEqual(validate_companion_evidence(e,self._session(),"control"),(False,"companion-context-mismatch"))

    def test_local_evidence_requires_local_role(self):
        s=self._session("router-local-client"); e=self._evidence(role="router-local-client")
        self.assertTrue(validate_companion_evidence(e,s,"control")[0])
        e["role"]="lan-client"; self.assertFalse(validate_companion_evidence(e,s,"control")[0])

    def test_reward(self):
        self.assertAlmostEqual(controlled_ab_reward(100,110),0.1)
        with self.assertRaises(ValueError): controlled_ab_reward(0,100)

    def test_health_is_baseline_relative(self):
        before={k:True for k in ['lan','wan','dns','ipv4','route']}; before.update({'ipv6':None,'proxy':None,'vpn':None,'recentOom':False,'thermal':{'throttleCount':0}})
        after=dict(before); after['dns']=False
        self.assertIn('dns:healthy-to-unhealthy',health_regressions(before,after))
        after=dict(before); after['ipv6']=False
        self.assertEqual(health_regressions(before,after),[])

    def test_uninstall_cleanup_never_stale_rolls_back(self):
        self.assertEqual(ownership_cleanup_decision(owner="performance_manager",target_resolved=True,lease_boot="b",current_boot="b",lease_complete=True,live_matches_owned=True),"restore-lease-before-remove-intent")
        self.assertEqual(ownership_cleanup_decision(owner="performance_manager",target_resolved=True,lease_boot="b",current_boot="b",lease_complete=True,live_matches_owned=False),"preserve-live-remove-intent")
        self.assertEqual(ownership_cleanup_decision(owner="performance_manager",target_resolved=True,lease_boot="old",current_boot="new",lease_complete=True,live_matches_owned=True),"remove-intent-runtime-untouched")
        self.assertEqual(ownership_cleanup_decision(owner="external",target_resolved=True,lease_boot="b",current_boot="b",lease_complete=True,live_matches_owned=True),"ignore-not-owned")

    def test_runtime_shaped_transactions_validate(self):
        schema=json.loads((ROOT/'contracts/transaction.schema.json').read_text())
        base={"schemaVersion":2,"transactionId":"tx-1","actionId":"network.backlog","executionSource":"manual","rillDecision":None,"state":"planned","requiredLocks":["sysctl:x"],"bootId":"b","before":None,"applied":None,"deadlineMonotonicMs":None,"commitPolicy":"rollback_after_benchmark","requiresCommitConfirm":True,"pendingMarker":None,"verification":{},"result":None}
        jsonschema.Draft202012Validator(schema).validate(base)
        awaiting={**base,"state":"awaiting_confirm","before":{"benchmark":{}},"deadlineMonotonicMs":12345,"pendingMarker":"/etc/performance-manager/pending/tx-1.json"}
        jsonschema.Draft202012Validator(schema).validate(awaiting)

if __name__=='__main__': unittest.main()
