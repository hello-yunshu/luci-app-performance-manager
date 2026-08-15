#!/usr/bin/env python3
"""Pure reference model for frozen safety contracts.

This is deliberately independent from the ucode runtime.  Tests use it to
exercise state-machine decisions and evidence validation with fixtures; source
gates separately assert that the runtime exposes the corresponding mechanisms.
"""
from __future__ import annotations
from typing import Any

ACTIVE_TX = {"pending", "applied", "verified", "awaiting_confirm"}


def recovery_decision(tx: dict[str, Any], current_boot: str, now_ms: int) -> str:
    if tx.get("state") not in ACTIVE_TX:
        return "ignore"
    if tx.get("bootId") != current_boot:
        return "cross-boot-clear-marker-no-stale-replay"
    state = tx.get("state")
    if state == "awaiting_confirm":
        deadline = tx.get("deadlineMonotonicMs")
        if deadline is None:
            return "rollback-missing-deadline"
        if now_ms >= int(deadline):
            return "rollback-timeout"
        return "rearm-timer"
    return "rollback-core-crash"


def benchmark_context(session: dict[str, Any]) -> tuple[Any, ...]:
    return (
        session.get("capabilityHash"),
        session.get("topologyGeneration"),
        session.get("routeIdentity"),
        session.get("evaluationPath"),
        session.get("actionId"),
    )


def validate_companion_evidence(e: dict[str, Any], session: dict[str, Any], phase: str) -> tuple[bool, str | None]:
    if not isinstance(e, dict) or e.get("contract") != "pm-companion/v2":
        return False, "invalid-companion-evidence"
    required_role = ((session.get("companion") or {}).get("requiredRole"))
    if e.get("role") != required_role or e.get("ok") is not True:
        return False, "invalid-companion-evidence"
    try:
        if float(e.get("bitsPerSecond", 0)) <= 0:
            return False, "invalid-companion-evidence"
    except (TypeError, ValueError):
        return False, "invalid-companion-evidence"
    if (e.get("sessionId"), e.get("phase"), e.get("actionId"), e.get("pathId")) != (
        session.get("sessionId"), phase, session.get("actionId"), session.get("evaluationPath")
    ):
        return False, "companion-context-mismatch"
    if (e.get("capabilityHash"), e.get("topologyGeneration"), e.get("routeIdentity")) != (
        session.get("capabilityHash"), session.get("topologyGeneration"), session.get("routeIdentity")
    ):
        return False, "companion-context-drift"
    return True, None


def controlled_ab_reward(control_bps: float, candidate_bps: float) -> float:
    control = float(control_bps)
    candidate = float(candidate_bps)
    if control <= 0 or candidate <= 0:
        raise ValueError("throughput-must-be-positive")
    return (candidate - control) / control


def health_regressions(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("lan", "wan", "dns", "ipv4", "ipv6", "proxy", "vpn", "route"):
        if before.get(key) is True and after.get(key) is not True:
            failures.append(f"{key}:healthy-to-unhealthy")
    if before.get("recentOom") is False and after.get("recentOom") is True:
        failures.append("oom:new")
    bt = (before.get("thermal") or {}).get("throttleCount")
    at = (after.get("thermal") or {}).get("throttleCount")
    if bt is not None and at is not None and at > bt:
        failures.append("thermal:new-throttle")
    return failures


def ownership_cleanup_decision(*, owner: str, target_resolved: bool, lease_boot: str | None, current_boot: str, lease_complete: bool, live_matches_owned: bool) -> str:
    """Reference decision for uninstall cleanup of PM-owned runtime leases.

    The key invariant is that uninstall may restore only a value this boot's
    runtime lease still demonstrably owns.  Otherwise it removes replay intent
    while preserving live state.
    """
    if owner != "performance_manager":
        return "ignore-not-owned"
    if not target_resolved or not lease_complete or lease_boot != current_boot:
        return "remove-intent-runtime-untouched"
    if not live_matches_owned:
        return "preserve-live-remove-intent"
    return "restore-lease-before-remove-intent"


def benchmark_lock_decision(*, domain: str, existing_session_active: bool, existing_same_boot: bool, existing_session_id: str | None, new_session_id: str) -> str:
    """Reference decision for the benchmark experiment-domain lock.

    Any two simultaneous controlled A/B candidates would attribute one
    throughput delta to two changed variables, so every active experiment is
    globally exclusive regardless of tuning domain.
    """
    if not existing_session_active or not existing_same_boot:
        return "acquire"
    if existing_session_id != new_session_id:
        return "reject-active-benchmark-exclusive"
    return "acquire-same-session"


def benchmark_lock_domain(action_id: str, plan_scope: str) -> str:
    """System/service and device/path experiments share one global domain."""
    return "benchmark:global"


def benchmark_masked_uci_keys(action_id: str) -> list[str]:
    """Keys a benchmark candidate itself mutates; they are excluded from the
    integration fingerprint so the candidate does not self-trigger drift."""
    if action_id in ("fastpath.software_flow_offload", "fastpath.hardware_flow_offload"):
        return ["firewall.@defaults[0].flow_offloading", "firewall.@defaults[0].flow_offloading_hw"]
    return []


def benchmark_context_drift(frozen: dict[str, Any], now: dict[str, Any]) -> list[str]:
    """Full frozen-context drift: capability/topology/route identity plus the
    canonical integration fingerprint and workload class."""
    reasons: list[str] = []
    if frozen.get("capabilityHash") != now.get("capabilityHash"):
        reasons.append("capability")
    if frozen.get("topologyGeneration") != now.get("topologyGeneration"):
        reasons.append("topology")
    if frozen.get("routeIdentity") != now.get("routeIdentity"):
        reasons.append("route")
    if frozen.get("integrationFingerprint") != now.get("integrationFingerprint"):
        reasons.append("integration")
    if sorted(frozen.get("workloadClass") or []) != sorted(now.get("workloadClass") or []):
        reasons.append("workload")
    return reasons


def rill_context_key(*, profile: str, capability_hash: str, topology_generation: int, path_id: str, route_identity: str, workload_class: list[str], integration_fingerprint: str) -> str:
    """Canonical bounded ContextKey shared by observe and outcome payloads.

    The exact same components (with stable hashing) must produce the same key
    so Rill's model partitions align between observations and outcomes.
    """
    from hashlib import blake2b

    def digest(value: str) -> str:
        return blake2b(value.encode(), digest_size=4).hexdigest()

    route_class = "unresolved" if route_identity == "unresolved" else digest(route_identity)
    integ_class = digest(integration_fingerprint)
    workload_class_h = digest("|".join(sorted(workload_class)))
    return "ctx-v1:profile=%s;cap=%s;topo=%d;path=%s;route=%s;workload=%s;integ=%s" % (
        profile, capability_hash, topology_generation, path_id, route_class, workload_class_h, integ_class)


def rill_outcome_context_binding(payload: dict[str, Any]) -> str | None:
    """Outcomes must carry the context key; absence means no binding."""
    key = payload.get("contextKey")
    return key if isinstance(key, str) and key.startswith("ctx-v1:") else None


# ---------------------------------------------------------------------------
# rc.3 High-item / Blocker behavioral reference models.  These mirror the
# ucode runtime logic so behavioral fixtures can assert REAL semantics rather
# than a substring.  source_gates separately asserts the runtime exposes the
# matching mechanism.
# ---------------------------------------------------------------------------

WORKLOAD_CLASSES = ["plain_forwarding", "local_endpoint", "transparent_proxy",
                    "vpn_tunnel", "pppoe", "wireless", "storage_service"]


def underlay_target(devices: dict[str, str | None], start: str | None) -> tuple[list[str], str | None]:
    """Resolve a logical interface to its real underlay NIC chain and the first
    stable physical/virtual NIC in it.  `devices` maps name -> parent (netifd
    device dump).  Mirrors Core's underlay_chain(): the chain is walked fully
    (bridge -> VLAN -> PPPoE -> tunnel -> NIC) and only a true physical/virtual
    NIC (pure eth/wlan/phy, no VLAN/bridge decoration) is the stable target, so
    an intermediate `eth1.100` VLAN is part of the chain but is not the target."""
    import re
    chain: list[str] = []
    seen: set[str] = set()
    cur = start
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        if re.fullmatch(r"(eth\d+|wlan\d+|phy\d+)", cur):
            return chain, cur  # stable physical/virtual NIC
        cur = devices.get(cur)
    return (chain, chain[-1] if chain else None) if chain else ([], None)


def derive_workload_class(*, proto: str | None, transparent_proxy: bool, vpn: bool,
                          underlay_chain: list[str], local_endpoint: bool = False,
                          storage_chain: bool = False) -> list[str]:
    """Derive Workload Class from evidence (never hard-coded).  Mirrors Core's
    derive_workload() and workload_for_paths()."""
    wl: list[str] = []
    def _add(v: str) -> None:
        if v not in wl:
            wl.append(v)
    if proto == "pppoe":
        _add("pppoe")
    if transparent_proxy:
        _add("transparent_proxy")
    if vpn:
        _add("vpn_tunnel")
    if any(n.startswith("wlan") for n in (underlay_chain or [])):
        _add("wireless")
    if local_endpoint:
        _add("local_endpoint")
    if storage_chain or any(("storage" in n) or n.startswith("eth") and "-swp" in n for n in (underlay_chain or [])):
        _add("storage_service")
    if not wl:
        _add("plain_forwarding")
    return wl


def measurement_methodology(*, host: str | None, port, reverse: bool, parallel, duration,
                            protocol: str = "iperf3-tcp", tool: str = "iperf3",
                            tool_version: str | None = None) -> tuple[str, ...]:
    """Canonical frozen measurement fingerprint (Blocker 3)."""
    return (host, port, "R" if reverse else "F", max(1, int(parallel or 1)),
            int(duration or 0), protocol, tool, tool_version)


def methodology_matches(control_methodology: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
    return control_methodology == candidate


def goal_measurement(goal: str) -> str | None:
    """Which measurement a Goal genuinely needs.  An unsupported Goal must not
    silently degrade to throughput (Blocker 2)."""
    return {"balanced": "throughput", "throughput": "throughput",
            "latency": None, "cpu_efficiency": None}.get(goal)


def replay_cede_decision(*, has_owned_lease: bool, owned_ring: str | None, live_ring: str | None) -> str:
    """Policy replay ownership (Blocker 4): if a PM-owned lease exists and the
    live value no longer matches what PM owns, relinquish and do NOT replay.
    Status string matches the Core's emitted `ceded-live-drift`."""
    if not has_owned_lease or owned_ring is None:
        return "replay"
    if live_ring != owned_ring:
        return "ceded-live-drift"
    return "replay"


def nft_ruleset_fingerprint(ruleset_text: str, masked_keys: list[str] | None = None) -> int | None:
    """Canonical live nft ruleset identity: strip volatile packet/byte counters
    so the fingerprint reflects topology, not transient traffic (9.6)."""
    import re
    stripped = re.sub(r'"packets":\s*[0-9]+,\s*"bytes":\s*[0-9]+', '', ruleset_text)
    if not stripped.strip():
        return None
    if masked_keys and "fastpath-mask-nft" in masked_keys:
        return hash(("masked", stripped)) & 0xFFFFFFFF
    return hash(stripped) & 0xFFFFFFFF
