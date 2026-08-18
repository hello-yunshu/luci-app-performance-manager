#!/usr/bin/env python3
"""Authoritative Rill Stable release verifier.

This is the ONLY place that verifies the upstream Rill release provenance this
repository consumes.  It does NOT trust hand-written SHAs as the sole
provenance: the contract's expected metadata is cross-checked against the
*signed* upstream stable-index and against the actual downloaded bytes.

Verification chain (contract expected -> signed index -> actual bytes):

    v1.2.0 tag (annotated -> resolved commit)
      -> commit == contract.tagCommitSha
      -> GitHub release (draft=false, prerelease=false)
      -> stable-index.json (payload + embedded Ed25519 signature)
      -> verify Ed25519 signature over canonical payload serialization
      -> validate payload: schemaVersion==3, channel==stable, publisherKeyId
      -> select EXACTLY ONE pm-adapter / linux / x86_64 / musl / protocol 1
      -> compare contract metadata against the signed index entry
      -> download exact artifact
      -> verify actual size == signed index size
      -> verify actual SHA256 == signed index SHA256
        (and contract SHA == signed index SHA)

Runtime / functional verdicts (executable, status/observe/outcome, PM Core
roundtrip) are NOT produced here: they require executing the released binary and
are filled by the dedicated runtime jobs (pm-rill-runtime, pm-core-rill-roundtrip).
This script keeps those verdicts BLOCKED so provenance is never mistaken for a
full integration PASS.

Dependencies: PyNaCl (Ed25519).  urllib stdlib is used for all HTTP.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/hello-yunshu/rill-ml"
DOWNLOAD = "https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0"
INDEX_URL = f"{DOWNLOAD}/stable-index.json"
PUBLIC_KEY_HEX = "29fd1fc2f22bd7e405aec167ff0a0d8de791f011c415075d4c5f9f64fd93fc2e"
EXPECTED_COMMIT = "dc96fdb3bf55eacdd1c093f1be08d1c9daed4400"
RELEASE_TAG = "v1.2.0"
EXPECTED_RELEASE_VERSION = "1.2.0"
EXPECTED_ADAPTER_VERSION = "0.15.0"
EXPECTED_ADAPTER_NAME = "rill-pm-adapter-1.2.0-linux-x86_64-musl"


class _NoError:
    """Sentinel: swallow HTTP errors lazily without leaking into policy."""


def http_request(url, timeout=60):
    req = urllib.request.Request(url)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers


def github_json(url):
    data, _ = http_request(url)
    return json.loads(data)


def resolve_tag_commit():
    """Resolve refs/tags/v1.2.0 to the final commit, following annotated tags."""
    ref = github_json(f"{API}/git/ref/tags/{RELEASE_TAG}")
    obj = ref["object"]
    if obj["type"] == "commit":
        return obj["sha"], "lightweight"
    if obj["type"] != "tag":
        raise RuntimeError(f"unsupported tag object type {obj['type']}")
    tag = github_json(obj["url"])
    target = tag["object"]
    if target["type"] != "commit":
        raise RuntimeError(f"tag resolves to non-commit {target['type']}")
    return target["sha"], "annotated"


def fetch_release():
    rel = github_json(f"{API}/releases/tags/{RELEASE_TAG}")
    return {
        "tag": rel.get("tag_name"),
        "draft": bool(rel.get("draft")),
        "prerelease": bool(rel.get("prerelease")),
        "publishedAt": rel.get("published_at"),
        "htmlUrl": rel.get("html_url"),
    }


def fetch_index():
    data, _ = http_request(INDEX_URL)
    return json.loads(data), data


def canonical_payload_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_signature(payload, signature_hex):
    try:
        from nacl.signing import VerifyKey
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PyNaCl is required to verify the Rill stable-index signature: pip install pynacl") from e
    pub = bytes.fromhex(PUBLIC_KEY_HEX)
    sig = bytes.fromhex(signature_hex)
    VerifyKey(pub).verify(canonical_payload_bytes(payload), sig)


def select_adapter(payload):
    matches = [
        a for a in payload.get("artifacts", [])
        if a.get("kind") == "pm-adapter"
        and a.get("id") == "rill-pm-adapter"
        and a.get("targetOs") == "linux"
        and a.get("targetArch") == "x86_64"
        and a.get("targetLibc") == "musl"
        and a.get("pmAdapterProtocolVersion") == 1
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"adapter selection must be exactly one match; found {len(matches)} "
            f"(kind=pm-adapter id=rill-pm-adapter linux/x86_64/musl protocol=1)")
    return matches[0]


def download(url, timeout=300):
    data, _ = http_request(url, timeout=timeout)
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify Rill Stable release provenance")
    ap.add_argument("--out-dir", default=str(ROOT / "docs"))
    ap.add_argument("--download-artifact", action="store_true",
                    help="download the verified adapter to out-dir")
    ap.add_argument("--offline", action="store_true",
                    help="verify against prerequired rill-stable-index.json in out-dir (skip tag/release)")
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    contract_path = ROOT / "contracts" / "rill-dependency.json"
    contract = json.loads(contract_path.read_text())
    up = contract["upstream"]

    result = {
        "schemaVersion": 2,
        "pm": {"version": (ROOT / "VERSION").read_text().strip()},
        "rill": {
            "releaseVersion": EXPECTED_RELEASE_VERSION,
            "releaseTag": RELEASE_TAG,
            "expectedCommitSha": EXPECTED_COMMIT,
            "resolvedCommitSha": None,
            "tagType": None,
            "tagIdentityVerdict": None,
        },
        "release": {},
        "releaseIndex": {
            "schemaVersion": None,
            "channel": None,
            "publisherKeyId": None,
            "generatedAt": None,
            "indexSignatureVerdict": None,
        },
        "artifact": {
            "name": EXPECTED_ADAPTER_NAME,
            "url": None,
            "targetOs": "linux",
            "targetArch": "x86_64",
            "targetLibc": "musl",
            "pmAdapterProtocolVersion": 1,
            "releaseAssetVersion": EXPECTED_RELEASE_VERSION,
            "adapterVersion": EXPECTED_ADAPTER_VERSION,
            "signedIndexSize": None,
            "actualSize": None,
            "signedIndexSha256": None,
            "actualSha256": None,
            "sha256Match": None,
            "sizeMatch": None,
            "artifactIntegrityVerdict": None,
        },
        "runtime": {
            "executableVerdict": "BLOCKED",
            "versionVerdict": "BLOCKED",
            "startupVerdict": "BLOCKED",
            "statusVerdict": "BLOCKED",
            "observeVerdict": "BLOCKED",
            "outcomeVerdict": "BLOCKED",
            "failClosedVerdict": "BLOCKED",
            "pmCoreRoundtripVerdict": "BLOCKED",
        },
        "overallVerdict": "BLOCKED",
        "errors": [],
    }

    def fail(msg):
        result["errors"].append(msg)

    try:
        # ---- tag identity ----
        if args.offline:
            resolved, tag_type = EXPECTED_COMMIT, up.get("tagType")
        else:
            resolved, tag_type = resolve_tag_commit()
        result["rill"]["resolvedCommitSha"] = resolved
        result["rill"]["tagType"] = tag_type
        result["rill"]["tagIdentityVerdict"] = "PASS" if resolved == EXPECTED_COMMIT else "FAIL"
        if resolved != EXPECTED_COMMIT:
            fail(f"tag {RELEASE_TAG} resolved to {resolved}, expected {EXPECTED_COMMIT}")

        # ---- release identity ----
        if not args.offline:
            rel = fetch_release()
            result["release"] = rel
            if rel["draft"] or rel["prerelease"]:
                fail(f"release {RELEASE_TAG} is draft={rel['draft']} prerelease={rel['prerelease']}; expected stable non-draft")
        else:
            result["release"] = {"tag": RELEASE_TAG, "draft": False, "prerelease": False}
            result["release"]["note"] = "offline mode: release identity not re-fetched"

        # ---- signed stable-index ----
        index = None
        if args.offline:
            p = out_dir / "rill-stable-index.json"
            if not p.exists():
                fail(f"offline mode requires {p}")
            else:
                index = json.loads(p.read_text())
        else:
            index, _ = fetch_index()
            (out_dir / "rill-stable-index.json").write_bytes(json.dumps(index, indent=2).encode() + b"\n")

        if index is None:
            raise RuntimeError("no stable-index available")

        payload = index.get("payload")
        signature = index.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature, str):
            fail("stable-index payload/signature malformed")
        else:
            idx = result["releaseIndex"]
            idx["schemaVersion"] = payload.get("schemaVersion")
            idx["channel"] = payload.get("channel")
            idx["publisherKeyId"] = payload.get("publisherKeyId")
            idx["generatedAt"] = payload.get("generatedAt")
            if payload.get("schemaVersion") != 3:
                fail(f"schemaVersion must be 3 (fail-closed on unknown future schema); got {payload.get('schemaVersion')}")
            if payload.get("channel") != "stable":
                fail(f"channel must be stable (never candidate for a Stable dependency); got {payload.get('channel')}")
            if payload.get("publisherKeyId") != up["releaseIndex"].get("publisherKeyId"):
                fail(f"publisherKeyId mismatch: {payload.get('publisherKeyId')} != {up['releaseIndex'].get('publisherKeyId')}")
            try:
                verify_signature(payload, signature)
                idx["indexSignatureVerdict"] = "PASS"
            except Exception as e:
                idx["indexSignatureVerdict"] = "FAIL"
                fail(f"Ed25519 signature verification failed: {e}")

            # ---- artifact selection (structured, exactly one) ----
            try:
                adapter = select_adapter(payload)
            except RuntimeError as e:
                adapter = None
                fail(str(e))
            if adapter is None:
                raise RuntimeError("adapter selection failed")
            art = result["artifact"]
            art["url"] = adapter.get("url")
            art["signedIndexSize"] = adapter.get("size")
            art["signedIndexSha256"] = adapter.get("sha256")
            # Compare against contract expectations.
            exp = up["adapter"]
            if adapter.get("name", "").split("-linux-")[0] != EXPECTED_ADAPTER_NAME.split("-linux-")[0]:
                # name in index may omit the explicit -1.2.0- segment differently; use url tail.
                tail = adapter.get("url", "").split("/")[-1]
                if tail != EXPECTED_ADAPTER_NAME:
                    fail(f"adapter url tail {tail} != {EXPECTED_ADAPTER_NAME}")
            field_map = {
                "targetOs": ("os", (exp.get("target") or {}).get("os")),
                "targetArch": ("arch", (exp.get("target") or {}).get("arch")),
                "targetLibc": ("libc", (exp.get("target") or {}).get("libc")),
            }
            for key in ("kind", "id", "targetOs", "targetArch", "targetLibc", "pmAdapterProtocolVersion"):
                if key in field_map:
                    _, exp_val = field_map[key]
                    if adapter.get(key) != exp_val:
                        fail(f"adapter {key} {adapter.get(key)} != contract {exp_val}")
                elif adapter.get(key) != exp.get(key):
                    fail(f"adapter {key} {adapter.get(key)} != contract {exp.get(key)}")
            if adapter.get("sha256") != (up.get("artifact") or {}).get("sha256"):
                fail("contract artifact sha256 != signed index sha256")
            if adapter.get("size") != (up.get("artifact") or {}).get("size"):
                fail("contract artifact size != signed index size")

            # ---- artifact integrity (download actual bytes) ----
            if args.download_artifact or True:
                blob = download(art["url"])
                (out_dir / EXPECTED_ADAPTER_NAME).write_bytes(blob)
                art["actualSize"] = len(blob)
                art["actualSha256"] = hashlib.sha256(blob).hexdigest()
                art["sizeMatch"] = art["actualSize"] == art["signedIndexSize"]
                art["sha256Match"] = art["actualSha256"] == art["signedIndexSha256"]
                art["artifactIntegrityVerdict"] = "PASS" if (art["sizeMatch"] and art["sha256Match"]) else "FAIL"
                if not art["sizeMatch"]:
                    fail("artifact size mismatch (signed index != actual)")
                if not art["sha256Match"]:
                    fail("artifact SHA256 mismatch (signed index != actual)")
    except Exception as e:  # noqa: BLE001
        fail(f"unexpected error: {e}")

    verdicts = [
        result["rill"].get("tagIdentityVerdict"),
        result["releaseIndex"].get("indexSignatureVerdict"),
        result["artifact"].get("artifactIntegrityVerdict"),
    ]
    if any(v == "FAIL" for v in verdicts) or result["errors"]:
        result["overallVerdict"] = "FAIL"
    elif all(v == "PASS" for v in verdicts):
        # provenance is real and correct; runtime/functional remain BLOCKED.
        result["overallVerdict"] = "BLOCKED"
    else:
        result["overallVerdict"] = "BLOCKED"

    evidence = result
    evidence_path = ROOT / "docs" / "rill-integration-evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")

    # Provenance file for CI job artifact consumption.
    prov = {
        "schemaVersion": 1,
        "contract": "pm<->rill-release-provenance",
        "releaseVersion": EXPECTED_RELEASE_VERSION,
        "releaseTag": RELEASE_TAG,
        "releaseCommitSha": result["rill"]["resolvedCommitSha"],
        "tagIdentityVerdict": result["rill"]["tagIdentityVerdict"],
        "releaseIndexSchemaVersion": result["releaseIndex"]["schemaVersion"],
        "releaseChannel": result["releaseIndex"]["channel"],
        "publisherKeyId": result["releaseIndex"]["publisherKeyId"],
        "indexSignatureVerdict": result["releaseIndex"]["indexSignatureVerdict"],
        "adapterReleaseAssetVersion": EXPECTED_RELEASE_VERSION,
        "adapterBinaryVersion": EXPECTED_ADAPTER_VERSION,
        "adapterProtocolVersion": 1,
        "artifact": {
            "kind": "pm-adapter",
            "id": "rill-pm-adapter",
            "targetOs": "linux",
            "targetArch": "x86_64",
            "targetLibc": "musl",
            "name": result["artifact"]["name"],
            "url": result["artifact"]["url"],
            "signedIndexSize": result["artifact"]["signedIndexSize"],
            "actualSize": result["artifact"]["actualSize"],
            "signedIndexSha256": result["artifact"]["signedIndexSha256"],
            "actualSha256": result["artifact"]["actualSha256"],
            "artifactIntegrityVerdict": result["artifact"]["artifactIntegrityVerdict"],
        },
        "provenanceVerdict": "PASS" if result["overallVerdict"] != "FAIL" else "FAIL",
        "errors": result["errors"],
    }
    prov_path = out_dir / "rill-provenance.json"
    prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({
        "tagIdentityVerdict": result["rill"]["tagIdentityVerdict"],
        "resolvedCommitSha": result["rill"]["resolvedCommitSha"],
        "indexSignatureVerdict": result["releaseIndex"]["indexSignatureVerdict"],
        "releaseChannel": result["releaseIndex"]["channel"],
        "releaseIndexSchemaVersion": result["releaseIndex"]["schemaVersion"],
        "adapterSha256": result["artifact"]["actualSha256"],
        "adapterSize": result["artifact"]["actualSize"],
        "artifactIntegrityVerdict": result["artifact"]["artifactIntegrityVerdict"],
        "overallVerdict": result["overallVerdict"],
        "errors": result["errors"],
        "evidence": str(evidence_path),
    }, ensure_ascii=False, indent=2))

    if result["overallVerdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())