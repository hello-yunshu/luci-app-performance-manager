#!/usr/bin/env python3
"""Validate the shared exact-qualified Stable Rill Runtime identity for PM."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import tempfile
import json
import os
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/rill-runtime.json"
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^1\.\d+\.\d+$")


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check(package_dir: Path | None) -> list[str]:
    return check_data(json.loads(CONTRACT.read_text(encoding="utf-8")), package_dir)


def check_data(data: dict, package_dir: Path | None) -> list[str]:
    errors: list[str] = []
    if data.get("schemaVersion") != 2:
        errors.append("schemaVersion must be 2")
    policy = data.get("policy", {})
    if any(policy.get(key) != value for key,value in {"major":1,"track":"shared-exact-qualified-stable"}.items()):
        errors.append("policy must be shared-exact-qualified-stable major 1")
    resolved = data.get("resolved", {})
    package = data.get("openwrtPackage", {})
    qualification = data.get("qualification", {})
    version = resolved.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("resolved.version must be an exact 1.x SemVer")
    if resolved.get("tag") != f"v{version}" and resolved.get("tag") != f"stable-main-{str(resolved.get('upstreamCommit', ''))[:7]}":
        errors.append("resolved.tag must be the release tag or stable-main commit sentinel")
    if not SHA1.fullmatch(str(resolved.get("upstreamCommit", ""))):
        errors.append("resolved.upstreamCommit must be an immutable SHA-1")
    if package.get("repository") != "hello-yunshu/rill-openwrt-packages":
        errors.append("openwrtPackage.repository is not canonical")
    if not SHA1.fullmatch(str(package.get("commit", ""))):
        errors.append("openwrtPackage.commit must be immutable")
    if package.get("package") != "rill-runtime":
        errors.append("openwrtPackage.package must be rill-runtime")
    if package.get("packageVersion") != version or package.get("binary") != "/usr/bin/rill-runtime":
        errors.append("package version or canonical binary drifted")
    if type(package.get("packageRelease")) is not int or package["packageRelease"]<=0:
        errors.append("package release must be positive")
    if type(qualification.get("runId")) is not int or qualification["runId"]<=0 or qualification.get("workflow")!="qualify.yml":
        errors.append("qualification requires exact run ID and workflow")
    if "runAttempt" in qualification and (type(qualification["runAttempt"]) is not int or qualification["runAttempt"]<=0 or not SHA256.fullmatch(str(qualification.get("manifestSha256","")))):
        errors.append("exact attempt requires the manifest digest")
    if qualification.get("required") is not True or qualification.get("verdict") != "PASS":
        errors.append("qualification is not required and PASS")
    if package_dir:
        makefile = package_dir / "package/rill-runtime/Makefile"
        metadata = package_dir / "metadata/rill-runtime.json"
        if not makefile.is_file() or not metadata.is_file():
            errors.append("package checkout is missing canonical Runtime metadata")
        else:
            make = makefile.read_text(encoding="utf-8")
            meta = json.loads(metadata.read_text(encoding="utf-8"))
            version_file = package_dir / "VERSION"
            versioned_recipe = any(line.startswith("PKG_VERSION:=") and "$(RILL_VERSION_FILE)" in line
                                   for line in make.splitlines())
            version_matches = (version_file.is_file() and version_file.read_text(encoding="utf-8").strip() == version
                               if versioned_recipe else f"PKG_VERSION:={version}" in make.splitlines())
            if not version_matches or "PKG_NAME:=rill-runtime" not in make.splitlines():
                errors.append("package Makefile identity does not match contract")
            if meta.get("package",{}).get("release")!=package.get("packageRelease") or f"PKG_RELEASE:={package.get('packageRelease')}\n" not in make:
                errors.append("package release differs from contract")
            upstream = meta.get("upstream", {})
            if (upstream.get("version") != version or upstream.get("commit") != resolved.get("upstreamCommit")
                    or meta.get("package", {}).get("name") != "rill-runtime"):
                errors.append("Stable package source identity does not match contract")
            try:
                if git_head(package_dir) != package.get("commit"):
                    errors.append("package checkout HEAD does not match contract")
            except (OSError, subprocess.CalledProcessError) as error:
                errors.append(f"cannot resolve package checkout HEAD: {error}")
    return errors


def api_headers() -> dict[str, str]:
    """Return GitHub API headers without ever exposing the token."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pm-rill-sync",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api(path: str):
    authenticated = "Authorization" in api_headers()
    request = Request(f"https://api.github.com/{path}", headers=api_headers())
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                f"GitHub API rate limit exceeded (authenticated={str(authenticated).lower()})"
            ) from error
        raise


def qualified_manifest(run, attempt, commit, package_dir):
    path=package_dir/'scripts/qualified_runtime_artifacts.py'
    if not path.is_file():raise ValueError('package checkout lacks schema 3 qualified-byte authority')
    spec=importlib.util.spec_from_file_location('pm_qualified_upstream',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.fetch_manifest(run,attempt,commit,package_dir)


def sync(package_dir: Path) -> int:
    old=json.loads(CONTRACT.read_text())
    if check_data(old,None):raise ValueError('existing Stable Runtime contract requires explicit repair')
    package_commit = git_head(package_dir)
    metadata = json.loads((package_dir / "metadata/rill-runtime.json").read_text(encoding="utf-8"))
    upstream = metadata.get("upstream", {})
    package = metadata.get("package", {})
    runs = api(f"repos/hello-yunshu/rill-openwrt-packages/actions/workflows/qualify.yml/runs?head_sha={package_commit}&status=completed&per_page=100").get("workflow_runs", [])
    passed = next((run for run in runs if run.get("conclusion") == "success"), None)
    if not passed:
        print(f"WAIT: no successful qualify.yml run for Stable package commit {package_commit}")
        return 0
    attempt=passed.get('run_attempt')
    if type(attempt) is not int or attempt<=0:raise ValueError('qualification has no exact attempt')
    evidence,raw,_=qualified_manifest(passed['id'],attempt,package_commit,package_dir)
    stable=evidence.get('package',{})
    # Schema 4 moved the upstream identity to the top level; older manifests kept it
    # under package. Read both so a feed schema bump cannot look like a provenance
    # mismatch. Mirrors the read in CFI's check_rill_dependency.py.
    qualified_upstream=evidence.get('upstream') or stable.get('upstream',{})
    if qualified_upstream.get('commit') != upstream.get('commit'):
        raise ValueError(
            'qualified Stable source differs from package metadata: '
            f"manifest {qualified_upstream.get('commit')} vs metadata {upstream.get('commit')}"
        )
    if any(stable.get(key)!=package.get(field) for key,field in [('name','name'),('version','version'),('release','release')]):
        raise ValueError('qualified Stable package differs from package metadata')
    candidate=copy.deepcopy(old)
    candidate['resolved'].update({'version':upstream['version'],'tag':upstream['tag'],'upstreamCommit':upstream['commit']})
    candidate['openwrtPackage'].update({
        'repository': 'hello-yunshu/rill-openwrt-packages', 'commit': package_commit,
        'package': package['name'], 'packageVersion': package['version'],
        'packageRelease': package['release'], 'binary': package['binary'],
    })
    candidate['qualification'] = {
        'required': True, 'workflow': 'qualify.yml', 'runId': passed['id'],
        'runAttempt': attempt, 'manifestSha256': hashlib.sha256(raw).hexdigest(), 'verdict': 'PASS',
    }
    errors=check_data(candidate,package_dir)
    if errors:raise ValueError('; '.join(errors))
    if candidate==old:
        print('No new qualified Stable Runtime contract.')
        return 0
    descriptor,name=tempfile.mkstemp(prefix='.rill-contract-',dir=CONTRACT.parent)
    try:
        os.fchmod(descriptor,CONTRACT.stat().st_mode&0o777)
        with os.fdopen(descriptor,'w') as stream:
            stream.write(json.dumps(candidate,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
        if check_data(json.loads(Path(name).read_text()),package_dir):raise ValueError('serialized contract failed validation')
        os.replace(name,CONTRACT)
    finally:Path(name).unlink(missing_ok=True)
    print(json.dumps(candidate, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--sync", action="store_true", help="resolve latest qualified Stable 1.x and update the contract")
    args = parser.parse_args()
    if args.sync:
        if not args.package_dir:
            parser.error("--sync requires --package-dir")
        try:
            return sync(args.package_dir)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            print(f"FAIL: {error}", file=sys.stderr)
            return 1
    errors = check(args.package_dir)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    print(f"PASS: shared qualified Stable rill-runtime {data['resolved']['version']} from {data['openwrtPackage']['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
