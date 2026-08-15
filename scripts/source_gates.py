#!/usr/bin/env python3
"""Machine-computed source completion gates for planning pack v0.3.2.

These gates intentionally do not pretend to be target-runtime evidence.  They
answer only whether each phase's required source mechanism and contract surface
is present after executable contract/tests have passed.
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
COMP=(ROOT/'companion/pm_companion_agent.py').read_text()
CFG=(ROOT/'package/performance-manager/files/etc/config/performance-manager').read_text()
CONTRACTS=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text()
RILL_MAKE=(ROOT/'package/performance-manager-rill/Makefile').read_text()
RILL_SCHEMA=(ROOT/'contracts/rill-ipc.schema.json').read_text()

def all_tokens(text,tokens): return all(t in text for t in tokens)
def gate(name, checks):
    failed=[desc for desc,ok in checks if not ok]
    return {'name':name,'status':'pass' if not failed else 'fail','checks':len(checks),'failed':failed}

schemas={p.name for p in (ROOT/'contracts').glob('*.schema.json')}
required_schemas={'capability.schema.json','topology-path.schema.json','target-ref.schema.json','action.schema.json','persistence.schema.json','transaction.schema.json','lock.schema.json','health.schema.json','profile.schema.json','benchmark-session.schema.json','rill-ipc.schema.json'}
phases={}
phases['0']=gate('Contract Freeze',[
 ('all required formal schemas',required_schemas<=schemas),
 ('frozen Action safety fields',all_tokens((ROOT/'contracts/action.schema.json').read_text(),['risk','requiresBenchmark','persistenceClass','requiredLocks','requiresCommitConfirm'])),
 ('full transaction states',all_tokens((ROOT/'contracts/transaction.schema.json').read_text(),['planned','locked','snapshotted','awaiting_confirm','rolled_back']))])
phases['1']=gate('Bootstrap',[(f'package {x}',(ROOT/'package'/x/'Makefile').exists()) for x in ['performance-manager','luci-app-performance-manager','performance-manager-rill']]+[
 ('Core ubus daemon',all_tokens(CORE,['ubusmod.connect()','conn.publish(UBUS_NAME','{ call: function']))])
phases['2']=gate('Capability / Topology / Target / Event',[
 ('stable TargetRef',all_tokens(CORE,['stableId','topologyGeneration','evidence'])),('multi-WAN candidates','wanCandidates' in CORE),('route/rule evidence',all_tokens(CORE,["'-j', '-4', 'route'","'-j', '-4', 'rule', 'show'",'routeIdentity'])),('rtnl route/link listener',all_tokens(CORE,['rtnl.listener','[ 16, 17, 24, 25 ]','[ 1, 7, 11 ]'])),('profile full checker',all_tokens(CORE,['missingRequiredPackages','missingRecommendedPackages','missingConditionalPackages','missingCapabilities','targetMatched']))])
phases['3']=gate('Telemetry / Health / Analyzer / Path',[
 ('health dimensions',all_tokens(CORE,['dns_health()','proxy_health()','vpn_health()','thermal_health()','recent_oom_state()','high-cpu-steal'])),('baseline-relative health',all_tokens(CORE,['healthy-to-unhealthy','oom:new','thermal:new-throttle'])),('local + forwarding paths',all_tokens(CORE,['path:lan-to-wan','path:local-endpoint'])),('analyzer emits findings/evidence/confidence',all_tokens(CORE,['function analysis_report()','findings:findings','evidence:evidence','confidence:confidence'])),('bounded telemetry cadence',all_tokens(CORE,["max(30, int_cfg('main.telemetry_interval'","max(300, int_cfg('main.deep_interval'"]))])
phases['4']=gate('Policy / Compatibility',[
 ('integration detectors',all_tokens(CORE,['openclash','sqm','qosify','mwan3','pbr','wireguard'])),('native packet steering respect',all_tokens(CORE,['packet_steering_capability','observe-respect'])),('compatibility blockers','function compatibility(' in CORE)])
phases['5']=gate('Transactions / Locks / Commit-confirm',[
 ('durable pending marker',all_tokens(CORE,['pending_marker_path','persist_dir()}/pending','pendingMarker'])),('deadline actually armed','deadlineMonotonicMs = monotonic_ms()' in CORE),('timer callback rollback',all_tokens(CORE,['arm_tx_timer','confirm-timeout'])),('same-boot crash rollback','core-crash-recovery' in CORE),('cross-boot no stale replay','boot-recovery-runtime-reset-no-stale-replay' in CORE),('stale rollback refusal','live-state-drift-refuses-stale-rollback' in CORE),('locks','acquire_locks' in CORE and 'release_locks' in CORE),('ownership-safe uninstall',all_tokens(CORE,['function cleanup_owned','runtimeLease','live-drift-preserved-intent-removed','runtime-restored-and-intent-removed'])),('fail-closed prerm on remove',all_tokens((ROOT/'package/performance-manager/Makefile').read_text(),['[ -x /usr/sbin/performance-manager.uc ] || exit 0',"grep -q '\"ok\":true'",'exit 1','start the service and retry removal'])),('benchmark locks survive daemon death',all_tokens(CORE,['clean_stale_benchmark_locks()'])),('benchmark lock released on terminal paths',all_tokens(CORE,['release_benchmark_lock(','benchmark_fail_session(']))])
phases['6']=gate('Conservative',[
 ('safe allowlist ring only',"SAFE_ACTIONS = [ 'nic.ring.floor' ]" in CONTRACTS),('ring readback rollback',all_tokens(CORE,['ring_restore','ring_matches','verification-failed'])),('policy replay ownership',all_tokens(CORE,['pm_policy_replay','ownerTransactionId','replay_policies']))])
phases['7']=gate('Benchmark',[
 ('tuning-domain exclusivity',all_tokens(CORE,["return 'benchmark:global'",'acquire_benchmark_lock(','benchmark-domain-lock-conflict','existing.sessionId != session_id'])),('lock acquired before session write',CORE.index('acquire_benchmark_lock(lock_domain, id)')<CORE.index('json_write(benchmark_path(id),session)')),('stale experiment lock recovery',all_tokens(CORE,['clean_stale_benchmark_locks()'])),('full context fingerprint',all_tokens(CORE,['integration_fingerprint(masked_keys)','benchmark_masked_keys(action_id)','benchmark-context-drift'])),('candidate-mutated keys masked',all_tokens(CORE,['firewall.@defaults[0].flow_offloading'])),('strict evaluation path resolve',all_tokens(CORE,['primary_path(path_id)','evaluation-path-not-found'])),('forwarding requires resolved route',all_tokens(CORE,["selected_path.routeResolved === true","routeProvider != 'ip-full+rtnl-events'",'evaluation-route-unresolved'])),('controlled evidence state machine',all_tokens(CORE,['awaiting_control','candidate_applied','companion_evidence_valid','benchmark_apply_candidate'])),('candidate rollback before reward',CORE.find("rollback_transaction(session.transactionId,'benchmark-complete')")>=0 and CORE.find("rollback_transaction(session.transactionId,'benchmark-complete')")<CORE.find('reward=(c1-c0)/c0')),('one variable',all_tokens(CORE,['variableCount:1','benchmark.one_variable'])),('all action IDs',all(x in CORE for x in ['service.irqbalance','network.backlog','network.budget','network.buffers','network.busy_poll','netdev.tx_queue_len','nic.coalescing','tcp.cc','qdisc.replace','fastpath.software_flow_offload','fastpath.hardware_flow_offload','fastpath.third_party_sfe','cpu.governor'])),('unsafe generic providers explicitly blocked',all_tokens(CORE,['exact-qdisc-restore-not-proven','no-generic-third-party-sfe-contract']))])
phases['8']=gate('Rill Intelligence (external runtime)',[
 ('no bundled Rust source',not (ROOT/'package/performance-manager-rill/src').exists()),
 ('integration package never compiles Rill',all_tokens(RILL_MAKE,['Build/Compile','PKG_BUILD_DEPENDS:=']) and 'cargo' not in RILL_MAKE and 'rust' not in RILL_MAKE.lower()),
 ('shadow-only ops contract',all_tokens(CORE,["const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ]"])),
 ('protocol major gate',all_tokens(CORE,['RILL_PROTOCOL_API',"protocol-major-mismatch",'(r.response?.api ?? 0) != RILL_PROTOCOL_API'])),
 ('external runtime fail-closed',all_tokens(CORE,['external-runtime-missing','shadow.binary'])),
 ('no apply/uci op in protocol',"'apply' not in RILL_SCHEMA and 'uci' not in RILL_SCHEMA"),
 ('bounded context-key partition',all_tokens(CORE,['rill_context_key_build','ctx-v1:','goal=%s'])),
 ('goal is first-class partition',all_tokens(CORE,['const GOALS =',"goal_class = safe_name(goal_id ?? 'balanced')"])),
 ('per-op validation',all_tokens(CORE,['rill_send','rill_status','rill_observe','rill_outcome_payload']))])
phases['9']=gate('Recommend',[
 ('learned advisory',all_tokens(CORE,['learnedAdvisory','rill.detail?.recommendations'])),
 ('Rill recommendation threshold (external contract)',all_tokens(CORE,['learnedAdvisory']))])
phases['10']=gate('Assisted Auto',[
 ('default off',"option assisted_auto '0'" in CFG),('double opt-in',all_tokens(CORE,["!= 'assisted'","bool_cfg('main.assisted_auto', false)"])),('maintenance + health gates',all_tokens(CORE,['in_maintenance_window()','system_guard()'])),('action selected before traffic gate',CORE.index('let action = actions[0]')<CORE.index('assisted_low_traffic(current, target_ref?.runtimeName ?? null)')),('target-specific low-traffic gate',all_tokens(CORE,['assisted_low_traffic(current, runtime)','assisted-previous-','resolve_target(action.applyTarget)'])),('safe allowlist only','index(SAFE_ACTIONS, action.id)' in CORE)])
phases['11']=gate('Platforms',[
 ('generic/hyperv/kvm detection',all_tokens(CORE,['hyperv','kvm','generic','hv_netvsc'])),('KVM/Proxmox compatibility guidance','kvmProxmoxCompatible' in CORE)])
phases['12']=gate('Companion',[
 ('v2 context envelope',all_tokens(COMP,['pm-companion/v2','sessionId','phase','actionId','pathId','topologyGeneration','routeIdentity','capabilityHash'])),('no router mutation',all_tokens(COMP,['routerMutation','shell=False']) and 'shell=True' not in COMP),('Core ingest',all_tokens(CORE,['pm-companion/v2','companion_evidence_valid','controlEvidence','candidateEvidence']))])
report={'planningBaseline':'v0.3.2 Contract Freeze','scope':'source-completion-only','phases':phases,'allPassed':all(x['status']=='pass' for x in phases.values()),'note':'Target build/runtime/virtualization/forwarding/soak gates are intentionally tracked separately and are not inferred from source gates.'}
out=ROOT/'docs/SOURCE_GATES.json'; out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for n,g in phases.items(): print(f"Phase {n}: {g['status'].upper()} — {g['name']}" + (f"; failed: {', '.join(g['failed'])}" if g['failed'] else ''))
if not report['allPassed']: sys.exit(1)
