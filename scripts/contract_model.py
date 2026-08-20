#!/usr/bin/env python3
"""Pure reference model for frozen safety contracts.

This is deliberately independent from the ucode runtime.  Tests use it to
exercise state-machine decisions and evidence validation with fixtures; source
gates separately assert that the runtime exposes the corresponding mechanisms.
"""
from __future__ import annotations
from typing import Any

ACTIVE_TX = {"pending", "applied", "verified", "awaiting_confirm"}


def reserve_rill_decision(bindings: dict[str, dict[str, Any]], journals: dict[str, dict[str, Any]],
                          *, decision_id: str, action_id: str, authority: str,
                          owner_type: str, owner_id: str) -> tuple[bool, str]:
    """Executable reference for the Core's single-owner reservation CAS."""
    binding = bindings.get(decision_id)
    if not binding or journals.get(decision_id):
        return False, "rill-decision-already-reserved"
    if binding.get("actionId") != action_id or binding.get("executionAuthority") != authority:
        return False, "rill-decision-binding-invalid"
    if owner_type not in {"transaction", "benchmark"} or not owner_id:
        return False, "rill-owner-invalid"
    journals[decision_id] = {
        "decisionId": decision_id, "actionId": action_id, "executionAuthority": authority,
        "ownerType": owner_type, "ownerId": owner_id, "executionState": "reserved",
        "mutationStarted": False, "mayHaveReachedPeer": False,
    }
    del bindings[decision_id]
    return True, "reserved"


def release_rill_reservation(bindings: dict[str, dict[str, Any]], journals: dict[str, dict[str, Any]],
                             frozen: dict[str, Any]) -> bool:
    journal = journals.get(frozen.get("decisionId"))
    if not journal or journal.get("mutationStarted") is True:
        return False
    if (journal.get("ownerType"), journal.get("ownerId")) != (frozen.get("ownerType"), frozen.get("ownerId")):
        return False
    del journals[frozen["decisionId"]]
    bindings[frozen["decisionId"]] = dict(frozen)
    return True


def transport_stage(*, connected: bool, bytes_sent: int, request_bytes: int,
                    response_received: bool, response_valid: bool = False) -> dict[str, Any]:
    fully_sent = connected and request_bytes > 0 and bytes_sent == request_bytes
    if not connected:
        state = "connect-failed"
    elif not fully_sent:
        state = "send-failed"
    elif not response_received:
        state = "response-lost-after-send"
    elif not response_valid:
        state = "bad-response-after-send"
    else:
        state = "response-received"
    return {"state": state, "connected": connected, "fullySent": fully_sent,
            "responseReceived": response_received, "mayHaveReachedPeer": fully_sent}


def recover_rill_execution(journal: dict[str, Any], *, current_boot: str,
                           owner_state: str | None = None) -> str:
    state = journal.get("executionState")
    if state in {"outcome-pending", "sent-unknown"}:
        return "retry-with-immutable-outcome"
    if state == "outcome-prepared":
        if owner_state == journal.get("expectedOwnerState"):
            return "arm-and-retry-with-immutable-outcome"
        if journal.get("createdBootId") != current_boot:
            return "retire-prepared-owner-not-terminal"
        return "leave-prepared"
    if state in {"reserved", "executing"} and journal.get("createdBootId") != current_boot:
        return "retire-no-auto-actuation"
    return "leave"


def reconcile_duplicate(*, code: str, persisted_fingerprint: str, current_fingerprint: str,
                        may_have_reached_peer: bool, persisted_owner: str, current_owner: str) -> str:
    if (code == "duplicateFeedback" and may_have_reached_peer
            and persisted_fingerprint == current_fingerprint and persisted_owner == current_owner):
        return "RECONCILED"
    return "TERMINAL_FAIL_CLOSED"


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
    integration fingerprint so the candidate does not self-trigger drift.
    The extra 'fastpath-expected-delta' marker (Blocker B) tells the benchmark
    context that the nft component must be verified by EXACT expected delta
    (nft_comparable) instead of being folded into the fingerprint, so only the
    candidate's own flowtable/flow-rule toggle is allowed to differ."""
    if action_id in ("fastpath.software_flow_offload", "fastpath.hardware_flow_offload"):
        return ["firewall.@defaults[0].flow_offloading", "firewall.@defaults[0].flow_offloading_hw", "fastpath-expected-delta"]
    return []


def benchmark_context_drift(frozen: dict[str, Any], now: dict[str, Any]) -> list[str]:
    """Full frozen-context drift: capability/topology/route identity plus the
    canonical integration fingerprint and workload class.  Fastpath sessions
    additionally verify the live nft ruleset by EXACT expected delta
    (Blocker B): the candidate may toggle exactly the PM flowtable/flow-rule
    and nothing else (unrelated flowtable/rule changes fail closed)."""
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
    if "nftSnapshot" in frozen or "nftSnapshot" in now:
        if not nft_comparable(frozen.get("nftSnapshot"), now.get("nftSnapshot")).get("comparable"):
            reasons.append("nft")
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


def nft_ruleset_fingerprint(ruleset_text: str) -> int | None:
    """Canonical FULL live nft ruleset identity (Blocker B): strip volatile
    packet/byte counters so the identity reflects topology, not transient
    traffic (9.6).  No component is masked — fastpath candidates verify the
    nft ruleset by EXACT expected delta (nft_comparable) instead."""
    import re
    stripped = re.sub(r'"packets":\s*[0-9]+,\s*"bytes":\s*[0-9]+', '', ruleset_text)
    if not stripped.strip():
        return None
    return hash(stripped) & 0xFFFFFFFF


# -- Expected Delta (Blocker B) ---------------------------------------------
# fastpath A/B attribution no longer uses a global "ignore all flowtable/flow
# rule" mask, which also hid unrelated external changes.  Instead the control
# and candidate nft rulesets are structurally compared and the delta must be
# EXACTLY the PM candidate's own flowtable/flow-rule toggle.  Anything else
# (an unrelated rule, a second flowtable, an in-place mutation of the PM
# flowtable/rule) invalidates the experiment (fail-closed).  These mirror the
# real Core ucode functions so unit tests assert the same semantics.

# Exact identity of the ONLY nft structures a firewall4 fastpath candidate is
# allowed to toggle.  Everything else must stay byte-identical across the
# control/candidate snapshots.
FASTPATH_FLOWTABLE = {"family": "inet", "table": "fw4", "name": "ft"}
FASTPATH_FLOW_RULE = {"family": "inet", "table": "fw4", "chain": "forward", "ref": "@ft"}


def nft_canon(value) -> str:
    """Canonical structural serialization of one nft item.  Volatile identity
    (handle) and live counters (packets/bytes) are dropped so the snapshot
    reflects topology, not transient traffic or allocation order."""
    if isinstance(value, dict):
        parts = []
        for k in sorted(value):
            if k in ("handle", "packets", "bytes"):
                continue
            parts.append(f"{k}={nft_canon(value[k])}")
        return "{" + ",".join(parts) + "}"
    if isinstance(value, list):
        parts = sorted(nft_canon(v) for v in value)
        return "[" + ",".join(parts) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{int(value)}"
    if value is None:
        return "null"
    return f'"{value}"'


def nft_item_matches_spec(item, spec: str) -> bool:
    """Does one parsed nft element match the exact PM fastpath structure?
    `spec` is 'flowtable' (exact family/table/name) or 'flowrule' (exact
    family/table/chain + `flow add @ft`).  Structural content beyond the
    identity is intentionally NOT matched, so an in-place mutation of the PM
    flowtable/rule surfaces as a delta instead of being silently accepted."""
    kind = next(iter(item)) if isinstance(item, dict) and item else None
    if spec == "flowtable":
        if kind != "flowtable":
            return False
        ft = item.get("flowtable") or {}
        return (ft.get("family") == FASTPATH_FLOWTABLE["family"]
                and ft.get("table") == FASTPATH_FLOWTABLE["table"]
                and ft.get("name") == FASTPATH_FLOWTABLE["name"])
    if spec == "flowrule":
        if kind != "rule":
            return False
        r = item.get("rule") or {}
        if (r.get("family") != FASTPATH_FLOW_RULE["family"]
                or r.get("table") != FASTPATH_FLOW_RULE["table"]
                or r.get("chain") != FASTPATH_FLOW_RULE["chain"]):
            return False
        flow = r.get("flow") or {}
        return flow.get("add") == FASTPATH_FLOW_RULE["ref"]
    return False


def nft_item_in(items: list, item) -> bool:
    canon = nft_canon(item)
    return any(nft_canon(it) == canon for it in items)


def nft_delta_is_expected(control: list, candidate: list) -> dict:
    """Structural delta between two parsed nft element lists (metainfo
    dropped).  ok == True ONLY when the delta is exactly the PM flowtable
    `ft` + `flow add @ft` rule toggled on one side (add or remove), with no
    unrelated change and no in-place mutation of those structures."""
    added = [c for c in candidate if not nft_item_in(control, c)]
    removed = [c for c in control if not nft_item_in(candidate, c)]
    ft_added = rule_added = ft_removed = rule_removed = 0
    unrelated: list[str] = []
    for it in added:
        if nft_item_matches_spec(it, "flowtable"):
            ft_added += 1
        elif nft_item_matches_spec(it, "flowrule"):
            rule_added += 1
        else:
            unrelated.append(f"added:{nft_canon(it)}")
    for it in removed:
        if nft_item_matches_spec(it, "flowtable"):
            ft_removed += 1
        elif nft_item_matches_spec(it, "flowrule"):
            rule_removed += 1
        else:
            unrelated.append(f"removed:{nft_canon(it)}")
    add_side = ft_added + rule_added
    rm_side = ft_removed + rule_removed
    ok = (not unrelated
          and ((add_side == 2 and rm_side == 0 and ft_added == 1 and rule_added == 1)
               or (rm_side == 2 and add_side == 0 and ft_removed == 1 and rule_removed == 1)))
    return {"ok": ok,
            "added": [nft_canon(it) for it in added],
            "removed": [nft_canon(it) for it in removed],
            "unrelated": unrelated}


def nft_snapshot(ruleset_text: str) -> dict | None:
    """Parse `nft -j list ruleset` JSON text into {items, parsed, canonical}
    (metainfo dropped) or None when nft output is empty/unparseable."""
    import json
    if not ruleset_text or not ruleset_text.strip():
        return None
    try:
        root = json.loads(ruleset_text)
    except Exception:
        return None
    items = root.get("nftables") if isinstance(root, dict) else None
    if not items:
        return None
    parsed = [it for it in items if not (isinstance(it, dict) and "metainfo" in it)]
    if not parsed:
        return None
    parts = sorted(nft_canon(it) for it in parsed)
    return {"items": parts, "parsed": parsed, "canonical": "\n".join(parts)}


def nft_comparable(control_snapshot, candidate_snapshot) -> dict:
    """Expected-delta comparability for controlled fastpath A/B.  The control
    and candidate snapshots must differ by EXACTLY the PM flowtable/flow-rule
    toggle.  If either snapshot is unavailable, the experiment FAILS CLOSED
    (not comparable) rather than guessing."""
    a, b = control_snapshot, candidate_snapshot
    if a is None or b is None:
        return {"comparable": False, "reason": "nft-snapshot-unavailable", "control": a, "candidate": b}
    d = nft_delta_is_expected(a.get("parsed") or [], b.get("parsed") or [])
    return {"comparable": d["ok"], "reason": "expected-delta" if d["ok"] else "unexpected-nft-delta", "delta": d}


# -- Rill v1 causal binding / response semantics ---------------------------

RILL_CONTRACT = "pm-rill-shadow"
RILL_PROTOCOL_VERSION = 1


def validate_rill_envelope(request: dict, response: object) -> tuple[bool, str | None]:
    if not isinstance(response, dict):
        return False, "response-not-object"
    if response.get("contract") != RILL_CONTRACT:
        return False, "wrong-contract"
    if response.get("protocolVersion") != RILL_PROTOCOL_VERSION:
        return False, "wrong-protocol"
    if response.get("requestId") != request.get("requestId"):
        return False, "request-id-mismatch"
    if not isinstance(response.get("ok"), bool):
        return False, "ok-not-boolean"
    return True, None


def validate_rill_observe_response(request: dict, response: object) -> tuple[bool, str | None]:
    import math
    import re
    ok, reason = validate_rill_envelope(request, response)
    if not ok:
        return ok, reason
    assert isinstance(response, dict)
    if response.get("ok") is not True:
        return False, ((response.get("error") or {}).get("code") or "observe-rejected")
    if re.fullmatch(r"[0-9a-f]{32}", str(response.get("decisionId") or "")) is None:
        return False, "decision-id-invalid"
    rec = response.get("recommendation")
    if not isinstance(rec, dict) or not rec.get("actionId") or rec.get("advisory") is not True:
        return False, "recommendation-invalid"
    confidence = rec.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return False, "confidence-invalid"
    available = {a.get("id") for a in request.get("availableActions", []) if isinstance(a, dict)}
    if rec.get("actionId") not in available:
        return False, "recommendation-action-unknown"
    return True, None


def validate_rill_outcome_response(request: dict, response: object) -> tuple[bool, str | None]:
    ok, reason = validate_rill_envelope(request, response)
    if not ok:
        return ok, reason
    assert isinstance(response, dict)
    if response.get("ok") is not True:
        return False, ((response.get("error") or {}).get("code") or "outcome-rejected")
    if response.get("accepted") is not True:
        return False, "outcome-not-accepted"
    return True, None


def binding_is_valid(binding: object, *, boot_id: str, now_ms: int, ttl_ms: int = 3_600_000) -> bool:
    import re
    if not isinstance(binding, dict) or binding.get("schemaVersion") != 2:
        return False
    if re.fullmatch(r"[0-9a-f]{32}", str(binding.get("decisionId") or "")) is None:
        return False
    if not all(binding.get(k) for k in ("actionId", "contextKey", "goal", "bootId")):
        return False
    at_ms = binding.get("atMs")
    return (binding.get("bootId") == boot_id and binding.get("modelGeneration") == 1
            and isinstance(at_ms, int) and 0 <= now_ms - at_ms <= ttl_ms)


def outcome_resolution(*, transport_ok: bool, envelope_ok: bool, response: dict | None,
                       prior_response_loss: bool, same_fingerprint: bool) -> str:
    """Return the production binding lifecycle decision for one attempt."""
    if not transport_ok or not envelope_ok:
        return "KEEP_RETRYABLE"
    response = response or {}
    if response.get("ok") is True and response.get("accepted") is True:
        return "CONSUME_ACCEPTED"
    error = response.get("error") or {}
    if error.get("code") == "duplicateFeedback" and prior_response_loss and same_fingerprint:
        return "CONSUME_RECONCILED"
    if error.get("retryable") is True:
        return "KEEP_RETRYABLE"
    return "RETIRE_TERMINAL"
