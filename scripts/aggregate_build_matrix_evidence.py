#!/usr/bin/env python3
"""Aggregate one exact build/evidence pair per native OpenWrt target."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM_TARGETS = json.loads((ROOT / "contracts/openwrt-native-targets.json").read_text())["targets"]


def files(root: Path, name: str, path_fragments: list[str]) -> list[Path]:
    candidates = (p for p in root.rglob(name) if p.is_file())
    if path_fragments:
        candidates = (p for p in candidates
                      if any(fragment in str(p) for fragment in path_fragments))
    return sorted(candidates, key=lambda p: str(p))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-arch", action="append", default=[])
    parser.add_argument("--expected-target", action="append", default=[],
                        help="exact release:package-arch:package-format target identity")
    parser.add_argument("--include-path-fragment", action="append", default=[])
    args = parser.parse_args(argv)

    root = Path(args.input).resolve()
    out = Path(args.out).resolve()
    metadata_files = files(root, "build-metadata.json", args.include_path_fragment)
    verification_files = files(root, "apk-verification.json", args.include_path_fragment)
    if not args.expected_arch and not args.expected_target:
        raise RuntimeError("expected target identities are required")
    expected_count = len(args.expected_target) or len(args.expected_arch)
    target_map = {
        f"{row['openwrtVersion']}:{row['packageArch']}:{row['packageManagerFormat']}": row
        for row in PM_TARGETS
    }
    if args.expected_target and set(args.expected_target) != set(target_map):
        raise RuntimeError("requested target coverage differs from the checked-in PM target policy")
    if len(metadata_files) != expected_count or len(verification_files) != expected_count:
        raise RuntimeError(
            f"expected {expected_count} target metadata and verification files, "
            f"found {len(metadata_files)} and {len(verification_files)}"
        )

    pairs = []
    for metadata_path in metadata_files:
        metadata = json.loads(metadata_path.read_text())
        metadata_arch = metadata.get("architecture")
        candidates = []
        for verification_path in verification_files:
            verification = json.loads(verification_path.read_text())
            if args.expected_target:
                exact_target_match = (
                    verification.get("openwrtVersion") == metadata.get("openwrtVersion")
                    and verification.get("pkgtype") == metadata.get("packageManagerFormat")
                )
            else:
                exact_target_match = (
                    (not verification.get("openwrtVersion") or verification.get("openwrtVersion") == metadata.get("openwrtVersion"))
                    and (not verification.get("pkgtype") or verification.get("pkgtype") == metadata.get("packageManagerFormat"))
                )
            if verification.get("arch") == metadata_arch and exact_target_match:
                candidates.append((verification_path, verification))
        if len(candidates) != 1:
            raise RuntimeError(
                f"cannot pair {metadata_path} with one target verification report "
                f"for architecture {metadata_arch!r}"
            )
        verification_path, verification = candidates[0]
        if metadata.get("repositoryCommitSha") != args.expected_commit or \
                verification.get("pmCommitSha") != args.expected_commit:
            raise RuntimeError(f"same-commit evidence mismatch under {metadata_path.parent}")
        if metadata.get("verdict") != "PASS" or verification.get("verdict") != "PASS":
            raise RuntimeError(f"target evidence is not PASS under {metadata_path.parent}")
        arch = metadata.get("architecture")
        target_id = f"{metadata.get('openwrtVersion')}:{arch}:{metadata.get('packageManagerFormat')}"
        if arch != verification.get("arch") or (args.expected_arch and arch not in args.expected_arch) or \
                (args.expected_target and target_id not in args.expected_target):
            raise RuntimeError(f"metadata/verification architecture mismatch: {arch!r}")
        if args.expected_target:
            target_spec = target_map[target_id]
            expected_sdk_prefix = f"openwrt-sdk-{target_spec['openwrtVersion']}-{target_spec['sdkPrefix']}_"
            if metadata.get("target") != target_spec["target"]:
                raise RuntimeError(f"SDK target identity mismatch for {target_id}: {metadata.get('target')!r}")
            if not str(metadata.get("sdkIdentity", "")).startswith(expected_sdk_prefix):
                raise RuntimeError(f"SDK archive identity mismatch for {target_id}: {metadata.get('sdkIdentity')!r}")
            if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("sdkArchiveSha256", ""))):
                raise RuntimeError(f"SDK archive checksum missing for {target_id}")
        pairs.append((metadata_path, verification_path, metadata, verification))

    arches = [metadata.get("architecture") for _, _, metadata, _ in pairs]
    target_ids = [f"{meta.get('openwrtVersion')}:{meta.get('architecture')}:{meta.get('packageManagerFormat')}"
                  for _, _, meta, _ in pairs]
    if args.expected_target:
        if sorted(target_ids) != sorted(args.expected_target):
            raise RuntimeError(f"exact target coverage mismatch: {target_ids!r}")
    elif sorted(arches) != sorted(args.expected_arch):
        raise RuntimeError(f"target architecture coverage mismatch: {arches!r}")

    package_names = sorted({
        name for _, _, _, verification in pairs
        for name in (verification.get("packages") or {})
    })
    package_matrix = {}
    for name in package_names:
        targets = []
        for metadata_path, verification_path, metadata, verification in pairs:
            verified = (verification.get("packages") or {}).get(name) or {}
            built = (metadata.get("packages") or {}).get(name) or {}
            if verified.get("status") != "ok" or built.get("status") != "ok":
                raise RuntimeError(f"{name} is not verified for {metadata.get('architecture')}")
            if verified.get("sha256") != built.get("apkSha256"):
                raise RuntimeError(f"{name} SHA mismatch for {metadata.get('architecture')}")
            targets.append({
                "openwrtVersion": metadata.get("openwrtVersion"),
                "target": metadata.get("target"),
                "packageArch": verified.get("arch") or built.get("arch") or metadata.get("architecture"),
                "rustTarget": metadata.get("rustTarget"),
                "packageManagerFormat": metadata.get("packageManagerFormat"),
                "sdkIdentity": metadata.get("sdkIdentity"),
                "sdkArchiveSha256": metadata.get("sdkArchiveSha256"),
                "apkFilename": built.get("apkFilename") or verified.get("filename"),
                "releaseFilename": built.get("releaseFilename") or verified.get("releaseFilename"),
                "apkSha256": built.get("apkSha256") or verified.get("sha256"),
                "pkgver": verified.get("pkgver"),
                "arch": verified.get("arch"),
                "runtimeBinary": verified.get("runtimeBinary"),
                "installedPayload": verified.get("installedPayload", {}),
                "sourceMetadata": str(metadata_path),
                "sourceVerification": str(verification_path),
            })
        package_matrix[name] = {"status": "ok", "targets": targets}
        if name == "luci-app-performance-manager-all":
            package_matrix[name]["runtimeBundled"] = False
            package_matrix[name]["runtimeSharedDependency"] = True

    first = pairs[0][2]
    target_records = [{
        "openwrtVersion": metadata.get("openwrtVersion"),
        "target": metadata.get("target"),
        "packageArch": metadata.get("architecture"),
        "rustTarget": metadata.get("rustTarget"),
        "packageManagerFormat": metadata.get("packageManagerFormat"),
        "sdkIdentity": metadata.get("sdkIdentity"),
        "sdkArchiveSha256": metadata.get("sdkArchiveSha256"),
        "feedsCommits": metadata.get("feedsCommits", {}),
        "metadataSha256": sha256(metadata_path),
        "verificationSha256": sha256(verification_path),
    } for metadata_path, verification_path, metadata, _ in pairs]

    combined_metadata = {
        "schemaVersion": 2,
        "repository": first.get("repository"),
        "repositoryCommitSha": args.expected_commit,
        "openwrtVersion": "multi-target",
        "architecture": "multi-target",
        "target": "multi-target",
        "packageManagerFormat": "multi-format",
        "externalRuntime": first.get("externalRuntime", {}),
        "targets": target_records,
        "packages": package_matrix,
        "expectedApkPackages": first.get("expectedApkPackages", []),
        "producedApkPackages": package_names,
        "verdicts": {"pmPackagesBuildVerdict": "PASS", "apkExactVerificationVerdict": "PASS"},
        "verdict": "PASS",
        "matrixCoverage": {
            "requiredTargets": sorted(args.expected_target) if args.expected_target else sorted(args.expected_arch),
            "qualifiedTargets": sorted(target_ids if args.expected_target else arches),
            "targetCount": len(target_records),
        },
    }
    combined_verification = {
        "schemaVersion": 2,
        "contract": "apk-exact-verification-matrix",
        "pmCommitSha": args.expected_commit,
        "expectedVersion": next((v.get("expectedVersion") for _, _, _, v in pairs
                                  if v.get("expectedVersion")), None),
        "arch": "multi-target",
        "targets": [{
            "packageArch": verification.get("arch"),
            "target": metadata.get("target"),
            "openwrtVersion": metadata.get("openwrtVersion"),
            "packageManagerFormat": metadata.get("packageManagerFormat"),
            "report": verification,
        } for _, _, metadata, verification in pairs],
        "packages": package_matrix,
        "verdict": "PASS",
        "failures": [],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build-metadata.json").write_text(json.dumps(combined_metadata, indent=2) + "\n")
    (out / "apk-verification.json").write_text(json.dumps(combined_verification, indent=2) + "\n")
    print(json.dumps({"verdict": "PASS", "targets": target_records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
