#!/usr/bin/env python3
"""Read-only/benchmark endpoint companion for OpenWrt Performance Manager.

The companion never mutates router configuration. Benchmark traffic only runs
when a human explicitly invokes `server` or `client`; subprocesses use argv
arrays and no shell.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CONTRACT = "pm-companion/v2"
MAX_RESULT_BYTES = 2 * 1024 * 1024


def emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def capabilities(role: str) -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "role": role,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "iperf3": shutil.which("iperf3"),
        "python": platform.python_version(),
        "authority": "endpoint-benchmark-only",
        "routerMutation": False,
    }


def run_iperf(argv: list[str], timeout: int) -> dict[str, Any]:
    if not shutil.which("iperf3"):
        return {"ok": False, "error": "iperf3-not-installed", "argv": argv[:1]}
    try:
        cp = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "iperf3-timeout"}
    raw = cp.stdout[-MAX_RESULT_BYTES:]
    if cp.returncode != 0:
        return {"ok": False, "error": "iperf3-failed", "returncode": cp.returncode, "stderr": cp.stderr[-4096:]}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "iperf3-invalid-json"}
    end = data.get("end", {})
    summary = end.get("sum_received") or end.get("sum") or end.get("sum_sent") or {}
    return {
        "ok": True,
        "bitsPerSecond": float(summary.get("bits_per_second") or 0.0),
        "seconds": float(summary.get("seconds") or 0.0),
        "retransmits": int((end.get("sum_sent") or {}).get("retransmits") or 0),
        "iperf3": data,
    }


def cmd_server(args: argparse.Namespace) -> int:
    # One-shot server: explicit invocation, bounded by process timeout.
    argv = ["iperf3", "-s", "-1", "-J", "-p", str(args.port)]
    if args.bind:
        argv += ["-B", args.bind]
    result = run_iperf(argv, args.timeout)
    emit({"contract": CONTRACT, "role": "wan-server", "capturedEpoch": int(time.time()), **result})
    return 0 if result.get("ok") else 2


def cmd_client(args: argparse.Namespace) -> int:
    argv = ["iperf3", "-c", args.host, "-J", "-p", str(args.port), "-t", str(args.seconds)]
    if args.reverse:
        argv.append("-R")
    if args.parallel > 1:
        argv += ["-P", str(args.parallel)]
    result = run_iperf(argv, args.seconds + args.timeout_slack)
    # Canonical measurement methodology (Blocker 3).  Control and candidate
    # legs of a controlled A/B must reproduce this exact fingerprint so the
    # Core can reject a mismatched experiment instead of rewarding it.
    tool_version = (result.get("iperf3") or {}).get("start", {}).get("version")
    methodology = {
        "host": args.host,
        "port": args.port,
        "reverse": bool(args.reverse),
        "parallel": int(args.parallel),
        "duration": int(args.seconds),
        "protocol": "iperf3-tcp",
        "tool": "iperf3",
        "toolVersion": tool_version,
    }
    envelope = {
        "contract": CONTRACT,
        "role": args.role,
        "capturedEpoch": int(time.time()),
        "sessionId": args.session_id,
        "phase": args.phase,
        "actionId": args.action_id,
        "pathId": args.path_id,
        "topologyGeneration": args.topology_generation,
        "routeIdentity": args.route_identity,
        "capabilityHash": args.capability_hash,
        "endpoint": {"host": args.host, "port": args.port, "reverse": args.reverse, "parallel": args.parallel, "tool": "iperf3"},
        "methodology": methodology,
        **result,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
    emit(envelope)
    return 0 if result.get("ok") else 2


def load_result(path: str) -> dict[str, Any]:
    p = Path(path)
    if p.stat().st_size > MAX_RESULT_BYTES:
        raise ValueError("result-too-large")
    obj = json.loads(p.read_text())
    if obj.get("contract") != CONTRACT or obj.get("ok") is not True:
        raise ValueError("invalid-companion-result")
    bps = float(obj.get("bitsPerSecond") or 0.0)
    if bps <= 0:
        raise ValueError("non-positive-throughput")
    return obj


def compare_results(control: dict[str, Any], candidate: dict[str, Any], action_id: str, path_id: str,
                    topology_generation: int | None, route_identity: str | None) -> dict[str, Any]:
    c0 = float(control["bitsPerSecond"])
    c1 = float(candidate["bitsPerSecond"])
    reward = (c1 - c0) / c0
    return {
        "contract": CONTRACT,
        "measurementClass": "controlled_ab",
        "validated": True,
        "validationScope": "endpoint-measurement-only",
        "actionId": action_id,
        "pathId": path_id,
        "topologyGeneration": topology_generation,
        "routeIdentity": route_identity,
        "oneVariable": True,
        "control": {"bitsPerSecond": c0, "retransmits": control.get("retransmits", 0)},
        "candidate": {"bitsPerSecond": c1, "retransmits": candidate.get("retransmits", 0)},
        "reward": reward,
        "note": "This envelope validates endpoint measurements only. Core must still validate topology, route identity, action transaction and rollback before treating it as a learning outcome.",
    }


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        control = load_result(args.control)
        candidate = load_result(args.candidate)
        out = compare_results(control, candidate, args.action_id, args.path_id, args.topology_generation, args.route_identity)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"contract": CONTRACT, "ok": False, "error": str(exc)})
        return 2
    if args.output:
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    emit({"ok": True, **out})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Performance Manager explicit benchmark endpoint companion")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capabilities")
    c.add_argument("--role", choices=["lan-client", "router-local-client", "wan-server", "observer"], default="observer")
    c.set_defaults(func=lambda a: (emit(capabilities(a.role)) or 0))

    s = sub.add_parser("server")
    s.add_argument("--bind")
    s.add_argument("--port", type=int, default=5201, choices=range(1, 65536), metavar="PORT")
    s.add_argument("--timeout", type=int, default=120)
    s.set_defaults(func=cmd_server)

    c = sub.add_parser("client")
    c.add_argument("--host", required=True)
    c.add_argument("--role", choices=["lan-client", "router-local-client"], default="lan-client")
    c.add_argument("--session-id")
    c.add_argument("--phase", choices=["control", "candidate"])
    c.add_argument("--action-id")
    c.add_argument("--path-id", default="path:lan-to-wan")
    c.add_argument("--topology-generation", type=int)
    c.add_argument("--route-identity")
    c.add_argument("--capability-hash")
    c.add_argument("--port", type=int, default=5201, choices=range(1, 65536), metavar="PORT")
    c.add_argument("--seconds", type=int, default=10, choices=range(1, 61), metavar="SECONDS")
    c.add_argument("--parallel", type=int, default=1, choices=range(1, 17), metavar="N")
    c.add_argument("--reverse", action="store_true")
    c.add_argument("--timeout-slack", type=int, default=15)
    c.add_argument("--output")
    c.set_defaults(func=cmd_client)

    c = sub.add_parser("compare")
    c.add_argument("--control", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--action-id", required=True)
    c.add_argument("--path-id", default="path:lan-to-wan")
    c.add_argument("--topology-generation", type=int)
    c.add_argument("--route-identity")
    c.add_argument("--output")
    c.set_defaults(func=cmd_compare)
    return p



if __name__ == "__main__":
    # Parse exactly once; kept separate from the helpers so tests can import safely.
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))
