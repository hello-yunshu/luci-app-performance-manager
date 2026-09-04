#!/usr/bin/env python3
"""Stage the public PM release: exactly three full architecture APKs.

All evidence is consumed from Actions artifacts but is never copied to the
public directory. The package filename shown to users is normalized from
VERSION and the verified target architecture.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from artifact_identity import ArtifactIdentityError, resolve_artifact, sha256


PACKAGE = "luci-app-performance-manager-all"
PUBLIC_PREFIX = "performance-manager-all"
TARGETS = {
    "x86_64": ("x86/64", "x86_64-unknown-linux-musl"),
    "aarch64_generic": ("armsr/armv8", "aarch64-unknown-linux-musl"),
    "aarch64_cortex-a53": ("mediatek/filogic", "aarch64-unknown-linux-musl"),
}


def _files(root: Path, name: str) -> list[Path]:
    return sorted((p for p in root.rglob(name) if p.is_file()), key=lambda p: str(p))


def read_one_json(root: Path, name: str, *, required: bool = True) -> tuple[Path | None, dict | None]:
    matches = _files(root, name)
    if not matches:
        if required:
            raise ArtifactIdentityError(f"missing {name} under {root}")
        return None, None
    values = [(p, json.loads(p.read_text())) for p in matches]
    first = json.dumps(values[0][1], sort_keys=True, separators=(",", ":"))
    if any(json.dumps(v, sort_keys=True, separators=(",", ":")) != first for _, v in values[1:]):
        raise ArtifactIdentityError(f"conflicting copies of {name}: {[str(p) for p, _ in values]}")
    return values[0]


def read_matrix_reports(root: Path) -> list[tuple[Path, dict, Path, dict]]:
    metadata = _files(root, "build-metadata.json")
    verification = _files(root, "apk-verification.json")
    if not metadata or len(metadata) != len(verification):
        raise ArtifactIdentityError("matrix build metadata and APK verification counts disagree")
    verification_values = [(p, json.loads(p.read_text())) for p in verification]
    pairs = []
    for metadata_path in metadata:
        build = json.loads(metadata_path.read_text())
        commit = build.get("repositoryCommitSha")
        arch = build.get("architecture")
        candidates = [(p, report) for p, report in verification_values
                      if report.get("pmCommitSha") == commit and report.get("arch") == arch]
        if not candidates:
            candidates = [(p, report) for p, report in verification_values
                          if p.parent == metadata_path.parent]
        if len(candidates) != 1:
            raise ArtifactIdentityError(f"cannot pair target evidence under {metadata_path.parent}")
        verification_path, report = candidates[0]
        if build.get("verdict") != "PASS" or report.get("verdict") != "PASS":
            raise ArtifactIdentityError(f"target evidence is not PASS under {metadata_path.parent}")
        if commit != report.get("pmCommitSha"):
            raise ArtifactIdentityError(f"target evidence commit mismatch under {metadata_path.parent}")
        pairs.append((metadata_path, build, verification_path, report))
    return pairs


def _full_record(build: dict, report: dict, arch: str) -> tuple[str, str]:
    verified = (report.get("packages") or {}).get(PACKAGE) or {}
    built = (build.get("packages") or {}).get(PACKAGE) or {}
    filename = built.get("apkFilename") or verified.get("filename")
    digest = built.get("apkSha256") or verified.get("sha256")
    runtime = verified.get("runtimeBinary") or {}
    if (verified.get("status") != "ok" or built.get("status") != "ok"
            or verified.get("sha256") != built.get("apkSha256")
            or verified.get("arch") != arch or not filename or not digest
            or runtime.get("status") != "present"
            or runtime.get("matchesSplitRuntime") is not True):
        raise ArtifactIdentityError(f"{PACKAGE} full identity is incomplete for {arch}")
    return filename, digest


def assemble_public_apk(*, input_root: Path, output_root: Path, expected_commit: str,
                        version: str | None = None, expected_filename: str | None = None) -> dict:
    pairs = read_matrix_reports(input_root)
    if any(build.get("repositoryCommitSha") != expected_commit for _, build, _, _ in pairs):
        raise ArtifactIdentityError("matrix build evidence is not for the expected commit")
    by_arch = {build.get("architecture"): (metadata, build, verification, report)
               for metadata, build, verification, report in pairs}
    if set(by_arch) != set(TARGETS):
        raise ArtifactIdentityError(f"expected exactly the three full target architectures, got {sorted(by_arch)}")
    resolved_version = version or str((pairs[0][3].get("expectedVersion") or "")).replace("_rc", "-rc.")
    if not resolved_version:
        raise ArtifactIdentityError("VERSION is required to name public assets")
    output_root.mkdir(parents=True, exist_ok=True)
    staged = []
    for arch in sorted(TARGETS):
        _, build, _, report = by_arch[arch]
        filename, digest = _full_record(build, report, arch)
        # The same package filename may be emitted by all SDK targets while
        # the native payload differs. Select by the authoritative target SHA
        # before asking the identity resolver to compare duplicate copies.
        target_candidates = [p for p in _files(input_root, filename) if sha256(p) == digest]
        if not target_candidates:
            raise ArtifactIdentityError(f"{PACKAGE}: no target copy found for {arch} and {digest}")
        try:
            identity = resolve_artifact(PACKAGE, digest, target_candidates, filename)
        except ArtifactIdentityError as exc:
            raise ArtifactIdentityError(str(exc)) from exc
        public_name = f"{PUBLIC_PREFIX}-v{resolved_version}-{arch}.apk"
        if expected_filename and public_name != expected_filename:
            raise ArtifactIdentityError(f"requested filename {expected_filename!r} does not match {public_name!r}")
        target = output_root / public_name
        shutil.copy2(identity["canonicalPath"], target)
        staged.append({
            "package": PACKAGE, "filename": target.name, "sourceFilename": filename,
            "sha256": sha256(target), "bytes": target.stat().st_size,
            "packageArch": arch, "target": build.get("target"),
            "runtime": ((report.get("packages") or {}).get(PACKAGE) or {}).get("runtimeBinary"),
            "artifactIdentity": identity,
        })
    checksum = output_root / "SHA256SUMS.txt"
    checksum.write_text("".join(f"{item['sha256']}  {item['filename']}\n" for item in staged))
    return {"version": resolved_version, "commit": expected_commit, "assets": staged,
            "checksum": {"filename": checksum.name, "sha256": sha256(checksum)}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--version")
    parser.add_argument("--expected-filename")
    args = parser.parse_args(argv)
    result = assemble_public_apk(input_root=Path(args.input).resolve(), output_root=Path(args.out).resolve(),
                                 expected_commit=args.expected_commit, version=args.version,
                                 expected_filename=args.expected_filename)
    print(json.dumps({"version": result["version"], "commit": result["commit"],
                      "files": [item["filename"] for item in result["assets"]] + ["SHA256SUMS.txt"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
