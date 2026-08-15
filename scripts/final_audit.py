#!/usr/bin/env python3
"""Self-contained final audit orchestrator.

Every upstream gate is rerun here in a fixed order and the fresh outputs are
consumed; stale report files are never trusted. Running this script alone
produces the same verdict as `make audit`, and `make audit` is exactly this.
"""
from __future__ import annotations
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
version=(ROOT/'VERSION').read_text().strip()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def present(cmd): return shutil.which(cmd) is not None
def run(cmd):
    return subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

steps=[]
def step(name,cmd):
    cp=run(cmd)
    steps.append({'name':name,'status':'pass' if cp.returncode==0 else 'fail','outputTail':cp.stdout[-4000:]})
    return cp

def run_unittest():
    cp=run([sys.executable,'-m','unittest','discover','-s','tests','-v'])
    m=re.search(r'Ran (\d+) tests?',cp.stdout)
    return {'status':'pass' if cp.returncode==0 else 'fail','count':int(m.group(1)) if m else None,'outputTail':cp.stdout[-4000:]}

tests=run_unittest()
step('contract-validation',[sys.executable,'scripts/validate_contracts.py'])
step('host-syntax',[sys.executable,'scripts/host_syntax_check.py'])
step('source-gates',[sys.executable,'scripts/source_gates.py'])
step('rill-contract',[sys.executable,'scripts/rill_contract_check.py'])
step('resource-budget',[sys.executable,'scripts/resource_budget.py','--source-tree','.'])

host=json.loads((ROOT/'docs/HOST_SYNTAX_REPORT.json').read_text())
source=json.loads((ROOT/'docs/SOURCE_GATES.json').read_text())
resource=json.loads((ROOT/'docs/RESOURCE_BUDGET.json').read_text())
packages={}
for name in ['performance-manager','luci-app-performance-manager','performance-manager-rill']:
    p=ROOT/'package'/name; files=[x for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts]
    packages[name]={'files':len(files),'bytes':sum(x.stat().st_size for x in files),'makefileSha256':sha(p/'Makefile')}
required=[s for s in steps if s['status']!='pass']
local_pass=len(required)==0 and host.get('errorCount')==0 and source.get('allPassed') is True and tests['status']=='pass'
external=[
 {'gate':'OpenWrt 25.12.x x86_64 SDK build: PM Core/LuCI/integration packages','status':'pending-external-ci-or-target'},
 {'gate':'PM <-> pinned upstream Rill release integration gate','status':'pending-external-ci-or-target'},
 {'gate':'Core-alone ucode compile/start on booted OpenWrt','status':'pending-external-target'},
 {'gate':'Hyper-V + KVM TargetRef/hotplug/replay/rollback','status':'pending-external-target'},
 {'gate':'LAN -> Router -> WAN and router-local controlled A/B','status':'pending-explicit-testbed'},
 {'gate':'sysupgrade + 24h resource/flash-write soak','status':'pending-external-target'},
]
report={
 'project':'OpenWrt Performance Manager','version':version,'planningBaseline':'v0.3.2 Contract Freeze',
 'auditSemantics':'Single orchestrator; every gate (contract validation, host syntax, source gates, resource budget, unittest suite) is rerun in this process and the fresh report files are consumed. They are not target-runtime evidence. Rill is an EXTERNAL runtime dependency: this repository never compiles or natively tests Rill; the referenced upstream Rill release and its contract are verified separately by the PM CI integration gate.',
 'orchestrationSteps':steps,
 'sourceCompletion':{'phase0Through12':'pass' if source.get('allPassed') else 'fail','localAudit':'pass' if local_pass else 'fail','packageCount':3,'frozenUbusContractMethods':18,'additionalRootAdminMethods':['cleanup']},
 'localEvidence':{'unitAndContractTests':tests,'hostSyntaxChecks':{'status':'pass' if host.get('errorCount')==0 else 'fail','count':len(host.get('checks',[]))},'sourceGates':source,'resourceBudgetGenerated':True},
 'toolchainAvailability':{'cargo':present('cargo'),'rustc':present('rustc'),'ucode':present('ucode')},
 'stableReleaseExternalGates':external,'targetEvidenceScripts':['scripts/openwrt-target-gate.sh','scripts/openwrt-sysupgrade-gate.sh','scripts/openwrt-resource-soak.sh'],'packages':packages,'resourceBudget':resource,
 'releaseDecision': (f'{version} source-complete release candidate; Stable remains blocked only by explicit external target/testbed gates' if local_pass else f'{version} local/source audit FAILED'),
 'criticalSafetyProperties':['Core is independent from LuCI/Rill','direct apply allowlist remains safe Hyper-V ring floor only','Native Packet Steering is observed/respected, not seized','commit-confirm has an armed monotonic deadline plus durable pending marker','same-boot crash fails closed to verified rollback; cross-boot never replays stale runtime snapshot','controlled A/B validates exact Companion methodology+context and restores candidate before reward','benchmark experiments are exclusive under a tuning-domain lock with idle-expiry recovery','Rill is an external advisory runtime driven through a shadow-only IPC protocol with capability gating and fail-closed on missing/incompatible runtime','Assisted Auto is double opt-in, maintenance/traffic/health gated, safe-allowlist only','uninstall cleanup is fail-closed: removal aborts unless the daemon confirms ownership-safe cleanup']
}
(ROOT/'docs/FINAL_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
phase_lines='\n'.join(f"- Phase {n}: **{g['status'].upper()}** — {g['name']}" for n,g in source['phases'].items())
md=f'''# Final Audit — {version}\n\n## Decision\n\n**{'PASS' if local_pass else 'FAIL'} — {report['releaseDecision']}.**\n\nThis audit is a single self-contained orchestrator: contract validation, host syntax checks, source gates, resource budget and the unittest suite are all rerun in this process, and only the freshly generated reports are consumed. Source completion is deliberately separated from real target evidence.\n\n## Orchestrated gates\n\n{''.join(f"- {s['name']}: **{s['status'].upper()}**\n" for s in steps)}\n\n## Local evidence\n\n- Executable unit/contract tests: **{tests['count']}**, status **{tests['status'].upper()}**.\n- Host syntax/JSON/JS/YAML checks: **{len(host.get('checks',[]))}**, status **{'PASS' if host.get('errorCount')==0 else 'FAIL'}**.\n- Formal schemas/examples and frozen profiles: validated by `scripts/validate_contracts.py`.\n- zh_Hans: all current literal LuCI msgids are covered.\n- Resource budget: generated; target-only RSS/CPU/writes/day/boot-time values remain explicitly unmeasured until a real OpenWrt VM is used.\n\n## Source phase gates\n\n{phase_lines}\n\n## Rill integration (external runtime)\n\nRill is an external runtime dependency owned, built and released by its upstream repository. This repository does not compile or natively test Rill. The PM CI `rill-contract` gate verifies the pinned upstream Rill release (provenance/checksum) and the PM<->Rill protocol/capability contract; a missing runtime, unreachable service or protocol-major mismatch is fail-closed and reported as Rill unavailable/incompatible, never silently assumed healthy.\n\n## Closed strict-audit blockers\n\n- Transaction Schema now covers the full frozen state machine and runtime-shaped null/awaiting-confirm states.\n- Persistence, Lock, Health, Benchmark Session and Companion Measurement contracts are formal schemas shipped with Core.\n- Commit-confirm now arms a real monotonic deadline and timer.\n- Active transaction state has a durable pending marker; same-boot daemon crash rolls back, while cross-boot recovery clears stale runtime intent without replay.\n- Health Guard includes baseline-relative LAN/WAN/DNS/IPv4/IPv6/proxy/VPN/route, load, steal, OOM, thermal and writable-state checks.\n- Route identity is based on `ip -j` default-route/rule evidence and rtnetlink route/link events; multi-WAN candidates are represented explicitly.\n- Runtime Topology conforms to the formal schema (string `lanInterface`), and paths resolve a real underlay NIC chain (VLAN/bridge/PPPoE/tunnel/radio) to a stable target.\n- Multi-WAN/PBR Path inventory is built from netifd/runtime route/rule evidence, not `wan[0-9]+` naming guesses.\n- Workload Class is derived from affected/evaluation path evidence (all seven frozen classes), never hard-coded to `plain_forwarding`.\n- Conservative automation carries real safety semantics: safe-allowlist-only auto-apply, never seizes preexisting, observe/respect packet steering, transactional ownership-backed writes, Rill advisory-only.\n- Controlled A/B freezes a canonical measurement methodology (host/port/direction/streams/duration/protocol/tool version); any control/candidate mismatch is rejected (`validated=false`, no reward, no Rill outcome).\n- Benchmark context includes a live nft ruleset fingerprint and route/rule identity; live-only control/candidate drift invalidates the experiment.\n- Policy replay cedes on live drift: if the value PM owns has changed, ownership is relinquished and the user/external value is not overwritten.\n- Assisted Auto gates on the selected action's own target traffic before applying, and remains safe-allowlist only.\n- Uninstall cleanup is fail-closed: package removal aborts unless the daemon confirms an ownership-safe cleanup; upgrades and staged roots are untouched.\n'''
(ROOT/'docs/FINAL_AUDIT.md').write_text(md)
print(json.dumps({'version':version,'localPass':local_pass,'testCount':tests['count'],'sourceGatesPassed':source.get('allPassed'),'decision':report['releaseDecision']},ensure_ascii=False,indent=2))
if not local_pass: sys.exit(1)
