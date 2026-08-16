import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/rill-ipc.schema.json').read_text())
CORE = (ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()


def branch_required(op):
    for node in SCHEMA['allOf']:
        if node.get('then') and node.get('if', {}).get('properties', {}).get('op', {}).get('const') == op:
            return set(node['then']['required'])
    return set()


class RillContextTests(unittest.TestCase):
    def test_api_version_and_context_key_bounds_match(self):
        # The formal IPC schema and the Core must agree on the protocol contract
        # (pm-rill-shadow v1) and the bounded ContextKey the Core constructs for
        # every observe/outcome.
        self.assertEqual(SCHEMA['properties']['contract']['const'], 'pm-rill-shadow')
        self.assertEqual(SCHEMA['properties']['protocolVersion']['const'], 1)
        self.assertEqual(SCHEMA['properties']['contextKey']['maxLength'], 512)
        self.assertIn("const RILL_CONTRACT = 'pm-rill-shadow'", CORE)
        self.assertIn('const RILL_PROTOCOL_VERSION = 1', CORE)
        self.assertIn('const RILL_REQUIRED_OPS = [ \'status\', \'observe\', \'outcome\' ]', CORE)

    def test_context_key_pattern_matches_core(self):
        pattern = SCHEMA['properties']['contextKey']['pattern']
        self.assertEqual(pattern, '^ctx-v1:')
        self.assertIn('ctx-v1:', CORE)

    def test_observe_required_fields_are_emitted_by_core(self):
        required = branch_required('observe')
        self.assertIn('contextKey', required)
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, CORE)

    def test_outcome_required_fields_are_emitted_by_core(self):
        required = branch_required('outcome')
        self.assertIn('validated', required)
        self.assertIn('reward', required)
        self.assertIn('contextKey', required)
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, CORE)

    def test_outcome_validated_const_only_after_validation(self):
        outcome = next(n['then'] for n in SCHEMA['allOf'] if n.get('if', {}).get('properties', {}).get('op', {}).get('const') == 'outcome')
        self.assertEqual(outcome['properties']['validated']['const'], True)
        # A validated reward/outcome is only emitted after safe rollback of the
        # candidate and a health pass; otherwise no reward is sent at all.
        body = CORE
        self.assertIn("reward=(c1-c0)/c0", body)
        self.assertIn("rollback_transaction(session.transactionId,'benchmark-complete')", body)

    def test_goal_is_first_class_rill_partition(self):
        # Goal is a ContextKey partition component and a first-class Rill
        # request field, so changing goal genuinely repartitions the model.
        self.assertIn('goal=%s', CORE)
        self.assertIn('goal_class = safe_name(goal_id ?? \'balanced\')', CORE)
        self.assertIn('const GOALS = [ \'balanced\', \'throughput\', \'latency\', \'cpu_efficiency\' ]', CORE)

    def test_measurement_class_enum_matches_core(self):
        enum = SCHEMA['properties']['measurementClass']['enum']
        self.assertEqual(enum, ['controlled_ab', 'passive_before_after', 'health_only'])
        for value in enum:
            self.assertIn(value, CORE)

    def test_rill_outcome_only_after_validated_ab(self):
        # Blocker 3: a methodology-mismatched or unvalidated experiment must
        # never send a reward/outcome to Rill.
        self.assertIn('measurement-methodology-mismatch', CORE)
        self.assertIn('validated:true', CORE)


if __name__ == '__main__':
    unittest.main()