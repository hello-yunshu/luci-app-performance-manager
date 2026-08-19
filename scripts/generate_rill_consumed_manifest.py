#!/usr/bin/env python3
"""Single, unified generator of the PM<->Rill consumed-release manifest.

Both CI workflows (ci.yml and build-openwrt.yml) MUST call this one script so
the two workflows can never drift into generating different manifest shapes
(previously ci.yml emitted a newer schema while build-openwrt.yml still emitted
the old `consumedVersion`/`protocolApi`/`minimumRillVersion` shape).

The manifest is contract-driven: every Rill value comes from
contracts/rill-dependency.json (the unique immutable-release source of truth),
never from hardcoded copies.  It records the PM commit that produced it so the
final evidence aggregator can enforce a same-commit evidence chain.

Schema v2 (see rc.7 prompt section 30):
  schemaVersion, contract, releaseVersion, releaseTag, releaseCommitSha,
  releaseIndexSchemaVersion, releaseChannel, adapterReleaseAssetVersion,
  adapterVersion, protocolContract, protocolVersion, artifactName,
  artifactSha256, artifactSize  -- plus pm/source context.

Exit code: 0 on success (even when the upstream is provisioned); the manifest
records `status`/`provisioned` so consumers fail closed on a blocked upstream.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 2
CONTRACT_NAME = "pm<->rill-consumed-release"


def env(key, default=None):
    return os.environ.get(key) or default


def pm_commit() -> str:
    sha = env("GITHUB_SHA")
    if sha:
        return sha
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def load_contract() -> dict:
    p = ROOT / "contracts" / "rill-dependency.json"
    if not p.exists():
        raise SystemExit(f"FATAL: contract {p} missing")
    return json.loads(p.read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the unified PM<->Rill consumed-release manifest")
    ap.add_argument("--out", default=str(ROOT / "rill-consumed-manifest.json"))
    args = ap.parse_args(argv)

    dep = load_contract()
    proto = dep.get("protocol") or {}
    up = dep.get("upstream") or {}
    idx = up.get("releaseIndex") or {}
    art = up.get("artifact") or {}
    adv = up.get("adapter") or {}
    tgt = adv.get("target") or {}
    caps = dep.get("capabilities") or {}

    release = up.get("releaseVersion")
    tag = up.get("releaseTag")
    commit = up.get("tagCommitSha")
    adapter_version = adv.get("adapterVersion")
    artifact_name = art.get("name") or adv.get("name")
    artifact_sha = art.get("sha256") or adv.get("sha256")
    artifact_size = art.get("size") or adv.get("size")

    # The contract itself is the unique source of truth; a malformed contract
    # must fail the build, not silently emit a hollow manifest.
    required_up = ("releaseVersion", "releaseTag", "tagCommitSha", "repository")
    missing = [k for k in required_up if not up.get(k)]
    if missing:
        raise SystemExit(f"FATAL: contract upstream missing {missing}")
    if not artifact_sha or not artifact_name:
        raise SystemExit("FATAL: contract upstream artifact name/sha256 missing (unpinned)")

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "contract": CONTRACT_NAME,
        "releaseVersion": release,
        "releaseTag": tag,
        "releaseCommitSha": commit,
        "releaseIndexSchemaVersion": idx.get("schemaVersion"),
        "releaseChannel": idx.get("channel"),
        "adapterReleaseAssetVersion": adv.get("releaseAssetVersion") or release,
        "adapterVersion": adapter_version,
        "protocolContract": proto.get("contract"),
        "protocolVersion": proto.get("protocolVersion"),
        "artifactName": artifact_name,
        "artifactSha256": artifact_sha,
        "artifactSize": artifact_size,
        "upstreamRepository": up.get("repository"),
        "adapterArtifactId": adv.get("id"),
        "adapterTargetOs": tgt.get("os"),
        "adapterTargetArch": tgt.get("arch"),
        "adapterTargetLibc": tgt.get("libc"),
        "requiredCapabilities": caps.get("required"),
        "status": up.get("status", "external-dependency-blocked"),
        "blockedReason": up.get("blockedReason"),
        "provisioned": bool(up.get("releaseVersion") and artifact_sha and up.get("tagCommitSha")),
        "pm": {
            "version": (ROOT / "VERSION").read_text().strip(),
            "commitSha": pm_commit(),
        },
        "generatedBy": str(Path(__file__).name),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workflow": env("GITHUB_WORKFLOW"),
        "workflowRunId": env("GITHUB_RUN_ID"),
        "note": ("PM never compiles Rill; this manifest records the immutable upstream release PM consumes. "
                 "The Rill release bundle version, the rill-pm-adapter crate/binary version and the pm-rill-shadow "
                 "protocol version are deliberately kept distinct and reported separately."),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "schemaVersion": manifest["schemaVersion"],
        "contract": manifest["contract"],
        "releaseVersion": release,
        "protocolContract": proto.get("contract"),
        "protocolVersion": proto.get("protocolVersion"),
        "artifactSha256": artifact_sha,
        "status": manifest["status"],
        "pmCommitSha": manifest["pm"]["commitSha"],
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
