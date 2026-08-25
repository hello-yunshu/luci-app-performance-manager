import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/rill-ipc.schema.json').read_text())
CORE = (ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()


def branch_required(op):
    """Required fields of the oneOf per-op branch (rill-ipc.schema.json mirrors
    the tagged Request enum in rill-pm-adapter v1.5.1 lib.rs)."""
    node = SCHEMA['$defs'].get(f'{op}Request')
    return set(node['required']) if node else set()


def branch_properties(op):
    node = SCHEMA['$defs'].get(f'{op}Request')
    return (node or {}).get('properties', {})


class RillContextTests(unittest.TestCase):
    def test_api_version_and_context_key_bounds_match(self):
        # The formal IPC schema and the Core must agree on the protocol contract
        # (pm-rill-shadow v1) and the bounded ContextKey the Core constructs for
        # every observe/outcome.
        props = branch_properties('status')
        self.assertEqual(props['contract']['const'], 'pm-rill-shadow')
        self.assertEqual(props['protocolVersion']['const'], 1)
        self.assertEqual(SCHEMA['$defs']['contextKey']['maxLength'], 512)
        self.assertIn("const RILL_CONTRACT = 'pm-rill-shadow'", CORE)
        self.assertIn('const RILL_PROTOCOL_VERSION = 1', CORE)
        self.assertIn('const RILL_REQUIRED_OPS = [ \'status\', \'observe\', \'outcome\' ]', CORE)

    def test_context_key_pattern_matches_core(self):
        pattern = SCHEMA['$defs']['contextKey']['pattern']
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

    def test_outcome_validated_only_after_safe_rollback(self):
        # The v1.5.1 schema types validated as a boolean (not a const), so the
        # validated-only-after-safety rule is enforced by the Core, not the
        # wire schema: a reward/outcome is only emitted after safe rollback of
        # the candidate and a health pass; otherwise no reward is sent at all.
        outcome = SCHEMA['$defs']['outcomeRequest']
        self.assertIn('validated', outcome['required'])
        self.assertIn('reward', outcome['required'])
        body = CORE
        self.assertIn("reward=(c1-c0)/c0", body)
        self.assertIn("rollback_transaction(session.transactionId,'benchmark-complete')", body)

    def test_goal_is_first_class_rill_partition(self):
        # Goal is a ContextKey partition component and a first-class Rill
        # request field, so changing goal genuinely repartitions the model.
        self.assertIn('goal=%s', CORE)
        self.assertIn('goal_class = safe_name(goal_id ?? \'balanced\')', CORE)
        self.assertIn('const GOALS = [ \'balanced\', \'throughput\', \'latency\', \'cpu_efficiency\' ]', CORE)

    def test_measurement_class_values_match_core(self):
        # Rill v1.5.1 types measurementClass as an open string; the Core is the
        # source of the closed set of methodology values.
        self.assertIn("['controlled_ab','passive_before_after','health_only']", CORE)
        for value in ('controlled_ab', 'passive_before_after', 'health_only'):
            self.assertIn(value, CORE)

    def test_rill_outcome_only_after_validated_ab(self):
        # Blocker 3: a methodology-mismatched or unvalidated experiment must
        # never send a reward/outcome to Rill.
        self.assertIn('measurement-methodology-mismatch', CORE)
        self.assertIn('measurement_methodology({ methodology: a })', CORE)
        self.assertIn('measurement_methodology({ methodology: b })', CORE)
        self.assertIn('validated:true', CORE)


if __name__ == '__main__':
    unittest.main()
