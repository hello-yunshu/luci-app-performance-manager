import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smart_decision_model import (  # noqa: E402
    FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_features, build_reward,
    learning_stage, select_smart_action,
)

CORE = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()


class SmartDecisionTests(unittest.TestCase):
    def setUp(self):
        self.actions = [
            {"id": "pm.noop", "executionAuthority": "none", "risk": "none"},
            {"id": "nic.ring.floor", "executionAuthority": "safe-direct", "risk": "safe"},
            {"id": "network.backlog", "executionAuthority": "benchmark", "risk": "benchmark"},
        ]

    def test_unified_selector_is_in_both_auto_paths(self):
        self.assertIn("function select_smart_action(mode, candidates, context)", CORE)
        self.assertIn("select_smart_action('assisted', actions, context)", CORE)
        self.assertIn("select_smart_action('conservative', actions, context)", CORE)
        self.assertNotIn("let action = actions[0];", CORE[CORE.index("function assisted_auto_tick"):CORE.index("function benchmark_active")])
        self.assertNotIn("let action = actions[0];", CORE[CORE.index("function conservative_auto_tick"):CORE.index("function analysis_report")])

    def test_ready_rill_selects_second_action_with_exact_decision(self):
        result = select_smart_action("assisted", self.actions, rill_state="available", learning="ready",
                                     confidence=0.91, ranking=[{"actionId": "nic.ring.floor", "score": 0.8}],
                                     selected_action_id="nic.ring.floor", decision_id="decision-2")
        self.assertEqual(result.selected_action_id, "nic.ring.floor")
        self.assertEqual(result.source, "rill")
        self.assertEqual(result.decision_id, "decision-2")

    def test_cold_warming_low_confidence_and_invalid_action_fail_closed(self):
        for stage in ("cold", "warming"):
            result = select_smart_action("conservative", self.actions, rill_state="available", learning=stage,
                                         confidence=0.99, ranking=[], selected_action_id="nic.ring.floor", decision_id="d")
            self.assertEqual(result.source, "core-fallback")
        result = select_smart_action("conservative", self.actions, rill_state="available", learning="ready",
                                     confidence=0.30, ranking=[], selected_action_id="nic.ring.floor", decision_id="d")
        self.assertEqual(result.reason, "confidence-below-policy")
        result = select_smart_action("conservative", self.actions, rill_state="available", learning="ready",
                                     confidence=0.90, ranking=[], selected_action_id="missing", decision_id="d")
        self.assertEqual(result.reason, "rill-action-not-legal")

    def test_noop_and_benchmark_are_not_direct_apply(self):
        result = select_smart_action("assisted", self.actions, rill_state="available", learning="ready",
                                     confidence=0.90, ranking=[], selected_action_id="pm.noop", decision_id="d")
        self.assertEqual(result.selected_action_id, "pm.noop")
        self.assertTrue(result.auto_eligible)
        result = select_smart_action("assisted", self.actions, rill_state="available", learning="ready",
                                     confidence=0.90, ranking=[], selected_action_id="network.backlog", decision_id="d")
        self.assertNotEqual(result.selected_action_id, "network.backlog")
        self.assertIn("executionAuthority == 'benchmark'", CORE)
        self.assertIn("mutation: false", CORE)

    def test_learning_stage_and_feature_contract(self):
        self.assertEqual(learning_stage(0, 1.0, False), "cold")
        self.assertEqual(learning_stage(3, 0.9, False), "warming")
        self.assertEqual(learning_stage(8, 0.9, False), "ready")
        self.assertEqual(learning_stage(8, 0.9, True), "drifted")
        self.assertEqual(len(FEATURE_NAMES), 20)
        self.assertEqual(FEATURE_SCHEMA_VERSION, 2)
        values = build_features(self.actions[0], {"health": {}}, {})
        self.assertEqual(len(values), 20)
        self.assertEqual(values[0], 1.0)
        schema = json.loads((ROOT / "contracts/rill-feature-schema.json").read_text())
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 2)
        self.assertEqual(schema["properties"]["vectorWidth"]["const"], 20)

    def test_reward_goals_are_distinct_and_missing_evidence_is_invalid(self):
        control = {"bitsPerSecond": 100, "latencyMs": 100}
        candidate = {"bitsPerSecond": 110, "latencyMs": 80}
        telemetry0 = {"health": {"cpu": {"busyPct": 0.5}}}
        telemetry1 = {"health": {"cpu": {"busyPct": 0.55}}}
        throughput = build_reward("throughput", control, candidate, telemetry0, telemetry1)
        latency = build_reward("latency", control, candidate, telemetry0, telemetry1)
        cpu = build_reward("cpu_efficiency", control, {"bitsPerSecond": 110}, telemetry0, telemetry1)
        balanced = build_reward("balanced", control, candidate, telemetry0, telemetry1)
        self.assertNotEqual(throughput["reward"], latency["reward"])
        self.assertIsNotNone(cpu["reward"])
        self.assertNotEqual(throughput["reward"], balanced["reward"])
        missing = build_reward("latency", {"bitsPerSecond": 100}, {"bitsPerSecond": 110}, telemetry0, telemetry1)
        self.assertFalse(missing["validated"])
        health_bad = build_reward("throughput", control, candidate, telemetry0, telemetry1, health_regressed=True)
        self.assertFalse(health_bad["validated"])

    def test_core_contains_closed_loop_governance(self):
        for token in ["pm.noop", "SMART_WARMING_SAMPLES", "drifted", "action-cooldown",
                      "build_reward", "smart_record_validated_outcome", "confidence-below-policy",
                      "recommended-for-benchmark", "rill-selected-noop"]:
            self.assertIn(token, CORE)
        self.assertIn("rill_refresh:", CORE)


if __name__ == "__main__":
    unittest.main()
