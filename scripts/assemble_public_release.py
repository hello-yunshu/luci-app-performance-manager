#!/usr/bin/env python3
"""Shared exact all-in-one APK assembly for prerelease and Stable releases."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"
ADAPTER_PACKAGE = "performance-manager-rill-adapter"


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


def read_matrix_reports(root: Path) -> list[tuple[Path, dict, Path, dict]]:
    metadata = _files(root, "build-metadata.json")
    verification = _files(root, "apk-verification.json")
    if not metadata or len(metadata) != len(verification):
        raise ArtifactIdentityError("matrix build metadata and APK verification counts disagree")
    pairs = []
    for metadata_path in metadata:
        candidates = [path for path in verification if path.parent == metadata_path.parent]
        if len(candidates) != 1:
            raise ArtifactIdentityError(f"cannot pair target evidence under {metadata_path.parent}")
        verification_path = candidates[0]
        build = json.loads(metadata_path.read_text())
        report = json.loads(verification_path.read_text())
        if build.get("verdict") != "PASS" or report.get("verdict") != "PASS":
            raise ArtifactIdentityError(f"target evidence is not PASS under {metadata_path.parent}")
        if build.get("repositoryCommitSha") != report.get("pmCommitSha"):
            raise ArtifactIdentityError(f"target evidence commit mismatch under {metadata_path.parent}")
        pairs.append((metadata_path, build, verification_path, report))
    return pairs


def assemble_public_apk(
    *,
    input_root: Path,
    output_root: Path,
    expected_commit: str,
    expected_filename: str | None = None,
) -> dict:
    """Resolve, verify, and stage exactly one public all-in-one APK."""
    pairs = read_matrix_reports(input_root)
    if any(build.get("repositoryCommitSha") != expected_commit for _, build, _, _ in pairs):
        raise ArtifactIdentityError("matrix build evidence is not for the expected commit")
    manifest_paths = _files(input_root, "all-in-one-release-manifest.json")
    manifests = [json.loads(path.read_text()) for path in manifest_paths]
    if any(manifest.get("pmCommitSha") != expected_commit or manifest.get("package") != PACKAGE
           for manifest in manifests):
        raise ArtifactIdentityError("all-in-one release manifest identity mismatch")
    verified_records = [(build, report, (report.get("packages") or {}).get(PACKAGE) or {})
                        for _, build, _, report in pairs]
    apk_sha_values = {record.get("sha256") for _, _, record in verified_records}
    apk_sha_values.update((build.get("packages") or {}).get(PACKAGE, {}).get("apkSha256")
                          for build, _, _ in verified_records)
    apk_sha_values.discard(None)
    if len(apk_sha_values) != 1:
        raise ArtifactIdentityError(f"all-in-one SHA identities disagree: {sorted(apk_sha_values)}")
    filename_values = {record.get("filename") for _, _, record in verified_records}
    filename_values.update((manifest.get("apk") or {}).get("filename") for manifest in manifests)
    filename_values.discard(None)
    filename = expected_filename or (next(iter(filename_values)) if len(filename_values) == 1 else None)
    if not filename:
        raise ArtifactIdentityError("all-in-one filename is missing or differs across targets")

    apk_sha = next(iter(apk_sha_values))
    identity = resolve_artifact(PACKAGE, apk_sha, [input_root], filename)
    source = Path(identity["canonicalPath"])
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / source.name
    shutil.copy2(source, target)
    adapter_identities = []
    for _, build, _, report in pairs:
        adapter_verified = (report.get("packages") or {}).get(ADAPTER_PACKAGE) or {}
        adapter_built = (build.get("packages") or {}).get(ADAPTER_PACKAGE) or {}
        adapter_filename = adapter_verified.get("filename") or adapter_built.get("apkFilename")
        adapter_sha = adapter_verified.get("sha256") or adapter_built.get("apkSha256")
        if adapter_verified.get("status") != "ok" or not adapter_filename or not adapter_sha:
            raise ArtifactIdentityError("target-specific adapter APK identity is incomplete")
        adapter_identity = resolve_artifact(ADAPTER_PACKAGE, adapter_sha, [input_root], adapter_filename)
        adapter_source = Path(adapter_identity["canonicalPath"])
        adapter_release_name = adapter_built.get("releaseFilename") or adapter_verified.get("releaseFilename")
        adapter_target = output_root / (adapter_release_name or adapter_source.name)
        if adapter_target.exists():
            raise ArtifactIdentityError(f"duplicate target adapter release name: {adapter_target.name}")
        shutil.copy2(adapter_source, adapter_target)
        adapter_identities.append({
            **adapter_identity,
            "canonicalPath": str(adapter_target),
            "filename": adapter_target.name,
            "sha256": sha256(adapter_target),
            "packageArch": build.get("architecture"),
            "target": build.get("target"),
            "openwrtVersion": build.get("openwrtVersion"),
        })
    # Keep one deterministic all-in-one manifest/checksum as a human-readable
    # convenience; matrix evidence remains target-specific in the input.
    dedicated_manifest = manifests[0] if manifests else None
    if dedicated_manifest:
        (output_root / "all-in-one-release-manifest.json").write_text(
            json.dumps(dedicated_manifest, ensure_ascii=False, indent=2) + "\n"
        )
    checksum_lines = [f"{sha256(target)}  {target.name}\n"]
    checksum_lines.extend(f"{item['sha256']}  {item['filename']}\n" for item in adapter_identities)
    (output_root / "all-in-one-checksums.txt").write_text("".join(checksum_lines))
    # Release consumers need one aggregate identity, not an arbitrary target's
    # report.  The per-target records retain the exact SDK/arch provenance.
    aggregate_packages = {}
    package_names = sorted({name for _, build, _, report in pairs
                            for name in set((build.get("packages") or {})) | set((report.get("packages") or {}))})
    for name in package_names:
        target_records = []
        for _, build, _, report in pairs:
            verified = (report.get("packages") or {}).get(name) or {}
            built = (build.get("packages") or {}).get(name) or {}
            target_records.append({"packageArch": build.get("architecture"), "target": build.get("target"),
                                   "openwrtVersion": build.get("openwrtVersion"),
                                   "packageManagerFormat": build.get("packageManagerFormat"),
                                   "apkFilename": built.get("apkFilename") or verified.get("filename"),
                                   "releaseFilename": built.get("releaseFilename") or verified.get("releaseFilename"),
                                   "apkSha256": built.get("apkSha256") or verified.get("sha256"),
                                   "status": verified.get("status")})
        aggregate_packages[name] = {"status": "ok", "targets": target_records}
    aggregate_metadata = {"schemaVersion": 2, "repositoryCommitSha": expected_commit,
                          "openwrtVersion": "multi-target", "architecture": "multi-target",
                          "target": "multi-target", "packageManagerFormat": "multi-format",
                          "targets": [{"openwrtVersion": build.get("openwrtVersion"), "target": build.get("target"),
                                       "packageArch": build.get("architecture"),
                                       "packageManagerFormat": build.get("packageManagerFormat"),
                                       "sdkIdentity": build.get("sdkIdentity"),
                                       "sdkArchiveSha256": build.get("sdkArchiveSha256")}
                                      for _, build, _, _ in pairs],
                          "packages": aggregate_packages, "verdicts": {"pmPackagesBuildVerdict": "PASS",
                          "apkExactVerificationVerdict": "PASS"}, "verdict": "PASS"}
    (output_root / "build-metadata.json").write_text(json.dumps(aggregate_metadata, indent=2) + "\n")
    (output_root / "apk-verification.json").write_text(json.dumps({
        "schemaVersion": 2, "pmCommitSha": expected_commit, "arch": "multi-target",
        "targets": [{"packageArch": report.get("arch"), "target": build.get("target"),
                      "report": report} for _, build, _, report in pairs],
        "packages": aggregate_packages, "verdict": "PASS", "failures": []
    }, indent=2) + "\n")
    consumed_paths = _files(input_root, "rill-consumed-manifest.json")
    if consumed_paths:
        consumed = json.loads(consumed_paths[0].read_text())
        consumed_by_parent = {path.parent: json.loads(path.read_text()) for path in consumed_paths}
        consumed["targets"] = [
            {"packageArch": build.get("architecture"), "target": build.get("target"),
             "openwrtVersion": build.get("openwrtVersion"),
             "artifactName": (consumed_by_parent.get(metadata_path.parent) or consumed).get("artifactName"),
             "rustTarget": (consumed_by_parent.get(metadata_path.parent) or consumed).get("rustTarget")}
            for metadata_path, build, _, _ in pairs
        ]
        (output_root / "rill-consumed-manifest.json").write_text(
            json.dumps(consumed, ensure_ascii=False, indent=2) + "\n"
        )
    result = {
        **identity,
        "canonicalPath": str(target),
        "filename": target.name,
        "sha256": sha256(target),
        "adapters": adapter_identities,
        "adapter": adapter_identities[0],
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
