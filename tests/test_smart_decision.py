import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smart_decision_model import (  # noqa: E402
    FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_features, build_reward,
    candidate_identity, learning_stage, select_smart_action,
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
                                     confidence=0.91, ranking=[{"actionId": candidate_identity(self.actions[1]), "score": 0.8}],
                                     selected_action_id=candidate_identity(self.actions[1]), decision_id="decision-2")
        self.assertEqual(result.selected_action_id, "nic.ring.floor")
        self.assertEqual(result.source, "rill")
        self.assertEqual(result.decision_id, "decision-2")

    def test_runtime_score_order_selects_b_even_when_a_is_first(self):
        actions = [
            {"id": "A", "applyTarget": "NIC-A", "evaluationPaths": ["wan-a"], "executionAuthority": "safe-direct", "risk": "safe"},
            {"id": "B", "applyTarget": "NIC-B", "evaluationPaths": ["wan-b"], "executionAuthority": "safe-direct", "risk": "safe"},
        ]
        result = select_smart_action("assisted", actions, rill_state="available", learning="ready",
                                     confidence=0.91, ranking=[
                                         {"actionId": candidate_identity(actions[1]), "score": 0.91},
                                         {"actionId": candidate_identity(actions[0]), "score": 0.42},
                                     ], selected_action_id=actions[1]["id"], decision_id="decision-b")
        self.assertEqual(result.selected_action_id, "B")
        self.assertEqual(result.source, "rill")

    def test_runtime_exploration_accepts_untrained_below_numeric_a(self):
        actions = [
            {"id": "A", "applyTarget": "NIC-A", "evaluationPaths": ["wan-a"], "executionAuthority": "safe-direct", "risk": "safe"},
            {"id": "B", "applyTarget": "NIC-B", "evaluationPaths": ["wan-b"], "executionAuthority": "safe-direct", "risk": "safe"},
        ]
        result = select_smart_action(
            "assisted", actions, rill_state="available", learning="ready", confidence=0.91,
            ranking=[
                {"actionId": candidate_identity(actions[0]), "score": 0.80},
                {"actionId": candidate_identity(actions[1]), "score": 0.20},
            ], selected_action_id=candidate_identity(actions[1]), decision_id="explore-b",
        )
        self.assertEqual(result.selected_action_id, "B")
        self.assertEqual(result.selected_candidate_id, candidate_identity(actions[1]))
        self.assertEqual(result.source, "rill")
        self.assertEqual(result.reason, "runtime-selected-eligible-candidate")

    def test_runtime_selection_rejects_invalid_or_ambiguous_evidence(self):
        actions = [
            {"id": "A", "applyTarget": "NIC-A", "evaluationPaths": ["wan-a"], "executionAuthority": "safe-direct", "risk": "safe"},
            {"id": "B", "applyTarget": "NIC-B", "evaluationPaths": ["wan-b"], "executionAuthority": "safe-direct", "risk": "safe"},
        ]
        kwargs = dict(rill_state="available", learning="ready", confidence=0.91,
                      selected_action_id=candidate_identity(actions[1]), decision_id="d")
        for ranking in (
            [{"actionId": "unknown", "score": 0.9}],
            [{"actionId": candidate_identity(actions[0]), "score": float("nan")}],
            [{"actionId": candidate_identity(actions[0]), "score": float("inf")}],
            [{"actionId": candidate_identity(actions[0]), "score": 0.9},
             {"actionId": candidate_identity(actions[0]), "score": 0.8}],
        ):
            result = select_smart_action("assisted", actions, ranking=ranking, **kwargs)
            self.assertEqual(result.source, "core-fallback")
            self.assertIn(result.reason, {"rill-ranking-candidate-unknown", "rill-score-invalid", "duplicate-ranking-candidate-id"})
        missing = select_smart_action("assisted", actions, ranking=[], rill_state="available", learning="ready",
                                      confidence=0.91, selected_action_id="missing", decision_id="d")
        self.assertEqual(missing.reason, "rill-selected-candidate-not-legal")
        duplicate_actions = [dict(actions[0]), dict(actions[0])]
        duplicate = select_smart_action("assisted", duplicate_actions, ranking=[], **kwargs)
        self.assertEqual(duplicate.reason, "duplicate-candidate-id")

    def test_candidate_identity_separates_targets_and_paths(self):
        nic_a = {"id": "nic.ring.floor", "applyTarget": "NIC-A", "evaluationPaths": ["wan-a"]}
        nic_b = {"id": "nic.ring.floor", "applyTarget": "NIC-B", "evaluationPaths": ["wan-b"]}
        self.assertNotEqual(candidate_identity(nic_a), candidate_identity(nic_b))
        self.assertLessEqual(len(candidate_identity(nic_a)), 96)

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
        self.assertEqual(result.reason, "rill-selected-candidate-not-legal")

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

    def test_features_use_interval_telemetry_not_cumulative_counters(self):
        action = {"id": "nic.ring.floor", "executionAuthority": "safe-direct", "risk": "safe"}
        cumulative_only = {"interfaces": {"wan": {"rxBytes": 10**12, "txBytes": 10**12}},
                           "softnet": {"dropped": 10**6}, "health": {"cpu": {"busyPct": 99}}}
        values = build_features(action, cumulative_only, {})
        self.assertEqual(values[10:17], [0.0] * 7)
        interval = {"trafficUtilization": 0.4, "ppsPressure": 0.3, "dropErrorPressure": 0.2,
                    "cpuBusyInterval": 0.5, "softirqPressure": 0.1, "queuePressure": 0.6,
                    "memoryPressure": 0.7}
        values = build_features(action, interval, {})
        self.assertEqual(values[10:17], [0.4, 0.3, 0.2, 0.5, 0.1, 0.6, 0.7])

    def test_features_prefer_resolved_path_interval_with_global_fallback(self):
        action = {"id": "nic.ring.floor", "evaluationPaths": ["wan-b"],
                  "executionAuthority": "safe-direct", "risk": "safe"}
        telemetry = {"trafficUtilization": 0.9, "ppsPressure": 0.8,
                     "dropErrorPressure": 0.7, "pathFeatures": {
                         "wan-b": {"available": True, "trafficUtilization": 0.1,
                                   "ppsPressure": 0.2, "dropErrorPressure": 0.3}}}
        self.assertEqual(build_features(action, telemetry, {})[10:13], [0.1, 0.2, 0.3])
        unresolved = dict(action, evaluationPaths=["missing"])
        self.assertEqual(build_features(unresolved, telemetry, {})[10:13], [0.9, 0.8, 0.7])

    def test_reward_goals_are_distinct_and_missing_evidence_is_invalid(self):
        control = {"bitsPerSecond": 100, "latencyMs": 100}
        candidate = {"bitsPerSecond": 110, "latencyMedianMs": 80, "latencyP95Ms": 120}
        control["latencyMedianMs"] = 100
        control["latencyP95Ms"] = 150
        telemetry0 = {"health": {"cpu": {"busyPct": 0.5}}, "cpuBusyInterval": 0.5, "cpuWindowValid": True}
        telemetry1 = {"health": {"cpu": {"busyPct": 0.55}}, "cpuBusyInterval": 0.55, "cpuWindowValid": True}
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

    def test_cumulative_cpu_busy_is_not_benchmark_evidence(self):
        control = {"bitsPerSecond": 100, "latencyMedianMs": 10, "latencyP95Ms": 20}
        candidate = {"bitsPerSecond": 110, "latencyMedianMs": 9, "latencyP95Ms": 18}
        result = build_reward("cpu_efficiency", control, candidate,
                              {"health": {"cpu": {"busyPct": 0.1}}},
                              {"health": {"cpu": {"busyPct": 0.9}}})
        self.assertFalse(result["validated"])
        self.assertEqual(result["reason"], "missing-evidence:cpuEfficiency")

    def test_invalid_cpu_window_cannot_become_zero_or_fallback_evidence(self):
        control = {"bitsPerSecond": 100, "latencyMedianMs": 10, "latencyP95Ms": 20}
        candidate = {"bitsPerSecond": 110, "latencyMedianMs": 9, "latencyP95Ms": 18}
        invalid = {"cpuBusyInterval": 0.0, "cpuWindowValid": False, "health": {"cpu": {"busyPct": 0.1}}}
        valid = {"cpuBusyInterval": 0.8, "cpuWindowValid": True, "health": {"cpu": {"busyPct": 0.9}}}
        for control_telemetry, candidate_telemetry in ((invalid, valid), (valid, invalid)):
            result = build_reward("balanced", control, candidate, control_telemetry, candidate_telemetry)
            self.assertFalse(result["validated"])
            self.assertIsNone(result["components"]["cpuEfficiency"])
            self.assertEqual(result["reason"], "missing-balanced-evidence")
            cpu_result = build_reward("cpu_efficiency", control, candidate, control_telemetry, candidate_telemetry)
            self.assertFalse(cpu_result["validated"])
            self.assertEqual(cpu_result["reason"], "missing-evidence:cpuEfficiency")

    def test_core_contains_closed_loop_governance(self):
        for token in ["pm.noop", "SMART_WARMING_SAMPLES", "drifted", "action-cooldown",
                      "build_reward", "smart_record_validated_outcome", "confidence-below-policy",
                      "recommended-for-benchmark", "rill-selected-noop"]:
            self.assertIn(token, CORE)
        self.assertIn("rill_refresh:", CORE)

    def test_candidate_identity_is_used_for_history_cooldown_and_journals(self):
        self.assertIn("candidateId: rec.actionId", CORE)
        self.assertIn("candidateId: frozen.candidateId ?? frozen.actionId", CORE)
        self.assertIn("smart_context_stats(context_key, candidate_id, true)", CORE)
        self.assertIn("smart_cooldown_state(context.contextKey, candidate_id)", CORE)
        self.assertNotIn("smart_cooldown_state(context.contextKey, action.id)", CORE)
        self.assertIn("stats.recentRewards", CORE)
        self.assertIn("components.cpuBusyInterval", CORE)
        self.assertIn("cpuWindowValid", CORE)
        self.assertNotIn("control_telemetry?.health?.cpu?.busyPct", CORE)
        self.assertNotIn("rill-ranking-selection-mismatch", CORE)

    def test_production_core_runtime_harness_is_wired_to_real_chain(self):
        driver = (ROOT / "tools/docker-validate/harness/production_core_rill_test.uc.frag").read_text()
        runner = (ROOT / "scripts/production_core_rill_integration.py").read_text()
        for token in ["rill_observe", "select_smart_action", "apply_action", "smart_context_stats", "cpu_interval", "build_reward", "PRODUCTION_CORE_EVIDENCE"]:
            self.assertIn(token, driver)
        for token in ["preview-serve", "Runtime executable", "docker", "production_core_rill_test.uc", "pm<->rill-core-integration", "features_a", "features_b"]:
            self.assertIn(token, runner)
        self.assertIn('state.parent}:/tmp/pm-production-runtime:rw', runner)
        self.assertNotIn('state}:/tmp/pm-production-runtime-state.json:rw', runner)
        self.assertIn('/tmp/pm-production-runtime/runtime-state.json', driver)
        self.assertIn('expected_unprivileged_exit', runner)
        self.assertIn('harnessExitCode', runner)
        self.assertIn('exploration', runner)

    def test_runtime_state_checksum_uses_keys_as_values_in_ucode(self):
        checksum = CORE[CORE.index("let canonical_map = function"):CORE.index("let p = fs.popen", CORE.index("let canonical_map = function"))]
        self.assertIn("out[name] = canonical_entry(input[name])", checksum)
        self.assertNotIn("out[names[name]] = canonical_entry(input[names[name]])", checksum)
        self.assertIn("function json_compact(value)", CORE)
        self.assertIn("let wire = json_compact(", checksum)

    def test_apply_action_can_resolve_exact_selector_context_in_ucode(self):
        self.assertLess(CORE.index("function smart_selector_context()"), CORE.index("function apply_action(msg)"))

    def test_conservative_runtime_ranking_is_scoped_to_safe_actions(self):
        self.assertIn("function rill_available_actions(mode)", CORE)
        self.assertIn("if (mode == 'conservative') return out;", CORE)
        self.assertIn("selectorMode: mode", CORE)
        self.assertIn("exact-decision-context-mismatch", CORE)
        gate = (ROOT / "scripts/openwrt-target-gate.sh").read_text()
        self.assertNotIn("actions[0]", gate)

    def test_current_config_has_one_runtime_binary_key(self):
        config = (ROOT / "package/performance-manager/files/etc/config/performance-manager").read_text()
        shadow = config.split("config rill 'shadow'", 1)[1].split("config benchmark", 1)[0]
        self.assertEqual(shadow.count("option binary"), 1)
        self.assertNotIn("runtime_binary", config)


if __name__ == "__main__":
    unittest.main()
