import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/rill-ipc.schema.json').read_text())
RILL = (ROOT / 'package/performance-manager-rill/src/src/main.rs').read_text()


def validation_path():
    start = RILL.index('fn parse_available_actions')
    end = RILL.index('fn parse_args')
    return RILL[start:end]


def branch_required(op):
    for node in SCHEMA['allOf']:
        if node.get('then') and node.get('if', {}).get('properties', {}).get('op', {}).get('const') == op:
            return set(node['then']['required'])
    return set()


class RillContextTests(unittest.TestCase):
    def test_api_version_and_context_key_bounds_match(self):
        self.assertEqual(SCHEMA['properties']['api']['const'], 2)
        self.assertEqual(SCHEMA['properties']['contextKey']['maxLength'], 512)
        self.assertIn('const API_VERSION: u64 = 2', RILL)
        self.assertIn('const MAX_CONTEXT_KEY_LEN: usize = 512', RILL)

    def test_context_key_pattern_matches_rust_check(self):
        pattern = SCHEMA['properties']['contextKey']['pattern']
        self.assertEqual(pattern, '^ctx-v1:')
        self.assertIn('starts_with("ctx-v1:")', RILL)

    def test_observe_required_fields_are_validated_by_rust(self):
        required = branch_required('observe')
        self.assertIn('contextKey', required)
        path = validation_path()
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, path)

    def test_outcome_required_fields_are_validated_by_rust(self):
        required = branch_required('outcome')
        self.assertIn('validated', required)
        self.assertIn('reward', required)
        self.assertIn('contextKey', required)
        path = validation_path()
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, path)

    def test_outcome_validated_const_matches_rust(self):
        outcome = next(n['then'] for n in SCHEMA['allOf'] if n.get('if', {}).get('properties', {}).get('op', {}).get('const') == 'outcome')
        self.assertEqual(outcome['properties']['validated']['const'], True)
        self.assertIn('get_bool("validated") != Some(true)', RILL)

    def test_rill_never_actuates(self):
        for forbidden in ['std::process::Command', 'Command::new', 'iptables', 'nft ', 'uci set', 'uci commit']:
            self.assertNotIn(forbidden, RILL)

    def test_measurement_class_enum_matches_rust(self):
        enum = SCHEMA['properties']['measurementClass']['enum']
        self.assertEqual(enum, ['controlled_ab', 'passive_before_after', 'health_only'])
        for value in enum:
            self.assertIn(value, RILL)


if __name__ == '__main__':
    unittest.main()