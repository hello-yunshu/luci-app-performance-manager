#!/usr/bin/env python3
"""Generate build-metadata.json for the remote OpenWrt SDK build gate.

This is the auditable evidence record required by the RC gate: it captures the
repository commit, OpenWrt version/architecture, SDK identity/digest, feed
commits, the packages that were built, the package manager format, the pinned
upstream Rill release this repo consumes (never `latest`), and the overall
PASS/FAIL verdict. It is emitted by the remote GitHub Actions build job; the
script is kept runnable on the host so the schema and field population can be
reused and tested without a toolchain.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def env(key, default=None):
    return os.environ.get(key) or default


def sh(args, cwd=None):
    try:
        cp = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return cp.stdout.strip()
    except Exception:
        return None


def sdk_digest(sdk_dir):
    sdk_dir = Path(sdk_dir)
    # The SDK root Makefile is a stable, small identity anchor for the SDK tree.
    p = sdk_dir / 'Makefile'
    if p.exists():
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception:
            return None
    return None


def feeds_commits(sdk_dir):
    """Record the pinned feed commit from each feed directory's .git origin, if
    the SDK retains feed metadata (fresh SDKs do)."""
    result = {}
    feeds = Path(sdk_dir) / 'feeds'
    if not feeds.exists():
        return result
    for f in sorted(feeds.iterdir()):
        if not f.is_dir():
            continue
        rev = sh(['git', '-C', str(f), 'rev-parse', '--short', 'HEAD'])
        if rev:
            result[f.name] = rev
    return result


def main(argv):
    repo = env('GITHUB_REPOSITORY', 'luci-app-performance-manager')
    commit = env('GITHUB_SHA', sh(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']) or 'unknown')
    run_id = env('GITHUB_RUN_ID', 'local')
    workflow = env('GITHUB_WORKFLOW', 'build-openwrt')
    openwrt_version = env('OPENWRT_VERSION', argv[1] if len(argv) > 1 else '25.12.5')
    target = env('OPENWRT_TARGET', 'x86/64')
    sdk_dir = env('SDKDIR', argv[2] if len(argv) > 2 else '')
    sdk_identity = Path(sdk_dir).name if sdk_dir else 'not-built-local'
    arch = 'x86_64'
    pkg_manager = 'apk'  # OpenWrt 25.12 uses apk; ipk is legacy (24.10 and earlier).

    dep_file = ROOT / 'contracts' / 'rill-dependency.json'
    dep = json.loads(dep_file.read_text()) if dep_file.exists() else {}
    up = dep.get('upstream') or {}
    rill_repo = up.get('repository') or None
    rill_version = up.get('releaseVersion') or None
    rill_checksum = up.get('artifactSha256') or None
    rill_status = up.get('status') or 'external-dependency-blocked'

    packages = ['performance-manager', 'luci-app-performance-manager', 'performance-manager-rill']
    package_shas = {}
    for name in packages:
        mk = ROOT / 'package' / name / 'Makefile'
        if mk.exists():
            package_shas[name] = hashlib.sha256(mk.read_bytes()).hexdigest()

    # The build gate is PASS only when the expected APK packages were produced
    # and the Rill consumed release (when provisioned) is pinned, never latest.
    expected_apks = [f'{name}_*.apk' for name in packages]
    apks_found = []
    if sdk_dir:
        for apk in Path(sdk_dir).rglob('*.apk'):
            if any(apk.name.startswith(name + '_') for name in packages):
                apks_found.append(apk.name)
    build_pass = bool(sdk_dir) and len(apks_found) >= len(packages) and 'latest' not in (up.get('artifactUrl') or '')

    metadata = {
        'schemaVersion': 1,
        'repository': repo,
        'repositoryCommitSha': commit,
        'openwrtVersion': openwrt_version,
        'architecture': arch,
        'target': target,
        'sdkIdentity': sdk_identity,
        'sdkDir': sdk_dir or None,
        'sdkSha256': sdk_digest(sdk_dir) if sdk_dir else None,
        'feedsCommits': feeds_commits(sdk_dir) if sdk_dir else {},
        'packageManagerFormat': pkg_manager,
        'packages': {name: {'makefileSha256': package_shas.get(name)} for name in packages},
        'expectedApkPackages': expected_apks,
        'producedApkPackages': sorted(apks_found),
        'rillUpstreamRepository': rill_repo,
        'rillConsumedVersion': rill_version,
        'rillConsumedArtifactSha256': rill_checksum,
        'rillUpstreamStatus': rill_status,
        'workflow': workflow,
        'workflowRunId': run_id,
        'buildTimestamp': datetime.now(timezone.utc).isoformat(),
        'verdict': 'PASS' if build_pass else 'FAIL',
    }
    out = ROOT / 'build-metadata.json' if not env('BUILD_EVIDENCE_OUT') else Path(env('BUILD_EVIDENCE_OUT'))
    out.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'verdict': metadata['verdict'], 'producedApks': len(apks_found), 'output': str(out)},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if build_pass else 1)


if __name__ == '__main__':
    main(sys.argv)