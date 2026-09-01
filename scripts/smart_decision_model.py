"""Pure reference model for Performance Manager Smart Decision v2.

The OpenWrt implementation lives in ucode.  This small model deliberately
contains only deterministic policy/math so tests can exercise the safety gates
without pretending that a host Python process is part of the product runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

FEATURE_SCHEMA_VERSION = 2
FEATURE_NAMES = (
    "is_noop", "is_safe_direct", "is_benchmark", "risk_level",
    "action_available", "action_delta_normalized", "affects_nic",
    "affects_network_stack", "affects_cpu", "affects_fastpath",
    "traffic_utilization", "pps_pressure", "drop_error_pressure",
    "cpu_load", "softirq_pressure", "queue_pressure", "memory_pressure",
    "recent_reward_mean", "recent_success_rate", "negative_streak",
)
MIN_SAMPLES_DEFAULT = 8
WARMING_SAMPLES_DEFAULT = 3
CONFIDENCE_CONSERVATIVE_DEFAULT = 0.65
CONFIDENCE_ASSISTED_DEFAULT = 0.75


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value if isfinite(value) else low))


def action_family(action_id: str) -> str:
    prefix = (action_id or "").split(".", 1)[0]
    return {
        "pm": "noop", "nic": "nic", "network": "network-stack",
        "netdev": "queue", "cpu": "cpu", "fastpath": "fastpath",
        "service": "service", "qdisc": "queue", "tcp": "network-stack",
    }.get(prefix, "service")


def build_features(action: dict[str, Any], telemetry: dict[str, Any] | None = None,
                    history: dict[str, Any] | None = None) -> list[float]:
    telemetry = telemetry or {}
    history = history or {}
    action_id = action.get("id", "")
    family = action_family(action_id)
    risk = action.get("risk", "none")
    health = telemetry.get("health") or {}
    cpu = health.get("cpu") or {}
    interfaces = telemetry.get("interfaces") or {}
    rx = sum(float(v.get("rxBytes", 0) or 0) for v in interfaces.values())
    tx = sum(float(v.get("txBytes", 0) or 0) for v in interfaces.values())
    traffic = clamp((rx + tx) / max(1.0, float(telemetry.get("trafficCapacity", 1) or 1)))
    softnet = telemetry.get("softnet") or {}
    drops = float(softnet.get("dropped", 0) or 0)
    errors = float(softnet.get("timeSqueezed", 0) or 0)
    return [
        float(action_id == "pm.noop"), float(action.get("executionAuthority") == "safe-direct"),
        float(action.get("executionAuthority") == "benchmark"),
        {"none": 0.0, "safe": 0.2, "benchmark": 0.7, "unsafe": 1.0}.get(risk, 1.0),
        float(action.get("available", True) is True),
        clamp(float(action.get("deltaNormalized", 0.0) or 0.0)),
        float(family == "nic"), float(family in {"network-stack", "queue"}),
        float(family == "cpu"), float(family == "fastpath"), traffic,
        clamp(float(telemetry.get("ppsPressure", 0.0) or 0.0)),
        clamp((drops + errors) / max(1.0, float(telemetry.get("dropCapacity", 1) or 1))),
        clamp(float(health.get("load1", 0.0) or 0.0) / max(1.0, float(cpu.get("count", 1) or 1) * 2.0)),
        clamp(float(telemetry.get("softirqPressure", 0.0) or 0.0)),
        clamp(float(telemetry.get("queuePressure", 0.0) or 0.0)),
        clamp(1.0 - float(health.get("memAvailableKiB", 0.0) or 0.0) / max(1.0, float(telemetry.get("memoryKiB", 1) or 1))),
        clamp(float(history.get("recentRewardMean", 0.0) or 0.0), -1.0, 1.0),
        clamp(float(history.get("successRate", 0.0) or 0.0)),
        clamp(float(history.get("negativeStreak", 0.0) or 0.0) / 3.0),
    ]


def build_reward(goal: str, control: dict[str, Any], candidate: dict[str, Any],
                 control_telemetry: dict[str, Any] | None = None,
                 candidate_telemetry: dict[str, Any] | None = None,
                 health_regressed: bool = False) -> dict[str, Any]:
    control_telemetry = control_telemetry or {}
    candidate_telemetry = candidate_telemetry or {}
    c_bps = float(control.get("bitsPerSecond", 0) or 0)
    n_bps = float(candidate.get("bitsPerSecond", 0) or 0)
    if c_bps <= 0 or n_bps <= 0 or health_regressed:
        return {"goal": goal, "reward": None, "components": {}, "measurementQuality": "controlled_ab", "validated": False,
                "reason": "health-regression" if health_regressed else "missing-throughput-evidence"}
    throughput = (n_bps - c_bps) / c_bps
    c_latency = control.get("latencyMs")
    n_latency = candidate.get("latencyMs")
    latency = None if c_latency is None or n_latency is None or float(c_latency) <= 0 else (float(c_latency) - float(n_latency)) / float(c_latency)
    c_cpu = control.get("cpuBusy") if control.get("cpuBusy") is not None else (((control_telemetry.get("health") or {}).get("cpu") or {}).get("busyPct"))
    n_cpu = candidate.get("cpuBusy") if candidate.get("cpuBusy") is not None else (((candidate_telemetry.get("health") or {}).get("cpu") or {}).get("busyPct"))
    cpu_eff = None
    if c_cpu is not None and n_cpu is not None and float(c_cpu) >= 0:
        # Comparable throughput-per-busy-unit; requires both legs from Core.
        cpu_eff = ((n_bps / max(float(n_cpu), 0.01)) - (c_bps / max(float(c_cpu), 0.01))) / max(c_bps / max(float(c_cpu), 0.01), 0.01)
    components = {"throughput": throughput, "latency": latency, "cpuEfficiency": cpu_eff}
    required = {"throughput": throughput, "latency": latency, "cpu_efficiency": cpu_eff, "balanced": (throughput, latency, cpu_eff)}.get(goal)
    if goal == "balanced":
        if latency is None or cpu_eff is None:
            return {"goal": goal, "reward": None, "components": components, "measurementQuality": "controlled_ab", "validated": False,
                    "reason": "missing-balanced-evidence"}
        reward = 0.45 * throughput + 0.35 * latency + 0.20 * cpu_eff
    elif required is None:
        return {"goal": goal, "reward": None, "components": components, "measurementQuality": "controlled_ab", "validated": False, "reason": "unsupported-goal"}
    else:
        reward = float(required)
    return {"goal": goal, "reward": reward, "components": components, "measurementQuality": "controlled_ab", "validated": True, "reason": "validated-controlled-ab"}


def learning_stage(validated_samples: int, confidence: float, drifted: bool,
                   minimum_samples: int = MIN_SAMPLES_DEFAULT) -> str:
    if drifted:
        return "drifted"
    if validated_samples < WARMING_SAMPLES_DEFAULT:
        return "cold"
    if validated_samples < minimum_samples or confidence < 0.65:
        return "warming"
    return "ready"


def cooldown_until(now_ms: int, *, last_execution_ms: int | None = None,
                   negative_streak: int = 0, rollback: bool = False,
                   failed: bool = False, base_seconds: int = 600) -> int:
    if rollback:
        return now_ms + 3600 * 1000
    if failed:
        return now_ms + min(6 * 3600 * 1000, base_seconds * 1000 * max(2, 2 ** min(5, negative_streak)))
    if negative_streak > 0:
        return now_ms + 1800 * 1000
    return now_ms + base_seconds * 1000


@dataclass(frozen=True)
class Selection:
    selected_action_id: str
    source: str
    auto_eligible: bool
    reason: str
    decision_id: str | None = None


def select_smart_action(mode: str, candidates: list[dict[str, Any]], *, rill_state: str,
                        learning: str, confidence: float, ranking: list[dict[str, Any]] | None,
                        decision_id: str | None = None, selected_action_id: str | None = None,
                        minimum_confidence: float | None = None) -> Selection:
    minimum_confidence = minimum_confidence or (CONFIDENCE_ASSISTED_DEFAULT if mode == "assisted" else CONFIDENCE_CONSERVATIVE_DEFAULT)
    legal = [a for a in candidates if a.get("available", True) and
             (a.get("id") == "pm.noop" or (a.get("executionAuthority") == "safe-direct" and a.get("risk") == "safe"))]
    fallback = next((a["id"] for a in legal if a["id"] != "pm.noop"), "pm.noop")
    if rill_state not in {"available", "learning"} or learning != "ready":
        return Selection(fallback, "core-fallback", True, f"rill-{learning}")
    if not selected_action_id or not decision_id:
        return Selection(fallback, "core-fallback", True, "missing-exact-decision")
    action = next((a for a in legal if a["id"] == selected_action_id), None)
    if action is None:
        return Selection(fallback, "core-fallback", True, "rill-action-not-legal")
    if confidence < minimum_confidence:
        return Selection(fallback, "core-fallback", True, "confidence-below-policy")
    if action["id"] == "pm.noop":
        return Selection("pm.noop", "rill", True, "rill-selected-noop", decision_id)
    return Selection(action["id"], "rill", True, "highest-ranked-eligible-action", decision_id)
