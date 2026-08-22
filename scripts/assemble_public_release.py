#!/usr/bin/env python3
"""Shared exact all-in-one APK assembly for prerelease and Stable releases."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"


def _files(root: Path, name: str) -> list[Path]:
    return sorted((path for path in root.rglob(name) if path.is_file()), key=lambda path: str(path))


def read_one_json(root: Path, name: str, *, required: bool = True) -> tuple[Path | None, dict | None]:
    matches = _files(root, name)
    if not matches:
        if required:
            raise ArtifactIdentityError(f"missing {name} under {root}")
        return None, None
    values = [(path, json.loads(path.read_text())) for path in matches]
    first = json.dumps(values[0][1], sort_keys=True, separators=(",", ":"))
    if any(json.dumps(value, sort_keys=True, separators=(",", ":")) != first for _, value in values[1:]):
        raise ArtifactIdentityError(f"conflicting copies of {name}: {[str(path) for path, _ in values]}")
    return values[0]


def assemble_public_apk(
    *,
    input_root: Path,
    output_root: Path,
    expected_commit: str,
    expected_filename: str | None = None,
) -> dict:
    """Resolve, verify, and stage exactly one public all-in-one APK."""
    _, manifest = read_one_json(input_root, "all-in-one-release-manifest.json", required=False)
    _, verification = read_one_json(input_root, "apk-verification.json")
    _, metadata = read_one_json(input_root, "build-metadata.json")
    if verification.get("verdict") != "PASS" or verification.get("pmCommitSha") != expected_commit:
        raise ArtifactIdentityError("APK verification is not a PASS for the expected commit")
    if metadata.get("verdict") != "PASS" or metadata.get("repositoryCommitSha") != expected_commit:
        raise ArtifactIdentityError("build metadata is not a PASS for the expected commit")

    verified = (verification.get("packages") or {}).get(PACKAGE) or {}
    built = (metadata.get("packages") or {}).get(PACKAGE) or {}
    expected_sha_values = {
        verified.get("sha256"),
        built.get("apkSha256"),
        (manifest or {}).get("apk", {}).get("sha256"),
    }
    if None in expected_sha_values or len(expected_sha_values) != 1:
        raise ArtifactIdentityError(f"all-in-one SHA identities disagree: {sorted(str(value) for value in expected_sha_values)}")
    filename = expected_filename or verified.get("filename") or built.get("apkFilename") or built.get("filename")
    if manifest:
        if manifest.get("pmCommitSha") != expected_commit or manifest.get("package") != PACKAGE:
            raise ArtifactIdentityError("all-in-one release manifest identity mismatch")
        filename = filename or (manifest.get("apk") or {}).get("filename")
    if not filename:
        raise ArtifactIdentityError("all-in-one filename is missing from authoritative metadata")

    apk_sha = next(iter(expected_sha_values))
    identity = resolve_artifact(PACKAGE, apk_sha, [input_root], filename)
    source = Path(identity["canonicalPath"])
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / source.name
    shutil.copy2(source, target)
    for name in ("all-in-one-release-manifest.json", "all-in-one-checksums.txt",
                 "build-metadata.json", "apk-verification.json", "rill-consumed-manifest.json"):
        source_path = _files(input_root, name)
        if not source_path:
            if name == "rill-consumed-manifest.json":
                continue
            raise ArtifactIdentityError(f"missing {name} under {input_root}")
        if name.endswith(".json"):
            read_one_json(input_root, name)
        shutil.copy2(source_path[0], output_root / name)
    result = {
        **identity,
        "canonicalPath": str(target),
        "filename": target.name,
        "sha256": sha256(target),
    }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-filename")
    args = parser.parse_args(argv)
    result = assemble_public_apk(
        input_root=Path(args.input).resolve(),
        output_root=Path(args.out).resolve(),
        expected_commit=args.expected_commit,
        expected_filename=args.expected_filename,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
