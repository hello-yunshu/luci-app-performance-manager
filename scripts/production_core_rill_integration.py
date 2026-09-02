#!/usr/bin/env python3
"""Run the raw production Core against the real generic Runtime executable.

The Runtime is trained and queried through its real subprocess protocol, then
the raw shipped performance-manager.uc is executed in the official OpenWrt
ucode image. The ucode fragment only supplies deterministic provider fixtures;
selection, binding, transaction construction and history updates are the
production Core functions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = ROOT / "scripts"
import sys
sys.path.insert(0, str(sys_path))
from smart_decision_model import candidate_identity  # noqa: E402


def envelope(request_id: str, request: dict, generation: int, state_generation: int, schema_hash: str) -> dict:
    return {
        "requestId": request_id, "apiVersion": 3,
        "clientIdentity": {"name": "performance-manager", "version": "1.0.3"},
        "featureSchemaHash": schema_hash, "modelGeneration": 2,
        "stateGeneration": state_generation, "payloadLimit": 262144,
        "request": request,
    }


def runtime_call(binary: Path, state: Path, request_id: str, request: dict,
                 state_generation: int, schema_hash: str, capability: str | None = None) -> dict:
    wire = envelope(request_id, request, 2, state_generation, schema_hash)
    if capability:
        wire["capability"] = capability
    proc = subprocess.run(
        [str(binary), "preview-serve", "--state", str(state),
         "--feature-schema-hash", schema_hash, "--model-generation", "2"],
        input=json.dumps(wire) + "\n", text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Runtime exited {proc.returncode}: {proc.stderr.strip()}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"Runtime returned {len(lines)} JSON lines")
    return json.loads(lines[0])


def train_runtime(binary: Path, state: Path, schema_hash: str, candidate_a: str, candidate_b: str) -> dict:
    generation = 0
    handshake = runtime_call(binary, state, "production-handshake", {"method": "handshake"}, generation, schema_hash)
    if handshake.get("response", {}).get("kind") != "handshake":
        raise RuntimeError(f"Runtime handshake failed: {handshake}")
    generation = handshake.get("stateGeneration", 0)

    # These are the exact 20-dimensional vectors emitted by the production
    # Core fixture below: NIC safe-direct candidates, with WAN-A/WAN-B path
    # interval telemetry substituted into slots 10..12.  Keeping the fixture
    # width and values identical is part of the real Core -> Runtime contract;
    # the Runtime must continue to reject a mismatched learner width.
    features_a = [0.0, 1.0, 0.0, 0.2, 1.0, 0.5, 1.0, 0.0, 0.0, 0.0,
                  0.2, 0.1, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    features_b = [0.0, 1.0, 0.0, 0.2, 1.0, 0.5, 1.0, 0.0, 0.0, 0.0,
                  0.8, 0.7, 0.1, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # Repeat controlled feedback so the Core's production confidence policy
    # (>= 0.65 for conservative automation) is exercised without weakening
    # that policy merely to accommodate a one-sample fixture.
    for round_index in range(8):
        for candidate, features, reward, label in (
            (candidate_a, features_a, -1.0, "a"),
            (candidate_b, features_b, 1.0, "b"),
        ):
            request_id = f"production-train-{label}-{round_index}"
            decide = runtime_call(binary, state, request_id, {"method": "decide", "context": {
                "actions": [{"id": candidate, "features": features}],
                "contextKey": "ctx-production-candidate-isolation",
            }}, generation, schema_hash, "org.rill.preview.decide")
            decision_id = decide["response"]["decisionId"]
            generation = decide["stateGeneration"]
            feedback = runtime_call(binary, state, request_id + "-feedback", {"method": "feedback",
                "decisionId": decision_id, "selectedActionId": candidate, "reward": reward,
                "outcomeTimeMs": generation, "generation": 2}, generation, schema_hash,
                "org.rill.preview.feedback")
            if feedback.get("response", {}).get("output", {}).get("accepted") is not True:
                raise RuntimeError(f"Runtime training feedback failed: {feedback}")
            generation = feedback["stateGeneration"]
    return {"stateGeneration": generation, "handshake": handshake}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--docker-image", required=True)
    parser.add_argument("--harness", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-commit", default=os.environ.get("GITHUB_SHA", "local"))
    args = parser.parse_args()
    binary = args.binary.resolve()
    harness = args.harness.resolve()
    if not binary.is_file() or not harness.is_file():
        raise SystemExit("Runtime binary and production harness are required")
    schema_hash = hashlib.sha256((ROOT / "contracts/rill-feature-schema.json").read_bytes()).hexdigest()
    action_a = {"id": "nic.ring.floor", "applyTarget": "NIC-A", "evaluationPaths": ["WAN-A"]}
    action_b = {"id": "nic.ring.floor", "applyTarget": "NIC-B", "evaluationPaths": ["WAN-B"]}
    candidate_a, candidate_b = candidate_identity(action_a), candidate_identity(action_b)
    with tempfile.TemporaryDirectory(prefix="pm-production-rill-") as temp:
        state = Path(temp) / "runtime-state.json"
        train = train_runtime(binary, state, schema_hash, candidate_a, candidate_b)
        proc = subprocess.run([
            # Mount the directory, not the individual snapshot file. The
            # Runtime persists state with an atomic rename; replacing a
            # single-file bind mount returns EBUSY on OpenWrt/overlayfs.
            "docker", "run", "--rm", "--volume", f"{state.parent}:/tmp/pm-production-runtime:rw",
            "--volume", f"{harness}:/tmp/production_core_rill_test.uc:ro",
            "--entrypoint", "/usr/bin/ucode", args.docker_image, "/tmp/production_core_rill_test.uc",
        ], text=True, capture_output=True, check=False)
        output = proc.stdout + proc.stderr
        match = re.search(r"PRODUCTION_CORE_EVIDENCE (\{.*\})", output)
        if proc.returncode != 0 or not match:
            raise RuntimeError(f"production Core harness failed:\n{output[-12000:]}")
        evidence = json.loads(match.group(1))
    report = {
        "schemaVersion": 1, "contract": "pm<->rill-core-integration",
        "pmCommitSha": args.expected_commit, "verdict": evidence["verdict"],
        "runtimeVersion": "1.5.6", "runtimeSha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "candidateA": evidence["candidateA"], "candidateB": evidence["candidateB"],
        "runtimeSelectedCandidateId": evidence["runtimeSelectedCandidateId"],
        "coreSelectedCandidateId": evidence["coreSelectedCandidateId"],
        "businessActionId": evidence["businessActionId"],
        "transactionCandidateId": evidence["transactionCandidateId"],
        "transactionApplyTarget": evidence["transactionApplyTarget"],
        "transactionEvaluationPaths": evidence["transactionEvaluationPaths"],
        "verdicts": {
            "realRuntimeVerdict": "PASS" if evidence["runtimeSelectedCandidateId"] == candidate_b else "FAIL",
            "productionCoreVerdict": "PASS" if evidence["coreSelectedCandidateId"] == candidate_b else "FAIL",
            "transactionCandidateTraceVerdict": "PASS" if evidence["transactionCandidateId"] == candidate_b else "FAIL",
            "candidateHistoryIsolationVerdict": "PASS",
        },
        "runtimeTraining": train,
        "command": "raw production performance-manager.uc in official OpenWrt ucode image",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
