#!/usr/bin/env python3
"""Aggregate one exact build/evidence pair per native OpenWrt target."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def files(root: Path, name: str) -> list[Path]:
    return sorted((p for p in root.rglob(name) if p.is_file()), key=lambda p: str(p))


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
    parser.add_argument("--expected-arch", action="append", required=True)
    args = parser.parse_args(argv)

    root = Path(args.input).resolve()
    out = Path(args.out).resolve()
    metadata_files = files(root, "build-metadata.json")
    verification_files = files(root, "apk-verification.json")
    expected_count = len(args.expected_arch)
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
            if verification.get("arch") == metadata_arch:
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
        if arch != verification.get("arch") or arch not in args.expected_arch:
            raise RuntimeError(f"metadata/verification architecture mismatch: {arch!r}")
        pairs.append((metadata_path, verification_path, metadata, verification))

    arches = [metadata.get("architecture") for _, _, metadata, _ in pairs]
    if sorted(arches) != sorted(args.expected_arch):
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
                "sourceMetadata": str(metadata_path),
                "sourceVerification": str(verification_path),
            })
        package_matrix[name] = {"status": "ok", "targets": targets}

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
            "requiredPackageArchitectures": sorted(args.expected_arch),
            "qualifiedPackageArchitectures": sorted(arches),
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
