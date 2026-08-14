import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import contract_model as m


class BenchmarkLockTests(unittest.TestCase):
    def test_any_active_experiment_is_globally_exclusive(self):
        self.assertEqual(m.benchmark_lock_decision(domain='benchmark:global', existing_session_active=True, existing_same_boot=True, existing_session_id='s1', new_session_id='s2'), 'reject-active-benchmark-exclusive')

    def test_stale_or_foreign_boot_lock_is_reacquirable(self):
        self.assertEqual(m.benchmark_lock_decision(domain='benchmark:global', existing_session_active=False, existing_same_boot=True, existing_session_id='s1', new_session_id='s2'), 'acquire')
        self.assertEqual(m.benchmark_lock_decision(domain='benchmark:global', existing_session_active=True, existing_same_boot=False, existing_session_id='s1', new_session_id='s2'), 'acquire')

    def test_same_session_hold_is_not_a_conflict(self):
        self.assertEqual(m.benchmark_lock_decision(domain='benchmark:global', existing_session_active=True, existing_same_boot=True, existing_session_id='s1', new_session_id='s1'), 'acquire-same-session')

    def test_system_and_device_experiments_share_one_domain(self):
        for action, scope in [('nic.coalescing', 'device'), ('tcp.cc', 'system'), ('qdisc.replace', 'device'), ('cpu.governor', 'system')]:
            self.assertEqual(m.benchmark_lock_domain(action, scope), 'benchmark:global')


class BenchmarkMaskedKeysTests(unittest.TestCase):
    def test_fastpath_candidate_masks_its_own_uci_keys(self):
        keys = m.benchmark_masked_uci_keys('fastpath.software_flow_offload')
        self.assertEqual(sorted(keys), ['firewall.@defaults[0].flow_offloading', 'firewall.@defaults[0].flow_offloading_hw'])
        self.assertEqual(m.benchmark_masked_uci_keys('fastpath.hardware_flow_offload'), keys)

    def test_non_fastpath_actions_mask_nothing(self):
        for action in ['nic.coalescing', 'tcp.cc', 'network.backlog', 'cpu.governor']:
            self.assertEqual(m.benchmark_masked_uci_keys(action), [])


class BenchmarkContextDriftTests(unittest.TestCase):
    FROZEN = {'capabilityHash': 'c1', 'topologyGeneration': 1, 'routeIdentity': 'r1', 'integrationFingerprint': 'f1', 'workloadClass': ['plain_forwarding']}

    def test_stable_context_has_no_drift(self):
        self.assertEqual(m.benchmark_context_drift(self.FROZEN, dict(self.FROZEN)), [])

    def test_every_component_is_a_drift_reason(self):
        cases = {
            'capability': {'capabilityHash': 'c2'},
            'topology': {'topologyGeneration': 2},
            'route': {'routeIdentity': 'r2'},
            'integration': {'integrationFingerprint': 'f2'},
            'workload': {'workloadClass': ['local_endpoint']},
        }
        for reason, mutation in cases.items():
            with self.subTest(reason=reason):
                now = dict(self.FROZEN); now.update(mutation)
                self.assertEqual(m.benchmark_context_drift(self.FROZEN, now), [reason])

    def test_workload_order_is_insensitive(self):
        frozen = dict(self.FROZEN); frozen['workloadClass'] = ['a', 'b']
        now = dict(self.FROZEN); now['workloadClass'] = ['b', 'a']
        self.assertEqual(m.benchmark_context_drift(frozen, now), [])


class RillContextKeyTests(unittest.TestCase):
    def key(self, **kw):
        base = dict(profile='recommended', capability_hash='cap1', topology_generation=7, path_id='path:lan-to-wan', route_identity='route-v2:abc', workload_class=['plain_forwarding'], integration_fingerprint='integ1')
        base.update(kw); return m.rill_context_key(**base)

    def test_canonical_bounded_prefix_and_components(self):
        k = self.key()
        self.assertTrue(k.startswith('ctx-v1:profile=recommended;cap=cap1;topo=7;path=path:lan-to-wan;route='))
        self.assertEqual(len(k.split(';')), 7)

    def test_route_identity_is_hashed_and_unresolved_is_marked(self):
        resolved = self.key(route_identity='route-v2:abc')
        unresolved = self.key(route_identity='unresolved')
        self.assertIn(';route=unresolved;', unresolved)
        self.assertNotIn(';route=unresolved;', resolved)
        self.assertNotEqual(resolved, unresolved)

    def test_same_components_produce_identical_keys(self):
        self.assertEqual(self.key(), self.key())

    def test_workload_ordering_is_stable(self):
        self.assertEqual(self.key(workload_class=['a', 'b']), self.key(workload_class=['b', 'a']))

    def test_different_integration_fingerprints_change_the_key(self):
        self.assertNotEqual(self.key(integration_fingerprint='integ1'), self.key(integration_fingerprint='integ2'))


class RillOutcomeBindingTests(unittest.TestCase):
    def test_valid_context_key_binds(self):
        k = m.rill_context_key(profile='p', capability_hash='c', topology_generation=1, path_id='path:lan-to-wan', route_identity='r', workload_class=['w'], integration_fingerprint='f')
        self.assertEqual(m.rill_outcome_context_binding({'contextKey': k}), k)

    def test_missing_or_bad_key_does_not_bind(self):
        self.assertIsNone(m.rill_outcome_context_binding({}))
        self.assertIsNone(m.rill_outcome_context_binding({'contextKey': 'v1:bad'}))


if __name__ == '__main__':
    unittest.main()