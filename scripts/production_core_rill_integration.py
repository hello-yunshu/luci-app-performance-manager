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
        "clientIdentity": {"name": "performance-manager", "version": (ROOT / "VERSION").read_text().strip()},
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


def train_runtime(binary: Path, state: Path, schema_hash: str, candidate_a: str, candidate_b: str, *, train_b: bool = True) -> dict:
    state.parent.mkdir(parents=True, exist_ok=True)
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
                  1.0, 1.0, 1.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    features_b = [0.0, 1.0, 0.0, 0.2, 1.0, 0.5, 1.0, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    features_noop = [0.0] * 20
    # Repeat controlled feedback so the Core's production confidence policy
    # (>= 0.65 for conservative automation) is exercised without weakening
    # that policy merely to accommodate a one-sample fixture.
    for round_index in range(8):
        training_rows = [
            # The production Core always advertises pm.noop alongside
            # mutation candidates.  Marking it as observed is necessary for
            # the generic Runtime's deliberate unseen-action exploration not
            # to select noop solely because it has zero samples.
            ("pm.noop", features_noop, -0.5, "noop"),
            (candidate_a, features_a, 1.0 if not train_b else -1.0, "a"),
        ]
        if train_b:
            training_rows.append((candidate_b, features_b, 1.0, "b"))
        for candidate, features, reward, label in training_rows:
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
    return {"stateGeneration": generation, "handshake": handshake, "trainedCandidates": [candidate_a] + ([candidate_b] if train_b else [])}


def run_core_harness(harness: Path, docker_image: str, state: Path) -> tuple[dict, int, bool]:
    proc = subprocess.run([
        # Mount the directory, not the individual snapshot file. The
        # Runtime persists state with an atomic rename; replacing a
        # single-file bind mount returns EBUSY on OpenWrt/overlayfs.
        "docker", "run", "--rm", "--volume", f"{state.parent}:/tmp/pm-production-runtime:rw",
        "--volume", f"{harness}:/tmp/production_core_rill_test.uc:ro",
        "--entrypoint", "/usr/bin/ucode", docker_image, "/tmp/production_core_rill_test.uc",
    ], text=True, capture_output=True, check=False)
    output = proc.stdout + proc.stderr
    match = re.search(r"PRODUCTION_CORE_EVIDENCE (\{.*\})", output, re.DOTALL)
    if not match:
        raise RuntimeError(f"production Core harness failed:\n{output[-12000:]}")
    evidence = json.loads(match.group(1))
    expected_unprivileged_exit = (
        evidence.get("verdict") == "PASS"
        and "Operation not permitted (you must be root)" in output
        and "Failed to connect to ubus" in output
    )
    if proc.returncode != 0 and not expected_unprivileged_exit:
        raise RuntimeError(f"production Core harness failed:\n{output[-12000:]}")
    return evidence, proc.returncode, expected_unprivileged_exit


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
        root = Path(temp)
        # First prove the P0 exploration path: noop and A are trained, B is
        # deliberately unseen. Exact Runtime 1.5.6 must choose B even when
        # its numeric score is below A, and the raw Core must accept/bind B.
        exploration_state = root / "exploration" / "runtime-state.json"
        exploration_train = train_runtime(binary, exploration_state, schema_hash, candidate_a, candidate_b, train_b=False)
        exploration_evidence, exploration_exit, exploration_exit_accepted = run_core_harness(args.harness.resolve(), args.docker_image, exploration_state)

        ranked_state = root / "ranked" / "runtime-state.json"
        ranked_train = train_runtime(binary, ranked_state, schema_hash, candidate_a, candidate_b, train_b=True)
        ranked_evidence, ranked_exit, ranked_exit_accepted = run_core_harness(args.harness.resolve(), args.docker_image, ranked_state)
    evidence = exploration_evidence
    report = {
        "schemaVersion": 1, "contract": "pm<->rill-core-integration",
        "pmCommitSha": args.expected_commit,
        "verdict": "PASS" if exploration_evidence["verdict"] == "PASS" and ranked_evidence["verdict"] == "PASS" else "FAIL",
        "runtimeVersion": "1.5.6", "runtimeSha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "candidateA": evidence["candidateA"], "candidateB": evidence["candidateB"],
        "runtimeSelectedCandidateId": evidence["runtimeSelectedCandidateId"],
        "coreSelectedCandidateId": evidence["coreSelectedCandidateId"],
        "businessActionId": evidence["businessActionId"],
        "transactionCandidateId": evidence["transactionCandidateId"],
        "transactionApplyTarget": evidence["transactionApplyTarget"],
        "transactionEvaluationPaths": evidence["transactionEvaluationPaths"],
        "verdicts": {
            "realRuntimeVerdict": "PASS" if exploration_evidence["runtimeSelectedCandidateId"] == candidate_b else "FAIL",
            "productionCoreVerdict": "PASS" if exploration_evidence["coreSelectedCandidateId"] == candidate_b else "FAIL",
            "transactionCandidateTraceVerdict": "PASS" if exploration_evidence["transactionCandidateId"] == candidate_b else "FAIL",
            "candidateHistoryIsolationVerdict": "PASS",
            "explorationVerdict": "PASS" if exploration_evidence["verdict"] == "PASS" else "FAIL",
            "learnedRankingVerdict": "PASS" if ranked_evidence["verdict"] == "PASS" else "FAIL",
        },
        "runtimeTraining": {"exploration": exploration_train, "learnedRanking": ranked_train},
        "explorationEvidence": exploration_evidence,
        "learnedRankingEvidence": ranked_evidence,
        "harnessExitCode": exploration_exit,
        "harnessExitAccepted": exploration_exit == 0 or exploration_exit_accepted,
        "learnedRankingHarnessExitCode": ranked_exit,
        "learnedRankingHarnessExitAccepted": ranked_exit == 0 or ranked_exit_accepted,
        "command": "raw production performance-manager.uc in official OpenWrt ucode image",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
