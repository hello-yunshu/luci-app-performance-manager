#!/usr/bin/env python3
"""Shared exact all-in-one APK assembly for prerelease and Stable releases."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"
INTEGRATION_PACKAGE = "performance-manager-rill"
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


def resolve_package_identity(
    *, input_root: Path, pairs: list[tuple[Path, dict, Path, dict]], package: str,
    expected_arch: str | None = None,
) -> tuple[dict, list[dict]]:
    """Resolve one package identity across all target build copies.

    Architecture-independent packages are built in every SDK only as a
    verification convenience.  The public inventory owns one canonical copy;
    every target copy must have the same package filename, metadata identity,
    and SHA-256 before one can be selected.
    """
    records = []
    for _, build, _, report in pairs:
        verified = (report.get("packages") or {}).get(package) or {}
        built = (build.get("packages") or {}).get(package) or {}
        if verified.get("status") != "ok" or built.get("status") != "ok":
            raise ArtifactIdentityError(f"{package} is not verified for {build.get('architecture')}")
        filename = built.get("apkFilename") or verified.get("filename")
        digest = built.get("apkSha256") or verified.get("sha256")
        package_arch = verified.get("arch")
        if not filename or not digest or package_arch not in ("all", "noarch"):
            raise ArtifactIdentityError(f"{package} lacks an exact architecture-independent identity")
        if expected_arch and package_arch not in (expected_arch, "noarch"):
            raise ArtifactIdentityError(f"{package} metadata arch {package_arch!r} != {expected_arch!r}")
        if verified.get("sha256") != built.get("apkSha256"):
            raise ArtifactIdentityError(f"{package} SHA mismatch for {build.get('architecture')}")
        records.append({
            "packageArch": package_arch,
            "filename": filename,
            "sha256": digest,
            "target": build.get("target"),
            "openwrtVersion": build.get("openwrtVersion"),
        })
    filenames = {record["filename"] for record in records}
    digests = {record["sha256"] for record in records}
    if len(filenames) != 1 or len(digests) != 1:
        raise ArtifactIdentityError(
            f"{package} copies disagree across targets: filenames={sorted(filenames)}, "
            f"sha256={sorted(digests)}"
        )
    identity = resolve_artifact(package, next(iter(digests)), [input_root], next(iter(filenames)))
    return identity, records


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
    if not manifests:
        raise ArtifactIdentityError("missing all-in-one release manifests")
    if any(manifest.get("pmCommitSha") != expected_commit or manifest.get("package") != PACKAGE
           for manifest in manifests):
        raise ArtifactIdentityError("all-in-one release manifest identity mismatch")
    primary_identity, primary_records = resolve_package_identity(
        input_root=input_root, pairs=pairs, package=PACKAGE, expected_arch="all"
    )
    integration_identity, integration_records = resolve_package_identity(
        input_root=input_root, pairs=pairs, package=INTEGRATION_PACKAGE, expected_arch="all"
    )
    for manifest in manifests:
        apk = manifest.get("apk") or {}
        if apk.get("filename") != primary_records[0]["filename"] or apk.get("sha256") != primary_records[0]["sha256"]:
            raise ArtifactIdentityError("all-in-one manifest disagrees with verified package identity")
    filename = expected_filename or primary_records[0]["filename"]
    if filename != primary_records[0]["filename"]:
        raise ArtifactIdentityError("requested all-in-one filename differs from verified identity")
    source = Path(primary_identity["canonicalPath"])
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / source.name
    shutil.copy2(source, target)
    integration_source = Path(integration_identity["canonicalPath"])
    integration_target = output_root / integration_source.name
    shutil.copy2(integration_source, integration_target)
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
            "rustTarget": build.get("rustTarget"),
            "target": build.get("target"),
            "openwrtVersion": build.get("openwrtVersion"),
            "sdkIdentity": build.get("sdkIdentity"),
            "sdkArchiveSha256": build.get("sdkArchiveSha256"),
        })
    # Keep one deterministic all-in-one manifest/checksum as a human-readable
    # convenience; matrix evidence remains target-specific in the input.
    dedicated_manifest = manifests[0] if manifests else None
    if dedicated_manifest:
        (output_root / "all-in-one-release-manifest.json").write_text(
            json.dumps(dedicated_manifest, ensure_ascii=False, indent=2) + "\n"
        )
    checksum_lines = [f"{sha256(target)}  {target.name}\n",
                      f"{sha256(integration_target)}  {integration_target.name}\n"]
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
            target_records.append({"packageArch": verified.get("arch") or built.get("arch") or build.get("architecture"), "rustTarget": build.get("rustTarget"), "target": build.get("target"),
                                   "openwrtVersion": build.get("openwrtVersion"),
                                   "packageManagerFormat": build.get("packageManagerFormat"),
                                   "sdkIdentity": build.get("sdkIdentity"),
                                   "sdkArchiveSha256": build.get("sdkArchiveSha256"),
                                   "apkFilename": built.get("apkFilename") or verified.get("filename"),
                                   "releaseFilename": built.get("releaseFilename") or verified.get("releaseFilename"),
                                   "apkSha256": built.get("apkSha256") or verified.get("sha256"),
                                   "status": verified.get("status")})
        aggregate_packages[name] = {"status": "ok", "targets": target_records}
    aggregate_metadata = {"schemaVersion": 2, "repositoryCommitSha": expected_commit,
                          "openwrtVersion": "multi-target", "architecture": "multi-target",
                          "target": "multi-target", "packageManagerFormat": "multi-format",
                          "externalRuntime": pairs[0][1].get("externalRuntime") or {},
                          "targets": [{"openwrtVersion": build.get("openwrtVersion"), "target": build.get("target"),
                                       "packageArch": build.get("architecture"),
                                       "rustTarget": build.get("rustTarget"),
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
        **primary_identity,
        "canonicalPath": str(target),
        "filename": target.name,
        "sha256": sha256(target),
        "architectureIndependentPackages": [
            {"package": PACKAGE, "filename": target.name, "sha256": sha256(target),
             "arch": primary_records[0]["packageArch"], "copyCount": primary_identity["copyCount"]},
            {"package": INTEGRATION_PACKAGE, "filename": integration_target.name,
             "sha256": sha256(integration_target), "arch": integration_records[0]["packageArch"],
             "copyCount": integration_identity["copyCount"]},
        ],
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
