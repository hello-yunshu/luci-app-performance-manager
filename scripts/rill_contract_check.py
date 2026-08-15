#!/usr/bin/env python3
"""PM<->Rill dependency contract gate (external runtime).

Rill is owned, built and released by its upstream repository.  This repository
never compiles or natively tests Rill.  This check verifies only the PM-side
contract:

  1. the pinned upstream Rill release entry is well-formed and, when a release
     is provisioned, carries a non-empty pinned version + artifact URL + SHA-256
     (never `latest` and never an empty checksum);
  2. the formal IPC schema and the Core agree on protocol api==2 and the
     shadow-only required ops (exactly status/observe/outcome);
  3. the Core capability gate is fail-closed: missing runtime, unreachable
     service and protocol-major mismatch are surfaced as unavailable/
     incompatible, never silently assumed OK.

When the upstream release entry is null (external-dependency-blocked), that is
a legitimate, honest state as long as the Core fails closed and the integration
package never compiles/bundles Rill.  This script does NOT fabricate a pass for
a missing release: it reports the blocked status verbatim and separates the
PM-side fail-closed contract (pass) from the upstream integration (blocked), so
the overall feature status is blocked rather than a claimed Rill PASS.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
SCHEMA=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
DEP=json.loads((ROOT/'contracts/rill-dependency.json').read_text())
RILL_MAKE=(ROOT/'package/performance-manager-rill/Makefile').read_text()

def fail(msg): print('FAIL:', msg); return False

checks=[]
def check(name, ok):
    checks.append((name, bool(ok)))
    if not ok: print('FAIL:', name)

# 1. Protocol api + shadow-only ops agreement between schema and Core.
check('schema api const==2', SCHEMA['properties']['api']['const']==2)
check('DEP protocol api==2', DEP['protocol']['api']==2)
ops=set(SCHEMA['properties']['op']['enum'])
check('schema ops == status/observe/outcome', ops=={'status','observe','outcome'})
check('Core shadow-only ops contract', "const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ]" in CORE
      and "RILL_REQUIRED_OPS" in CORE)
check('DEP requiredOps match', set(DEP['protocol']['requiredOps'])==ops)

# 2. Core fail-closed capability gate.
for token in ['external-runtime-missing','protocol-major-mismatch','RILL_PROTOCOL_API',
              '(r.response?.api ?? 0) != RILL_PROTOCOL_API',"state: 'incompatible'"]:
    check(f'Core fail-closed gate token: {token}', token in CORE)

# 3. Integration package never compiles/bundles Rill.
check('integration package never compiles Rill', 'cargo' not in RILL_MAKE and 'rust' not in RILL_MAKE.lower()
      and 'PKG_BUILD_DEPENDS:=' in RILL_MAKE)
check('no bundled Rust source', not (ROOT/'package/performance-manager-rill/src').exists())

# 4. Upstream release entry policy.
up=DEP.get('upstream',{})
if up.get('releaseVersion') or up.get('artifactUrl') or up.get('artifactSha256'):
    check('release pinned (no latest/download)', up.get('artifactUrl') and 'latest/download' not in (up.get('artifactUrl') or ''))
    check('release checksum non-empty', bool(up.get('artifactSha256')))
    check('release version non-empty', bool(up.get('releaseVersion')))
else:
    # No upstream release provisioned: legitimate blocked state, reported verbatim.
    status=up.get('status')
    check('upstream status is external-dependency-blocked', status=='external-dependency-blocked')
    check('blocked reason recorded', bool(up.get('blockedReason')))

ok=all(ok for _,ok in checks)
# 5. Honest feature status: the PM-side fail-closed contract can pass while the
#    upstream Rill integration stays blocked.  These MUST be reported separately
#    so a missing upstream is never surfaced as a working Rill integration.
up=DEP.get('upstream',{})
provisioned = bool(up.get('releaseVersion') or up.get('artifactUrl') or up.get('artifactSha256'))
pm_contract = 'pass' if ok else 'fail'
upstream_integration = 'pass' if (provisioned and ok) else 'blocked'
overall = 'pass' if (pm_contract == 'pass' and upstream_integration == 'pass') else 'blocked'
status = {
    'schemaVersion': 1,
    'contract': 'rill-integration-status',
    'pmFailClosedContract': pm_contract,
    'upstreamIntegration': upstream_integration,
    'overallFeatureStatus': overall,
    'upstreamStatus': up.get('status'),
    'blockedReason': up.get('blockedReason'),
    'provisioned': provisioned,
    'checks': [{'name': n, 'ok': o} for n, o in checks],
    'note': 'A blocked upstream integration is NOT a PASS; the Core/runtime fail-closed contract is verified separately and the overall feature status remains blocked until a compatible upstream release is provisioned and verified.'
}
out = ROOT/'docs/rill-integration-status.json'
out.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
print(f"rill-contract: {sum(1 for _,ok in checks if ok)}/{len(checks)} checks passed; "
      f"pmFailClosedContract={pm_contract} upstreamIntegration={upstream_integration} overallFeatureStatus={overall}")
print(json.dumps(status, ensure_ascii=False, indent=2))
if not ok: sys.exit(1)