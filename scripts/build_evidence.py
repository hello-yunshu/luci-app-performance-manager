#!/usr/bin/env python3
"""Generate build-metadata.json for the remote OpenWrt SDK build gate.

This is the auditable evidence record required by the RC gate: it captures the
repository commit, OpenWrt version/architecture, SDK identity/digest, feed
commits, the packages that were built, the package manager format, the pinned
upstream Rill release this repo consumes (never `latest`), and the overall
PASS/FAIL verdict. It is emitted by the remote GitHub Actions build job; the
script is kept runnable on the host so the schema and field population can be
reused and tested without a toolchain.

Package verification is NOT re-derived here from weak filename prefixes.
The authoritative source is the exact APK report written by
scripts/verify_apks.py (docs/apk-verification.json), which matches every
expected package on pkgname/pkgver/arch/depends and asserts the Core daemon
inside the built APK is byte-identical (SHA256) to the shipped source.  The
metadata also separates the build verdicts so an "APK build PASS" can never be
misread as a full RC PASS: pmPackagesBuildVerdict / apkExactVerificationVerdict
/ rillArtifactProvenanceVerdict / rillRuntimeCompatibilityVerdict /
rillFunctionalIntegrationVerdict are recorded independently and combined only
into the explicit rcVerdict.
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
    rill_checksum = (up.get('artifact') or {}).get('sha256') or None
    rill_status = up.get('status') or 'external-dependency-blocked'

    # Evidence is consumed from the per-job evidence files (prompt section 27),
    # so a job can never read a JSON another parallel job overwrote.  Each job
    # writes ONE file it owns:
    #   pm-rill-provenance   -> docs/rill-provenance.json
    #   pm-rill-runtime      -> docs/rill-runtime.json
    #   pm-core-rill-roundtrip -> docs/rill-core-integration.json
    #   openwrt-sdk-build    -> build-metadata.json (this script)
    # A per-job file present in the checkout wins; otherwise we fall back to the
    # legacy shared docs/rill-integration-evidence.json seed.  Any missing or
    # unknown verdict is BLOCKED (never fabricated PASS).
    def _read_json(path):
        p = ROOT / 'docs' / path
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}
        return {}

    _prov_job = _read_json('rill-provenance.json')
    _rt_job = _read_json('rill-runtime.json')
    _core_job = _read_json('rill-core-integration.json')
    _ev = _read_json('rill-integration-evidence.json')

    # Tracked reports are documentation snapshots, not current-run evidence.
    # Consume them only when their embedded PM commit matches this exact SDK
    # build commit; otherwise the corresponding runtime/provenance verdict is
    # BLOCKED and must be supplied by the CI run's per-job artifacts.
    def _evidence_commit(data):
        if not isinstance(data, dict):
            return None
        return data.get('pmCommitSha') or ((data.get('pm') or {}).get('commitSha'))

    _prov_job = _prov_job if _evidence_commit(_prov_job) == commit else {}
    _rt_job = _rt_job if _evidence_commit(_rt_job) == commit else {}
    _core_job = _core_job if _evidence_commit(_core_job) == commit else {}
    _ev = _ev if _evidence_commit(_ev) == commit else {}
    _ril = (_ev.get('rill', {}) or {}) if isinstance(_ev, dict) else {}
    _relidx = (_ev.get('releaseIndex', {}) or {}) if isinstance(_ev, dict) else {}
    _art = (_ev.get('artifact', {}) or {}) if isinstance(_ev, dict) else {}
    _rt = (_ev.get('runtime', {}) or {}) if isinstance(_ev, dict) else {}

    def _norm(v):
        v = str(v or 'BLOCKED').upper()
        return v if v in ('PASS', 'FAIL', 'BLOCKED') else 'BLOCKED'

    def combine_required(values):
        """Evidence aggregation rule (prompt section 25): ANY FAIL -> FAIL,
        ALL PASS -> PASS, otherwise BLOCKED.  A PASS + BLOCKED mix is BLOCKED,
        never silently upgraded to PASS."""
        vals = [_norm(v) for v in values]
        if any(v == 'FAIL' for v in vals):
            return 'FAIL'
        if all(v == 'PASS' for v in vals):
            return 'PASS'
        return 'BLOCKED'

    def _prov_verdicts():
        # Provenance verdicts live under DIFFERENT objects in the evidence
        # (rill.tagIdentityVerdict / releaseIndex.indexSignatureVerdict /
        # artifact.artifactIntegrityVerdict), not all under `rill`.  The
        # per-job rill-provenance.json mirrors the same split (tag at top level,
        # artifact integrity nested under artifact).  Read the REAL paths.
        if _prov_job:
            return [
                _prov_job.get('tagIdentityVerdict'),
                _prov_job.get('indexSignatureVerdict'),
                (_prov_job.get('artifact') or {}).get('artifactIntegrityVerdict'),
            ]
        return [
            _ril.get('tagIdentityVerdict'),
            _relidx.get('indexSignatureVerdict'),
            _art.get('artifactIntegrityVerdict'),
        ]

    def _rt_verdicts(fields):
        # Real runtime verdicts live in the per-job rill-runtime.json under
        # `verdicts.*`; the legacy shared evidence keeps them under `runtime.*`.
        if _rt_job:
            v = _rt_job.get('verdicts') or {}
            return [v.get(f) for f in fields]
        return [_rt.get(f) for f in fields]

    def _core_roundtrip_verdict():
        # Core<->adapter roundtrip is a separate parallel job; its own per-job
        # file is authoritative when present (never the shared seed, which the
        # roundtrip job must not clobber).
        if _core_job:
            return _core_job.get('verdict')
        return _rt.get('pmCoreRoundtripVerdict')

    packages = ['performance-manager', 'luci-app-performance-manager', 'performance-manager-rill']
    package_shas = {}
    for name in packages:
        mk = ROOT / 'package' / name / 'Makefile'
        if mk.exists():
            package_shas[name] = hashlib.sha256(mk.read_bytes()).hexdigest()

    # Authoritative package verification: consume the exact APK report produced
    # by scripts/verify_apks.py (exact pkgname/pkgver/arch/depends match + the
    # Core daemon SHA256 inside the APK vs the shipped source).  build_evidence
    # never re-does weak filename-prefix inference, because `performance-manager-*`
    # also matches the integration package and could mask a missing Core.
    apk_report = None
    apk_report_path = ROOT / 'docs' / 'apk-verification.json'
    if apk_report_path.exists():
        try:
            apk_report = json.loads(apk_report_path.read_text())
        except Exception:
            apk_report = None

    report_packages = (apk_report or {}).get('packages', {})
    produced = {}
    for name in packages:
        rec = report_packages.get(name) or {}
        produced[name] = rec.get('filename') if rec.get('status') not in ('missing', 'duplicate') else None

    pm_build_verdict = 'PASS' if (apk_report is not None and all(produced[n] for n in packages)) else 'FAIL'
    apk_exact_verdict = 'PASS' if (apk_report or {}).get('verdict') == 'PASS' else 'FAIL'

    # Rill Gate 1 — Artifact Provenance: pinned release tag/URL/SHA256/asset and
    # tag commit, never `latest`/`main`.  A not-provisioned (blocked) upstream is
    # an honest state (the Core fails closed); a provisioned-but-broken pin FAILS.
    # A provisioned pin is the baseline; an authoritative PASS additionally
    # requires the signed upstream evidence verdicts (tag identity, Ed25519 index
    # signature, artifact integrity) from docs/rill-integration-evidence.json --
    # a hand-written SHA alone is never enough (prompt \u00a712/\u00a729).
    artifact = up.get('artifact') or {}
    artifact_url = artifact.get('url') or ''
    provisioned = bool(up.get('releaseVersion') or artifact_url)
    if not provisioned:
        rill_provenance = 'BLOCKED'
        rill_provenance_reason = 'no upstream Rill release provisioned (external-dependency-blocked)'
    elif not (artifact.get('sha256') and artifact_url and 'latest/download' not in artifact_url
              and up.get('releaseVersion') and up.get('tagCommitSha')):
        rill_provenance = 'FAIL'
        rill_provenance_reason = 'upstream Rill release entry is incomplete or unpinned'
    else:
        _evidence_prov = combine_required(_prov_verdicts())
        if _evidence_prov == 'FAIL':
            rill_provenance = 'FAIL'
            rill_provenance_reason = 'evidence provenance verdict FAIL (tag identity / index signature / artifact integrity)'
        elif _evidence_prov == 'PASS':
            rill_provenance = 'PASS'
            rill_provenance_reason = None
        else:
            rill_provenance = 'BLOCKED'
            rill_provenance_reason = 'pin present but signed upstream evidence not resolved in this job'

    # Rill Gates 2 (Runtime Compatibility) and 3 (Functional Integration) require
    # executing the real adapter and are recorded by the gate jobs. The verdicts
    # come from the per-job evidence files (rill-runtime.json / rill-core-integration.json);
    # any missing/unknown verdict is BLOCKED (never fabricated PASS).
    rill_runtime_verdict = combine_required(_rt_verdicts(
        ['executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict']))
    _core_v = _core_roundtrip_verdict()
    rill_functional_verdict = combine_required(
        _rt_verdicts(['observeVerdict', 'outcomeVerdict', 'failClosedVerdict']) + [_core_v])

    verdicts = {
        'pmPackagesBuildVerdict': pm_build_verdict,
        'apkExactVerificationVerdict': apk_exact_verdict,
        'rillArtifactProvenanceVerdict': rill_provenance,
        'rillRuntimeCompatibilityVerdict': rill_runtime_verdict,
        'rillFunctionalIntegrationVerdict': rill_functional_verdict,
    }
    if all(v == 'PASS' for v in verdicts.values()):
        rc_verdict = 'PASS'
    elif any(v == 'FAIL' for v in verdicts.values()):
        rc_verdict = 'FAIL'
    else:
        rc_verdict = 'BLOCKED'

    # The SDK build job itself gates on: all expected packages built + the exact
    # APK verification passing + a valid Rill pin (a blocked upstream does not
    # fail the build; a provisioned-but-broken pin does).  The combined rcVerdict
    # is recorded separately so an APK build PASS is never read as a full RC PASS.
    build_pass = (pm_build_verdict == 'PASS' and apk_exact_verdict == 'PASS'
                  and rill_provenance in ('PASS', 'BLOCKED'))

    packages_meta = {}
    for name in packages:
        entry = {'makefileSha256': package_shas.get(name)}
        rec = report_packages.get(name) or {}
        if rec:
            entry['status'] = rec.get('status')
            if rec.get('filename'):
                entry['apkFilename'] = rec['filename']
            if rec.get('sha256'):
                entry['apkSha256'] = rec['sha256']
            if rec.get('pkgver'):
                entry['pkgver'] = rec['pkgver']
            if rec.get('arch'):
                entry['arch'] = rec['arch']
            if name == 'performance-manager' and 'core' in rec:
                entry['core'] = rec['core']
        packages_meta[name] = entry

    metadata = {
        'schemaVersion': 1,
        'repository': repo,
        'repositoryCommitSha': commit,
        'openwrtVersion': openwrt_version,
        'architecture': arch,
        'target': target,
        'sdkIdentity': sdk_identity,
        'sdkDir': sdk_dir or None,
        # sdkTreeAnchorSha256 is the digest of the SDK root Makefile (a stable
        # identity anchor for the SDK tree).  sdkArchiveSha256 is the REAL digest
        # of the official SDK archive, captured from downloads.openwrt.org
        # sha256sums and exported as SDK_ARCHIVE_SHA256 by the build job.
        'sdkTreeAnchorSha256': sdk_digest(sdk_dir) if sdk_dir else None,
        'sdkArchiveSha256': env('SDK_ARCHIVE_SHA256') or None,
        'feedsCommits': feeds_commits(sdk_dir) if sdk_dir else {},
        'packageManagerFormat': pkg_manager,
        'packages': packages_meta,
        'expectedApkPackages': list(packages),
        'producedApkPackages': [produced[n] for n in packages if produced[n]],
        'apkExactVerificationVerdict': apk_exact_verdict,
        'apkVerificationReport': str(apk_report_path) if apk_report is not None else None,
        'rillUpstreamRepository': rill_repo,
        'rillConsumedVersion': rill_version,
        'rillConsumedArtifactSha256': rill_checksum,
        'rillUpstreamStatus': rill_status,
        'rillArtifactProvenanceReason': rill_provenance_reason,
        'evidenceSources': {
            'provenance': str(ROOT / 'docs' / 'rill-provenance.json') if _prov_job else str(ROOT / 'docs' / 'rill-integration-evidence.json'),
            'runtime': str(ROOT / 'docs' / 'rill-runtime.json') if _rt_job else str(ROOT / 'docs' / 'rill-integration-evidence.json'),
            'coreRoundtrip': str(ROOT / 'docs' / 'rill-core-integration.json') if _core_job else str(ROOT / 'docs' / 'rill-integration-evidence.json'),
        },
        'verdictAggregationRule': 'ANY FAIL -> FAIL; ALL PASS -> PASS; otherwise BLOCKED (combine_required)',
        'workflow': workflow,
        'workflowRunId': run_id,
        'buildTimestamp': datetime.now(timezone.utc).isoformat(),
        'verdicts': {**verdicts, 'rcVerdict': rc_verdict},
        'verdict': 'PASS' if build_pass else 'FAIL',
    }
    out = ROOT / 'build-metadata.json' if not env('BUILD_EVIDENCE_OUT') else Path(env('BUILD_EVIDENCE_OUT'))
    out.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({
        'verdict': metadata['verdict'],
        'pmPackagesBuildVerdict': pm_build_verdict,
        'apkExactVerificationVerdict': apk_exact_verdict,
        'rillArtifactProvenanceVerdict': rill_provenance,
        'rcVerdict': rc_verdict,
        'producedApks': [produced[n] for n in packages if produced[n]],
        'output': str(out),
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if build_pass else 1)


if __name__ == '__main__':
    main(sys.argv)
