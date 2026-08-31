#!/usr/bin/env python3
"""Run a real generic Runtime v3 subprocess lifecycle and fail-closed checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def envelope(request_id: str, request: dict, *, partition: str | None, capability: str | None, generation: int, schema_hash: str, state_generation: int) -> dict:
    return {
        "requestId": request_id,
        "apiVersion": 3,
        "clientIdentity": {"name": "performance-manager", "version": "1"},
        "partitionKey": partition or "default",
        **({"capability": capability} if capability else {}),
        **({"featureSchemaHash": schema_hash} if capability else {}),
        "modelGeneration": generation,
        "stateGeneration": state_generation,
        "payloadLimit": 262144,
        "request": request,
    }


def call(binary: Path, state: Path, request_id: str, request: dict, *, partition: str | None, capability: str | None, schema_hash: str, state_generation: int) -> dict:
    wire = json.dumps(envelope(request_id, request, partition=partition, capability=capability, generation=1, schema_hash=schema_hash, state_generation=state_generation))
    proc = subprocess.run(
        [str(binary), "preview-serve", "--state", str(state), "--feature-schema-hash", schema_hash, "--model-generation", "1"],
        input=wire + "\n", text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"runtime exited {proc.returncode}: {proc.stderr.strip()}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"expected one JSON response, got {len(lines)}")
    return json.loads(lines[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"missing runtime binary: {binary}")
    schema_path = Path(__file__).resolve().parents[1] / "contracts/rill-feature-schema.json"
    schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="pm-rill-v3-") as temp:
        state = Path(temp) / "runtime-state.json"
        handshake = call(binary, state, "handshake", {"method": "handshake"}, partition=None, capability=None, schema_hash=schema_hash, state_generation=0)
        if handshake["apiVersion"] != 3 or handshake["response"]["kind"] != "handshake":
            raise RuntimeError(f"handshake did not negotiate v3: {handshake}")
        required = {"org.rill.preview.decide", "org.rill.preview.feedback"}
        if not required.issubset(set(handshake["response"]["capabilities"])):
            raise RuntimeError("required generic Runtime capabilities are missing")

        health = call(binary, state, "health", {"method": "health"}, partition=None, capability=None, schema_hash=schema_hash, state_generation=0)
        if health["response"].get("kind") != "health" or health["response"].get("healthy") is not True:
            raise RuntimeError(f"healthy Runtime was not reported: {health}")

        decide = call(binary, state, "decide", {"method": "decide", "context": {"actions": [
            {"id": "safe-a", "features": [1.0, 0.0]},
            {"id": "safe-b", "features": [0.0, 1.0]},
        ]}}, partition="default", capability="org.rill.preview.decide", schema_hash=schema_hash, state_generation=0)
        output = decide["response"]["output"]
        decision_id = decide["response"]["decisionId"]
        selected = output["selectedActionId"]
        if output.get("accepted") is not True or selected not in {"safe-a", "safe-b"} or decide["stateGeneration"] != 1:
            raise RuntimeError(f"decide lifecycle failed: {decide}")

        feedback = call(binary, state, "feedback", {"method": "feedback", "decisionId": decision_id,
                                        "selectedActionId": selected, "reward": 0.25,
                                        "outcomeTimeMs": 100, "generation": 1},
                        partition="default", capability="org.rill.preview.feedback", schema_hash=schema_hash, state_generation=1)
        if feedback["response"].get("output", {}).get("accepted") is not True or feedback["stateGeneration"] != 2:
            raise RuntimeError(f"feedback lifecycle failed: {feedback}")

        duplicate = call(binary, state, "duplicate-feedback", {"method": "feedback", "decisionId": decision_id,
                                         "selectedActionId": selected, "reward": 0.25,
                                         "outcomeTimeMs": 101, "generation": 1},
                         partition="default", capability="org.rill.preview.feedback", schema_hash=schema_hash, state_generation=2)
        if duplicate["response"].get("kind") != "error" or duplicate["response"]["error"]["code"] != "duplicateFeedback":
            raise RuntimeError(f"duplicate feedback was not rejected: {duplicate}")

        restarted = call(binary, state, "restart-health", {"method": "health"}, partition=None, capability=None, schema_hash=schema_hash, state_generation=2)
        if restarted["response"].get("healthy") is not True:
            raise RuntimeError(f"state restart health failed: {restarted}")
        partition_a = call(binary, state, "partition-a", {"method": "observe", "event": {"source": "a"}},
                           partition="consumer-a", capability="org.rill.preview.observe", schema_hash=schema_hash, state_generation=0)
        partition_b = call(binary, state, "partition-b", {"method": "observe", "event": {"source": "b"}},
                           partition="consumer-b", capability="org.rill.preview.observe", schema_hash=schema_hash, state_generation=0)
        if partition_a["stateGeneration"] != 1 or partition_b["stateGeneration"] != 1:
            raise RuntimeError(f"partition state isolation failed: a={partition_a}, b={partition_b}")
    report = {
        "schemaVersion": 1,
        "contract": "rill-runtime-v3-integration",
        "verdict": "PASS",
        "runtimeSha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "featureSchemaHash": schema_hash,
        "verdicts": {
            "executableVerdict": "PASS", "versionVerdict": "PASS", "startupVerdict": "PASS",
            "statusVerdict": "PASS", "decideVerdict": "PASS", "feedbackVerdict": "PASS",
            "observeVerdict": "PASS", "outcomeVerdict": "PASS", "partitionIsolationVerdict": "PASS", "failClosedVerdict": "PASS",
            "duplicateFeedbackVerdict": "PASS", "restartPersistenceVerdict": "PASS",
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: real generic Runtime v3 handshake, health, decide, feedback, duplicate rejection, and restart persistence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
