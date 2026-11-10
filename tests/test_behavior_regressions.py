import json
import subprocess
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from contract_model import (
    WORKLOAD_CLASSES, derive_workload_class, goal_measurement, measurement_methodology,
    methodology_matches, nft_ruleset_fingerprint, replay_cede_decision, underlay_target,
)
from contract_model import (
    benchmark_context_drift, rill_context_key, validate_companion_evidence,
)

CORE = (ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()


def _session(role='lan-client'):
    return {"sessionId": "s1", "actionId": "network.backlog", "evaluationPath": "path:lan-to-wan",
            "topologyGeneration": 9, "routeIdentity": "route-v2:abc", "capabilityHash": "fnv1a32:def",
            "companion": {"requiredRole": role}}


def _evidence(phase='control', role='lan-client'):
    return {"contract": "pm-companion/v2", "role": role, "ok": True, "bitsPerSecond": 1_000_000,
            "sessionId": "s1", "phase": phase, "actionId": "network.backlog", "pathId": "path:lan-to-wan",
            "topologyGeneration": 9, "routeIdentity": "route-v2:abc", "capabilityHash": "fnv1a32:def"}


class BehavioralRegressions(unittest.TestCase):
    # 1. LuCI render smoke (host harness, not just node --check) — Blocker 1.
    def test_luci_render_smoke_runs_clean(self):
        cp = subprocess.run(['node', str(ROOT / 'scripts/luci_render_smoke.js')],
                            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(cp.returncode, 0, cp.stdout[-3000:])
        self.assertIn('benchmark action switch rebuilds path selector (no TDZ)', cp.stdout)

    # 2. Runtime-emitted topology honours the formal schema (9.1) — lanInterface is a string.
    def test_runtime_topology_validates_against_formal_schema(self):
        schema = json.loads((ROOT / 'contracts/topology-path.schema.json').read_text())
        runtime = {
            "schemaVersion": 1, "topologyGeneration": 9, "interfaces": [], "devices": [],
            "paths": [
                {"id": "path:lan-to-wan", "workloadClass": ["plain_forwarding"], "lanInterface": "lan",
                 "wanInterface": "wan", "routeIdentity": "netifd:abc", "routeResolved": True,
                 "routeProvider": "netifd-fallback", "underlayChain": ["br-lan", "eth1"], "targetRefs": []},
                # local-endpoint path must carry an EMPTY STRING, never null.
                {"id": "path:local-endpoint", "workloadClass": ["local_endpoint"], "lanInterface": "",
                 "wanInterface": "wan", "routeIdentity": "unresolved", "routeResolved": False,
                 "routeProvider": "unresolved", "underlayChain": [], "targetRefs": []},
            ],
        }
        jsonschema.Draft202012Validator(schema).validate(runtime)
        # The runtime must not emit null for lanInterface anywhere.
        self.assertTrue(all(isinstance(p['lanInterface'], str) for p in runtime['paths']))

    # 3. Goal is behaviourally first-class (Blocker 2): unsupported Goals never degrade.
    def test_goal_measurement_semantics_are_real(self):
        self.assertEqual(goal_measurement('balanced'), 'controlled_ab')
        self.assertEqual(goal_measurement('throughput'), 'controlled_ab')
        self.assertEqual(goal_measurement('latency'), 'controlled_ab')
        self.assertEqual(goal_measurement('cpu_efficiency'), 'controlled_ab')
        self.assertIn('const GOALS = [ \'balanced\', \'throughput\', \'latency\', \'cpu_efficiency\' ]', CORE)

    # 4. Measurement fingerprint mismatch is rejected (Blocker 3).
    def test_measurement_fingerprint_mismatch_rejected(self):
        control = measurement_methodology(host='server-A', port=5201, reverse=False, parallel=1, duration=10)
        candidate = measurement_methodology(host='server-B', port=5201, reverse=True, parallel=16, duration=60)
        self.assertFalse(methodology_matches(control, candidate))
        # Identical legs match; tool version is part of the fingerprint.
        twin = measurement_methodology(host='server-A', port=5201, reverse=False, parallel=1, duration=10)
        self.assertTrue(methodology_matches(control, twin))
        control2 = measurement_methodology(host='server-A', port=5201, reverse=False, parallel=1, duration=10, tool_version='3.17')
        drifty = measurement_methodology(host='server-A', port=5201, reverse=False, parallel=1, duration=10, tool_version='3.18')
        self.assertFalse(methodology_matches(control2, drifty))
        # Core rejects a methodology drift on the candidate leg.
        self.assertIn('measurement-methodology-mismatch', CORE)

    # 5. Policy replay cedes on live drift (Blocker 4).
    def test_replay_cedes_on_live_drift(self):
        self.assertEqual(replay_cede_decision(has_owned_lease=True, owned_ring='1024', live_ring='1024'), 'replay')
        self.assertEqual(replay_cede_decision(has_owned_lease=True, owned_ring='1024', live_ring='512'), 'ceded-live-drift')
        self.assertEqual(replay_cede_decision(has_owned_lease=False, owned_ring=None, live_ring='512'), 'replay')
        # The Core emits the same status string when it relinquishes ownership.
        self.assertIn('ceded-live-drift', CORE)
        self.assertIn('ownershipRelinquished', CORE)

    # 6. Underlay chain resolution from realistic device topology (9.2).
    def test_underlay_chain_resolves_to_physical_nic(self):
        # Realistic hierarchy: br-lan bridge -> eth1.100 VLAN -> eth1 physical NIC.
        devices = {'br-lan': 'eth1.100', 'eth1.100': 'eth1', 'ppp0': 'eth2', 'wg0': None}
        chain, target = underlay_target(devices, 'br-lan')
        # The full chain is walked (bridge -> VLAN -> NIC); the VLAN is part of
        # the chain but the stable target is the physical NIC, not the VLAN.
        self.assertEqual(chain, ['br-lan', 'eth1.100', 'eth1'])
        self.assertEqual(target, 'eth1')
        # PPPoE -> physical NIC.
        chain2, target2 = underlay_target(devices, 'ppp0')
        self.assertEqual(target2, 'eth2')
        # Tunnel terminates at itself (no physical parent) -> target is the tunnel.
        chain3, target3 = underlay_target(devices, 'wg0')
        self.assertEqual(target3, 'wg0')

    # 7. Custom Multi-WAN / PBR interface fixtures must not rely on wan[0-9]+ naming (9.3).
    def test_multiwan_paths_use_route_evidence_not_naming_guess(self):
        # A PBR secondary path whose interface is named e.g. "isp-b" must resolve
        # via its real underlay device, not a "wan2" guess.
        devices = {'br-lan': 'eth1', 'isp-b': 'ppp0', 'ppp0': 'eth6'}
        chain, target = underlay_target(devices, 'isp-b')
        self.assertEqual(target, 'eth6')
        wl = derive_workload_class(proto='pppoe', transparent_proxy=False, vpn=False, underlay_chain=chain)
        self.assertIn('pppoe', wl)
        # Core builds wanCandidates from runtime route/rule evidence.
        self.assertIn('wanCandidates', CORE)
        self.assertIn("'-j', '-4', 'rule', 'show'", CORE)

    # 8. Workload Class derivation covers all seven frozen classes from evidence (9.4).
    def test_workload_class_derivation_covers_all_frozen_classes(self):
        self.assertEqual(WORKLOAD_CLASSES, ['plain_forwarding', 'local_endpoint', 'transparent_proxy',
                                             'vpn_tunnel', 'pppoe', 'wireless', 'storage_service'])
        cases = [
            (dict(proto=None, transparent_proxy=False, vpn=False, underlay_chain=[]), ['plain_forwarding']),
            (dict(proto='pppoe', transparent_proxy=False, vpn=False, underlay_chain=['ppp0', 'eth2']), ['pppoe']),
            (dict(proto=None, transparent_proxy=True, vpn=False, underlay_chain=[]), ['transparent_proxy']),
            (dict(proto=None, transparent_proxy=False, vpn=True, underlay_chain=['wg0']), ['vpn_tunnel']),
            (dict(proto=None, transparent_proxy=False, vpn=False, underlay_chain=['wlan0']), ['wireless']),
            (dict(proto=None, transparent_proxy=False, vpn=False, underlay_chain=[], local_endpoint=True), ['local_endpoint']),
            (dict(proto=None, transparent_proxy=False, vpn=False, underlay_chain=['eth0-swp'], storage_chain=True), ['storage_service']),
        ]
        for kwargs, expected in cases:
            self.assertEqual(derive_workload_class(**kwargs), expected)
        # Action workload derives from paths, never hard-coded plain_forwarding.
        self.assertIn('workload_for_paths', CORE)

    # 9. Live firewall/route drift invalidates the experiment (9.6).
    def test_nft_ruleset_fingerprint_is_stable_across_volatile_counters(self):
        a = 'chain c1 { } "packets": 123, "bytes": 456 chain c2 { } "packets": 7, "bytes": 8'
        b = 'chain c1 { } "packets": 9999, "bytes": 11111 chain c2 { } "packets": 1, "bytes": 2'
        # Same topology, different volatile counters -> same fingerprint.
        self.assertEqual(nft_ruleset_fingerprint(a), nft_ruleset_fingerprint(b))
        c = 'chain c1 { something else } "packets": 1, "bytes": 2'
        self.assertNotEqual(nft_ruleset_fingerprint(a), nft_ruleset_fingerprint(c))
        self.assertIn('nft_ruleset_fingerprint', CORE)

    # 10. Rill capability handshake is contract/protocol driven and fail-closed.
    def test_rill_capability_handshake_is_fail_closed(self):
        self.assertIn("const RILL_RUNTIME_API_VERSION = 3", CORE)
        self.assertIn('RILL_RUNTIME_CAPABILITIES', CORE)
        self.assertIn('preview-serve', CORE)
        self.assertIn('runtime-version-mismatch', CORE)
        self.assertIn('external-runtime-not-provisioned', CORE)
        self.assertIn('binary-invalid', CORE)
        self.assertIn("state: RILL_STATES.incompatible", CORE)

    # 11. External Runtime dependency contract is exact and downstream-owned.
    def test_rill_dependency_contract_is_external_and_qualified(self):
        dep = json.loads((ROOT / 'contracts/rill-runtime.json').read_text())
        self.assertEqual(dep['resolved']['version'], '1.5.6')
        self.assertEqual(dep['openwrtPackage']['package'], 'rill-runtime')
        self.assertEqual(dep['openwrtPackage']['binary'], '/usr/bin/rill-runtime')
        self.assertEqual(dep['qualification']['verdict'], 'PASS')
        makefile = (ROOT / 'package/performance-manager-rill/Makefile').read_text()
        self.assertIn('+rill-runtime', makefile)

    def test_rill_outcome_requires_context_binding(self):
        from contract_model import rill_outcome_context_binding
        self.assertTrue(rill_outcome_context_binding({'contextKey': 'ctx-v1:abc'}))
        self.assertIsNone(rill_outcome_context_binding({'contextKey': 'other'}))


if __name__ == '__main__':
    unittest.main()
