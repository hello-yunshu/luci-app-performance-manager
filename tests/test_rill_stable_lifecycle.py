import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from contract_model import (  # noqa: E402
    binding_is_valid,
    outcome_resolution,
    validate_rill_observe_response,
    validate_rill_outcome_response,
)

CORE = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()


def function_body(name: str) -> str:
    start = CORE.index(f"function {name}(")
    next_start = CORE.find("\nfunction ", start + 1)
    return CORE[start:] if next_start < 0 else CORE[start:next_start]


def observe_request():
    return {
        "contract": "pm-rill-shadow",
        "protocolVersion": 1,
        "requestId": "obs-1",
        "availableActions": [{"id": "network.buffers"}],
    }


def observe_response(**updates):
    response = {
        "contract": "pm-rill-shadow",
        "protocolVersion": 1,
        "requestId": "obs-1",
        "ok": True,
        "decisionId": "0123456789abcdef0123456789abcdef",
        "recommendation": {"actionId": "network.buffers", "confidence": 0.5, "advisory": True},
    }
    response.update(updates)
    return response


def outcome_request():
    return {"contract": "pm-rill-shadow", "protocolVersion": 1, "requestId": "out-1"}


def outcome_response(**updates):
    response = {"contract": "pm-rill-shadow", "protocolVersion": 1,
                "requestId": "out-1", "ok": True, "accepted": True}
    response.update(updates)
    return response


def binding(**updates):
    value = {
        "schemaVersion": 2,
        "decisionId": "0123456789abcdef0123456789abcdef",
        "actionId": "network.buffers",
        "contextKey": "ctx-v1:test",
        "goal": "balanced",
        "modelGeneration": 1,
        "bootId": "boot-a",
        "atMs": 100,
    }
    value.update(updates)
    return value


class RillStableLifecycleTests(unittest.TestCase):
    def test_observe_wrong_contract_rejected(self):
        ok, _ = validate_rill_observe_response(observe_request(), observe_response(contract="other"))
        self.assertFalse(ok)

    def test_observe_wrong_protocol_rejected(self):
        ok, _ = validate_rill_observe_response(observe_request(), observe_response(protocolVersion=2))
        self.assertFalse(ok)

    def test_observe_request_id_mismatch_rejected(self):
        ok, _ = validate_rill_observe_response(observe_request(), observe_response(requestId="other"))
        self.assertFalse(ok)

    def test_observe_invalid_decision_rejected(self):
        ok, _ = validate_rill_observe_response(observe_request(), observe_response(decisionId="short"))
        self.assertFalse(ok)

    def test_observe_unknown_action_rejected(self):
        response = observe_response()
        response["recommendation"]["actionId"] = "unknown.action"
        self.assertFalse(validate_rill_observe_response(observe_request(), response)[0])

    def test_observe_advisory_false_rejected(self):
        response = observe_response()
        response["recommendation"]["advisory"] = False
        self.assertFalse(validate_rill_observe_response(observe_request(), response)[0])

    def test_observe_bad_confidence_rejected(self):
        for confidence in (-0.1, 1.1, math.inf, math.nan, True, None):
            response = observe_response()
            response["recommendation"]["confidence"] = confidence
            with self.subTest(confidence=confidence):
                self.assertFalse(validate_rill_observe_response(observe_request(), response)[0])

    def test_outcome_transport_failure_keeps_binding(self):
        self.assertEqual(outcome_resolution(transport_ok=False, envelope_ok=False, response=None,
                                            prior_response_loss=False, same_fingerprint=True), "KEEP_RETRYABLE")
        body = function_body("rill_report_outcome")
        self.assertIn("rill_outcome_retry_mark(attempt, r.state, true)", body)
        self.assertNotIn("rill_binding_consume(binding)", body.split("if (!r.ok)", 1)[1].split("let envelope", 1)[0])

    def test_outcome_retryable_error_keeps_binding(self):
        response = outcome_response(ok=False, accepted=None,
                                    error={"code": "requestTimeout", "retryable": True})
        self.assertEqual(outcome_resolution(transport_ok=True, envelope_ok=True, response=response,
                                            prior_response_loss=False, same_fingerprint=True), "KEEP_RETRYABLE")

    def test_outcome_ok_false_not_success(self):
        response = outcome_response(ok=False, accepted=None,
                                    error={"code": "unknownDecision", "retryable": False})
        self.assertFalse(validate_rill_outcome_response(outcome_request(), response)[0])

    def test_outcome_missing_accepted_not_success(self):
        response = outcome_response()
        del response["accepted"]
        self.assertFalse(validate_rill_outcome_response(outcome_request(), response)[0])

    def test_outcome_accepted_false_not_success(self):
        self.assertFalse(validate_rill_outcome_response(outcome_request(), outcome_response(accepted=False))[0])

    def test_outcome_success_consumes_binding(self):
        self.assertEqual(outcome_resolution(transport_ok=True, envelope_ok=True, response=outcome_response(),
                                            prior_response_loss=False, same_fingerprint=True), "CONSUME_ACCEPTED")

    def test_outcome_duplicate_same_attempt_reconciles(self):
        response = outcome_response(ok=False, accepted=None,
                                    error={"code": "duplicateFeedback", "retryable": False})
        self.assertEqual(outcome_resolution(transport_ok=True, envelope_ok=True, response=response,
                                            prior_response_loss=True, same_fingerprint=True), "CONSUME_RECONCILED")

    def test_outcome_duplicate_unrelated_fails(self):
        response = outcome_response(ok=False, accepted=None,
                                    error={"code": "duplicateFeedback", "retryable": False})
        self.assertEqual(outcome_resolution(transport_ok=True, envelope_ok=True, response=response,
                                            prior_response_loss=False, same_fingerprint=True), "RETIRE_TERMINAL")
        self.assertEqual(outcome_resolution(transport_ok=True, envelope_ok=True, response=response,
                                            prior_response_loss=True, same_fingerprint=False), "RETIRE_TERMINAL")

    def test_binding_keyed_by_decision(self):
        self.assertIn("rill_bindings[binding.decisionId] = binding", CORE)
        self.assertNotIn("rill_bindings[actionId]", CORE)

    def test_new_observe_same_action_does_not_rebind_active_session(self):
        self.assertIn("rillDecision:frozen_decision", CORE)
        self.assertIn("session.rillDecision", CORE)

    def test_benchmark_freezes_exact_decision(self):
        body = function_body("benchmark_start")
        self.assertIn("rill_binding_freeze(msg?.decisionId,action,'benchmark')", body)

    def test_transaction_freezes_exact_decision(self):
        self.assertIn("executionSource: execution_source ?? 'manual', rillDecision: rill_decision ?? null", CORE)

    def test_manual_same_action_does_not_consume_unrelated_decision(self):
        body = function_body("apply_action")
        self.assertIn("source == 'rill-advisory'", body)
        self.assertIn("source != 'manual' || msg?.decisionId != null", body)

    def test_cross_boot_binding_invalidated(self):
        self.assertFalse(binding_is_valid(binding(), boot_id="boot-b", now_ms=200))
        self.assertIn("binding.bootId != boot_id()", CORE)

    def test_corrupt_binding_fail_closed(self):
        for value in (None, {}, binding(decisionId="bad"), binding(modelGeneration=2)):
            self.assertFalse(binding_is_valid(value, boot_id="boot-a", now_ms=200))

    def test_binding_store_bound_enforced(self):
        body = function_body("rill_bindings_prune")
        self.assertIn("length(rows) > RILL_BINDINGS_MAX", body)
        self.assertNotIn("rill-bindings.json", CORE)

    def test_telemetry_does_not_observe(self):
        self.assertNotIn("rill_observe", function_body("schedule_telemetry"))

    def test_cached_advisory_does_not_reobserve(self):
        body = function_body("recommendations")
        self.assertIn("if (allow_observe && !rill_advisory_live", body)
        self.assertIn("recommendations(false)", function_body("diagnostics"))

    def test_context_drift_invalidates(self):
        self.assertIn("rill_invalidate_runtime_decisions", function_body("refresh"))

    def test_fresh_advisory_observes_once(self):
        self.assertIn("rill_advisory_live = rill_advisory_get()", function_body("recommendations"))
        self.assertIn("rill_observation = rill_observe()", function_body("recommendations"))

    def test_idle_has_zero_periodic_decision_writes(self):
        self.assertNotIn("rill_bindings_save", CORE)
        self.assertNotIn("rill_observe", function_body("schedule_telemetry"))
        self.assertIn("rill_retry_pending_outcomes", function_body("schedule_telemetry"))

    def test_pending_outcome_retry_uses_exact_frozen_binding(self):
        body = function_body("rill_retry_pending_outcomes")
        self.assertIn("rill_binding_valid(attempt.binding)", body)
        self.assertIn("rill_report_outcome(attempt.binding", body)
        self.assertIn("attempt.bootId != boot_id()", body)

    def test_benchmark_rill_advisory_visible(self):
        self.assertIn("kind: 'benchmark'", function_body("rill_action_descriptor"))

    def test_benchmark_rill_advisory_never_direct_apply(self):
        body = function_body("rill_action_descriptor")
        self.assertIn("executionPath: 'benchmark_start'", body)
        self.assertIn("rill_binding_freeze(msg?.decisionId, action_id, 'safe-direct')", function_body("apply_action"))

    def test_model_generation_one_is_upstream_audited(self):
        snapshot = json.loads((ROOT / "contracts/upstream/rill-pm-adapter-v1.2.0-contract.json").read_text())
        self.assertEqual(snapshot["modelGeneration"]["fresh"], 1)
        self.assertFalse(snapshot["modelGeneration"]["normalV1PathIncrements"])
        self.assertEqual(snapshot["persistence"]["observe"], "ledger.register then persist")


if __name__ == "__main__":
    unittest.main()
