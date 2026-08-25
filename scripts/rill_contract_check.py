#!/usr/bin/env python3
"""PM<->Rill PM-side STATIC dependency/protocol contract gate (external runtime).

Rill is owned, built and released by its upstream repository.  This repository
never compiles or natively tests Rill.  This script verifies ONLY the PM-side
static contract and the well-formedness/immutability of the pinned upstream
release entry:

  1. the formal IPC schema and the Core agree on the pm-rill-shadow v1 protocol
     and the shadow-only required ops (exactly status/observe/outcome), with the
     bounded ContextKey pattern `^ctx-v1:` (max 512);
  2. the Core capability gate is fail-closed (missing runtime, unreachable
     service, protocol mismatch and capability mismatch are surfaced as
     unavailable/incompatible, never silently assumed OK) and the Core/init
     binary resolver implement the same resolution contract;
  3. the pinned upstream release entry is well-formed and immutable: pinned
     versioned tag, resolved tag commit, signed Stable
     release index (channel stable, schemaVersion 3, publisher identity) and an
     exact adapter URL + SHA-256 (never `latest`/`main`/branch, never empty).

This script NEVER outputs `functionalIntegration = PASS`.  Real tag identity,
signed-index signature and artifact integrity must come from
scripts/verify_rill_release.py, and real adapter runtime / PM Core roundtrip
must come from the runtime jobs (pm-rill-runtime, pm-core-rill-roundtrip).  All
those verdicts are recorded in docs/rill-integration-evidence.json.  A
blocked/not-provisioned upstream is a legitimate honest state as long as the
Core fails closed and the integration package never compiles/bundles Rill.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
INIT=(ROOT/'package/performance-manager-rill/files/etc/init.d/performance-manager-rill').read_text()
SCHEMA=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
DEP=json.loads((ROOT/'contracts/rill-dependency.json').read_text())
RILL_MAKE=(ROOT/'package/performance-manager-rill/Makefile').read_text()

checks=[]
def check(name, ok):
    checks.append((name, bool(ok)))
    if not ok: print('FAIL:', name)

# 1. Formal IPC schema + Core protocol agreement (pm-rill-shadow v1).
def branch_props(op):
    """Schema properties of the oneOf per-op branch (rill-ipc.schema.json)."""
    return SCHEMA['$defs'][f'{op}Request']['properties']

check('schema contract const==pm-rill-shadow', branch_props('status')['contract']['const']=='pm-rill-shadow')
check('schema protocolVersion const==1', branch_props('status')['protocolVersion']['const']==1)
check('DEP protocol contract==pm-rill-shadow', DEP['protocol']['contract']=='pm-rill-shadow')
check('DEP protocol protocolVersion==1', DEP['protocol']['protocolVersion']==1)
check('DEP protocol schemaFile present', bool(DEP['protocol']['schemaFile']))
ops={branch_props(op)['op']['const'] for op in ('status','observe','outcome')}
check('schema ops == {status,observe,outcome}', ops=={'status','observe','outcome'})
check('Core shadow-only ops contract', "const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ]" in CORE)
check('DEP requiredOps match', set(DEP['protocol']['requiredOps'])==ops)
check('schema contextKey pattern ^ctx-v1:', SCHEMA['$defs']['contextKey']['pattern']=='^ctx-v1:')
check('schema contextKey maxLength 512', SCHEMA['$defs']['contextKey']['maxLength']==512)
check('DEP contextKey pattern <=> schema', DEP['protocol'].get('contextKeyPattern')=='^ctx-v1:' and DEP['protocol'].get('contextKeyMaxLength')==512)
check('Core contextKey wiring', 'ctx-v1:' in CORE and 'rill_context_key_build' in CORE)

# 2. Core + init fail-closed and the unique binary-resolution contract.
# NOTE: 'external-runtime-missing' was merged into the unified binary resolver
# (explicit-missing -> 'binary-invalid', default-missing -> 'not-provisioned'), so it
# is no longer a distinct surfaced reason.
for token in [ 'binary-invalid', 'external-runtime-not-provisioned',
               'protocol-version-mismatch', 'contract-mismatch', 'missing-required-capability',
               "const RILL_CONTRACT = 'pm-rill-shadow'", 'const RILL_PROTOCOL_VERSION = 1',
               'RILL_STATES.incompatible', 'RILL_STATES.notProvisioned' ]:
    check('Core fail-closed gate token: '+token, token in CORE)
check('Core declares shared rill_binary_path resolver', 'function rill_binary_path(' in CORE)
check('Core resolver checks both default paths', '/usr/bin/rill-pm-adapter' in CORE and '/usr/sbin/rill-pm-adapter' in CORE)
check('Core resolver fails closed on explicit binary', "'binary-invalid'" in CORE and "source: 'explicit'" in CORE)
check('init declares resolve_binary resolver', 'resolve_binary()' in INIT)
check('init resolver checks both default paths', '/usr/bin/rill-pm-adapter' in INIT and '/usr/sbin/rill-pm-adapter' in INIT)
check('init fails closed on explicit binary', 'binary-invalid' in INIT and 'BINARY_STATE=' in INIT)

# 3. Version-field distinction (release bundle vs adapter crate/binary).
up=DEP.get('upstream',{})
adapter=up.get('adapter') or {}
art=up.get('artifact') or {}
ri=up.get('releaseIndex') or {}
target=(adapter.get('target') or {})
release=up.get('releaseVersion')
adapter_version=adapter.get('adapterVersion')
protocol_version=DEP.get('protocol',{}).get('protocolVersion')
expected_tag=f'v{release}'
expected_x86_name=f"rill-pm-adapter-{release}-linux-x86_64-musl"
check('minimumReleaseVersion derives from upstream release', DEP.get('minimumReleaseVersion')==release)
check('minimumAdapterVersion present', DEP.get('minimumAdapterVersion')==adapter_version=='0.15.0')
check('minimumRillVersion kept only as deprecated alias', DEP.get('minimumRillVersion')==release and 'DEPRECATED' in str(DEP.get('minimumRillVersionDeprecatedNote','')))

# 4. Integration package never compiles/bundles Rill.
check('integration package never compiles Rill', 'cargo' not in RILL_MAKE and 'rust' not in RILL_MAKE.lower()
      and 'PKG_BUILD_DEPENDS:=' in RILL_MAKE)
check('no bundled Rust source', not (ROOT/'package/performance-manager-rill/src').exists())

# 5. Upstream release entry policy (immutable Stable dependency).
pinned = bool(up.get('releaseVersion')) and bool(up.get('releaseTag')) and bool(up.get('tagCommitSha')) \
        and bool(adapter.get('url')) and bool(adapter.get('sha256')) and bool(adapter.get('size'))
if pinned:
    check('release pinned (no latest/download/branch)', 'latest/download' not in (adapter.get('url') or '') and 'latest/' not in (adapter.get('url') or ''))
    check('tag commit non-empty', bool(up.get('tagCommitSha')))
    check('release tag derives from releaseVersion', up.get('releaseTag')==expected_tag)
    check('release channel == stable (never candidate)', ri.get('channel')=='stable')
    check('release index schemaVersion == 3 (fail-closed on unknown)', ri.get('schemaVersion')==3)
    check('publisher identity present', bool(ri.get('publisherKeyId')) and bool(ri.get('publicKeyHex')))
    check('adapter protocol version == 1', adapter.get('pmAdapterProtocolVersion')==1)
    check('adapter target == linux/x86_64/musl', target.get('os')=='linux' and target.get('arch')=='x86_64' and target.get('libc')=='musl')
    check('adapter release asset version vs binary version distinct', adapter.get('releaseAssetVersion')==release and adapter.get('adapterVersion')==adapter_version)
    check('adapter name derives from release', adapter.get('name')==expected_x86_name)
    check('adapter x86 identity matches artifact', all(adapter.get(k)==art.get(k) for k in ('id','name','url','sha256','size')))
    x86 = (up.get('artifacts') or {}).get('linux-x86_64-musl') or {}
    check('adapter x86 identity matches artifacts[x86]', all(adapter.get(k)==x86.get(k) for k in ('name','url','sha256','size')))
    aarch = (up.get('artifacts') or {}).get('linux-aarch64-musl')
    if aarch is not None:
        check('aarch64 artifact identity is complete', all(aarch.get(k) for k in ('name','url','sha256','size')))
    release_urls = [ri.get('url'), ri.get('signatureUrl'), up.get('manifestUrl'), adapter.get('url'), art.get('url')]
    release_urls += [entry.get('url') for entry in (up.get('artifacts') or {}).values()]
    check('all release URLs point to the pinned tag', all(isinstance(url, str) and f'/v{release}/' in url for url in release_urls))
    check('release index and manifest URLs are identical', ri.get('url')==ri.get('signatureUrl')==up.get('manifestUrl'))
    check('adapter sha256 matches artifact', adapter.get('sha256')==art.get('sha256'))
    check('adapter size matches artifact', adapter.get('size')==art.get('size'))
    check('no branch URL / main / HEAD', all(x not in (adapter.get('url') or '') for x in ['/latest', 'main', 'master', 'HEAD', 'nightly', 'raw/main']))
else:
    status_key=up.get('status','external-dependency-blocked')
    check('upstream status is blocked/not-provisioned', status_key in ('external-dependency-blocked','blocked','not-provisioned','provisioned'))
    check('blocked reason recorded', bool(up.get('blockedReason')) or status_key=='provisioned')

ok=all(ok for _,ok in checks)
static_contract = 'PASS' if ok else 'FAIL'
release_pin_structure = 'PASS' if (pinned and ok) else ('BLOCKED' if not pinned else 'FAIL')
status={
    'schemaVersion': 3,
    'contract': 'rill-integration-status',
    'scope': 'PM-side static protocol/dependency contract + immutable Stable release pin only',
    'staticContractVerdict': static_contract,
    'releasePinStructureVerdict': release_pin_structure,
    'functionalIntegrationVerdict': 'NOT_EVALUATED',
    'promotionPolicy': 'This source-only report is non-promotable. It cannot produce a feature, release-candidate, or Stable PASS.',
    'functionalIntegrationVerification': 'Only the same-commit runtime/provenance/target evidence aggregator may evaluate functional integration.',
    'upstreamStatus': up.get('status'),
    'upstreamReleaseVersion': up.get('releaseVersion'),
    'upstreamReleaseTag': up.get('releaseTag'),
    'upstreamReleaseCommitSha': up.get('tagCommitSha'),
    'upstreamAdapterReleaseAssetVersion': adapter.get('releaseAssetVersion'),
    'upstreamAdapterBinaryVersion': adapter.get('adapterVersion'),
    'upstreamProtocolVersion': adapter.get('pmAdapterProtocolVersion'),
    'provisioned': bool(pinned),
    'blockedReason': 'upstream release entry incomplete or unpinned' if (not pinned and ok) else up.get('blockedReason'),
    'checks': [{'name': n, 'ok': o} for n, o in checks],
    'note': 'STATIC contract + release-pin only; never a functional-integration claim. Real tag identity, signed-index signature and artifact integrity: scripts/verify_rill_release.py. Real adapter runtime and PM Core roundtrip: pm-rill-runtime / pm-core-rill-roundtrip jobs. A blocked upstream is never a Rill PASS.'
}
out=ROOT/'docs/rill-integration-status.json'
out.write_text(json.dumps(status, ensure_ascii=False, indent=2) + chr(10))
print('rill-contract (static): %d/%d checks passed; staticContractVerdict=%s releasePinStructureVerdict=%s functionalIntegrationVerdict=NOT_EVALUATED' % (
    sum(1 for _,ok in checks if ok), len(checks), static_contract, release_pin_structure))
if not ok: sys.exit(1)
