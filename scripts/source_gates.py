#!/usr/bin/env python3
"""Machine-computed source completion gates for planning pack v0.3.2.

These gates intentionally do not pretend to be target-runtime evidence.  They
answer only whether each phase's required source mechanism and contract surface
is present after executable contract/tests have passed.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
COMP=(ROOT/'companion/pm_companion_agent.py').read_text()
CFG=(ROOT/'package/performance-manager/files/etc/config/performance-manager').read_text()
CONTRACTS=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text()
RILL_MAKE=(ROOT/'package/performance-manager-rill/Makefile').read_text()
RILL_SCHEMA=(ROOT/'contracts/rill-ipc.schema.json').read_text()
BUNDLE_MAKE=(ROOT/'package/luci-app-performance-manager-all/Makefile').read_text()

def all_tokens(text,tokens): return all(t in text for t in tokens)
def gate(name, checks):
    failed=[desc for desc,ok in checks if not ok]
    return {'name':name,'status':'pass' if not failed else 'fail','checks':len(checks),'failed':failed}

# ---- forbidden-API / repository-structure guards (structural, authoritative) --
# These are the ONLY places source_gates asserts an invariant. Everything else
# below is structural evidence (file/schema/wiring present) and never claims
# complex behavior is complete: that is the job of the real Core runtime harness
# (tools/docker-validate/harness) and the Remote OpenWrt build, not of source
# substring checks.
def forbidden_api_gates():
    # Enumerate the repository's own files.  In CI the workspace also contains
    # the downloaded OpenWrt SDK tree as a subdirectory, whose feed packages
    # legitimately include Rust/Cargo files; those must NOT count as this
    # repository reintroducing a Rust toolchain, so scan git-tracked files
    # (the SDK is untracked) rather than every file on disk.
    try:
        out = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, text=True)
        repo_files = [ROOT / p for p in out.stdout.split('\0') if p]
    except Exception:
        repo_files = [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts]
    rill_make = (ROOT/'package/performance-manager-rill/Makefile').read_text()
    legacy = [p for p in repo_files if p.exists() and 'performance-manager-rill-adapter' in p.as_posix()]
    workflow_files = sorted((ROOT/'.github/workflows').glob('*.yml'))
    mutable_actions = []
    for workflow in workflow_files:
        for line_no, line in enumerate(workflow.read_text().splitlines(), 1):
            match = re.search(r'\buses:\s*([^\s#]+)', line)
            if match and not match.group(1).startswith('./') and not re.search(r'@[A-Za-z0-9._/-]+$', match.group(1)):
                mutable_actions.append(f'{workflow.name}:{line_no}:{match.group(1)}')
    return [
      ('retired private adapter has no tracked files', not legacy),
      ('integration Makefile consumes external Runtime', 'Build/Compile' in rill_make and '+rill-runtime' in rill_make and 'cargo' not in rill_make and 'rust' not in rill_make.lower()),
      ('v3 Runtime contract gate is wired', 'check_rill_dependency.py' in ''.join(p.read_text() for p in workflow_files if p.is_file())),
      ('all third-party Actions use readable refs', not mutable_actions),
    ]

schemas={p.name for p in (ROOT/'contracts').glob('*.schema.json')}
required_schemas={'capability.schema.json','topology-path.schema.json','target-ref.schema.json','action.schema.json','persistence.schema.json','transaction.schema.json','lock.schema.json','health.schema.json','profile.schema.json','benchmark-session.schema.json','rill-ipc.schema.json'}
phases={}
phases['0']=gate('Contract Freeze',[
 ('all required formal schemas',required_schemas<=schemas),
 ('frozen Action safety fields',all_tokens((ROOT/'contracts/action.schema.json').read_text(),['risk','requiresBenchmark','persistenceClass','requiredLocks','requiresCommitConfirm'])),
 ('full transaction states',all_tokens((ROOT/'contracts/transaction.schema.json').read_text(),['planned','locked','snapshotted','awaiting_confirm','rolled_back']))])
phases['0'].update({'evidence':'structural: schema files + frozen contract fields present'})
phases['1']=gate('Bootstrap',[(f'package {x}',(ROOT/'package'/x/'Makefile').exists()) for x in ['performance-manager','luci-app-performance-manager','performance-manager-rill','luci-app-performance-manager-all']]+[
 ('Core ubus daemon wiring','ubusmod.connect()' in CORE and 'conn.publish' in CORE and '{ call: function' in CORE),
 ('full package is architecture-specific','PKGARCH:=all' not in BUNDLE_MAKE),
 ('full package embeds qualified Runtime','RILL_RUNTIME_BINARY' in BUNDLE_MAKE and '/usr/bin/rill-runtime' in BUNDLE_MAKE),
 ('full package has no Runtime dependency','+rill-runtime' not in BUNDLE_MAKE),
 ('full package conflicts with split owners',all_tokens(BUNDLE_MAKE,['CONFLICTS:=','performance-manager-rill','rill-runtime','luci-i18n-performance-manager-zh-cn'])),
 ('full package carries Rill keep rule','performance-manager-rill/files/lib/upgrade/keep.d/performance-manager-rill' in BUNDLE_MAKE)])
phases['1'].update({'evidence':'structural: package Makefiles + Core service wiring present'})
phases['2']=gate('Capability / Topology / Target / Event',[
 ('stable TargetRef functions defined',all_tokens(CORE,['function stable_target(','function target_refs(','topology_generation'])),
 ('multi-WAN evidence function defined',all_tokens(CORE,['function wan_candidates_evidence(','wanCandidates'])),
 ('route/rule evidence commands wired',all_tokens(CORE,["'-j', '-4', 'route'","'-j', '-4', 'rule', 'show'",'routeIdentity'])),
 ('rtnl listener wired',all_tokens(CORE,['rtnl.listener','[ 16, 17, 24, 25 ]','[ 1, 7, 11 ]'])),
 ('profile checker wiring',all_tokens(CORE,['missingRequiredPackages','missingRecommendedPackages','missingConditionalPackages','missingCapabilities','targetMatched']))])
phases['2'].update({'evidence':'structural: functions/commands present; real Multi-WAN/underlay behavior is verified by the real Core runtime harness (harness [1]-[3])'})
phases['3']=gate('Telemetry / Health / Analyzer / Path',[
 ('health dimension functions defined',all_tokens(CORE,['function dns_health(','function proxy_health(','function vpn_health(','function thermal_health(','function recent_oom_state('])),('baseline-relative health markers',all_tokens(CORE,['healthy-to-unhealthy','oom:new','thermal:new-throttle'])),('local + forwarding path ids present',all_tokens(CORE,['path:lan-to-wan','path:local-endpoint'])),('analyzer function defined',all_tokens(CORE,['function analysis_report(','findings:findings','evidence:evidence','confidence:confidence'])),('bounded telemetry cadence',all_tokens(CORE,["max(30, int_cfg('main.telemetry_interval'","max(300, int_cfg('main.deep_interval'"]))])
phases['3'].update({'evidence':'structural: analyzer/health functions present'})
phases['4']=gate('Policy / Compatibility',[
 ('integration detectors present',all_tokens(CORE,['openclash','sqm','qosify','mwan3','pbr','wireguard'])),('packet steering respect wiring',all_tokens(CORE,['packet_steering_capability','observe-respect'])),('compatibility function defined','function compatibility(' in CORE)])
phases['4'].update({'evidence':'structural: detectors + compatibility function present'})
phases['5']=gate('Transactions / Locks / Commit-confirm',[
 ('durable pending marker wiring',all_tokens(CORE,['pending_marker_path','pendingMarker'])),('deadline armed','deadlineMonotonicMs = monotonic_ms()' in CORE),('commit-confirm timer wiring',all_tokens(CORE,['arm_tx_timer','confirm-timeout'])),('same-boot crash rollback marker','core-crash-recovery' in CORE),('cross-boot no stale replay marker','boot-recovery-runtime-reset-no-stale-replay' in CORE),('stale rollback refusal marker','live-state-drift-refuses-stale-rollback' in CORE),('lock functions defined',all_tokens(CORE,['function acquire_locks','function release_locks'])),('ownership-safe cleanup wiring',all_tokens(CORE,['function cleanup_owned','runtimeLease','live-drift-preserved-intent-removed','runtime-restored-and-intent-removed'])),('fail-closed prerm on remove',all_tokens((ROOT/'package/performance-manager/Makefile').read_text(),['[ -x /usr/sbin/performance-manager.uc ] || exit 0',"grep -q '\"ok\":true'",'exit 1','start the service and retry removal'])),('stale benchmark lock recovery wiring',all_tokens(CORE,['function clean_stale_benchmark_locks('])),('benchmark lock release wiring',all_tokens(CORE,['release_benchmark_lock(','benchmark_fail_session(']))])
phases['5'].update({'evidence':'structural: transaction/lock/cleanup wiring present; real transaction semantics are exercised by the runtime harness and uninstall/migration gates'})
phases['6']=gate('Conservative',[
 ('safe allowlist ring declared',"SAFE_ACTIONS = [ 'nic.ring.floor' ]" in CONTRACTS),('ring readback/rollback wiring',all_tokens(CORE,['ring_restore','ring_matches','verification-failed'])),('policy replay ownership wiring',all_tokens(CORE,['pm_policy_replay','ownerTransactionId','replay_policies'])),('conservative auto-tick defined','function conservative_auto_tick(' in CORE)])
phases['6'].update({'evidence':'structural: allowlist + tick wiring present; real Conservative semantics are verified by the runtime harness [6]'})
phases['7']=gate('Benchmark',[
 ('tuning-domain exclusivity wiring',all_tokens(CORE,["return 'benchmark:global'",'acquire_benchmark_lock(','benchmark-domain-lock-conflict'])),('lock acquired before session write',CORE.index('acquire_benchmark_lock(lock_domain, id)')<CORE.index('json_write(benchmark_path(id),session)')),('stale experiment lock recovery',all_tokens(CORE,['function clean_stale_benchmark_locks('])),('full context fingerprint wiring',all_tokens(CORE,['integration_fingerprint(masked_keys,','benchmark_masked_keys(action_id)','benchmark-context-drift'])),('candidate-mutated keys masked',all_tokens(CORE,['firewall.@defaults[0].flow_offloading'])),('strict evaluation path resolve',all_tokens(CORE,['function primary_path(','evaluation-path-not-found'])),('forwarding requires resolved route',all_tokens(CORE,["selected_path.routeResolved === true",'evaluation-route-unresolved'])),('controlled evidence state machine wiring',all_tokens(CORE,['awaiting_control','candidate_applied','companion_evidence_valid','benchmark_apply_candidate'])),('candidate rollback before reward',CORE.find("rollback_transaction(session.transactionId,'benchmark-complete')")>=0 and CORE.find("rollback_transaction(session.transactionId,'benchmark-complete')")<CORE.find('build_reward(')),('one variable',all_tokens(CORE,['variableCount:1','benchmark.one_variable'])),('all action IDs present',all(x in CORE for x in ['service.irqbalance','network.backlog','network.budget','network.buffers','network.busy_poll','netdev.tx_queue_len','nic.coalescing','tcp.cc','qdisc.replace','fastpath.software_flow_offload','fastpath.hardware_flow_offload','fastpath.third_party_sfe','cpu.governor'])),('unsafe generic providers explicitly blocked',all_tokens(CORE,['exact-qdisc-restore-not-proven','no-generic-third-party-sfe-contract']))])
phases['7'].update({'evidence':'structural: state machine + fingerprint wiring present; methodology-mismatch and nft candidate-mask behavior are verified by the runtime harness [4]-[5]'})
phases['8']=gate('Rill Intelligence (external runtime)',[
 ('no PM-owned adapter source',not any('performance-manager-rill-adapter' in p.as_posix() for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts and 'target' not in p.parts)),
 ('integration package consumes generic Runtime',all_tokens(RILL_MAKE,['Build/Compile','+rill-runtime','/usr/bin/rill-runtime']) and 'cargo' not in RILL_MAKE and 'rust' not in RILL_MAKE.lower()),
 ('v3 protocol gate wiring',all_tokens(CORE,['const RILL_RUNTIME_API_VERSION = 3','RILL_RUNTIME_CAPABILITIES','preview-serve','runtime-version-mismatch'])),
 ('external runtime fail-closed wiring',all_tokens(CORE,['binary-invalid','rill_binary_path','external-runtime-not-provisioned'])),
 ('no apply/uci op in protocol',"'apply' not in RILL_SCHEMA and 'uci' not in RILL_SCHEMA"),
 ('bounded context-key partition wiring',all_tokens(CORE,['rill_context_key_build','ctx-v1:','goal=%s'])),
 ('goal is first-class partition wiring',all_tokens(CORE,['const GOALS =',"goal_class = safe_name(goal_id ?? 'balanced')"])),
 ('per-op send/status/observe/outcome wiring',all_tokens(CORE,['rill_send','rill_status','rill_observe','rill_report_outcome'])),
 ('exact decision lifecycle wiring',all_tokens(CORE,['rill_binding_reserve','rill_execution_mark_mutation_started','rill_prepare_outcome','mayHaveReachedPeer','schedule_rill_outcome_retry'])),
 ('telemetry does not observe', 'rill_observe()' not in CORE[CORE.index('function schedule_telemetry('):CORE.index('function reply(')])])
phases['8'].update({'evidence':'structural only: PM consumes the exact external Runtime contract and fail-closed v3 client. Functional status belongs exclusively to the real Runtime integration job.'})
phases['9']=gate('Recommend',[
 ('learned advisory wiring',all_tokens(CORE,['learnedAdvisory','rill_advisory_get']))])
phases['9'].update({'evidence':'structural: advisory wiring present; generate-advice behavior is gated by Rill availability (fail-closed when external runtime blocked).'})
phases['10']=gate('Assisted Auto',[
 ('default off',"option assisted_auto '0'" in CFG),('double opt-in',all_tokens(CORE,["!= 'assisted'","bool_cfg('main.assisted_auto', false)"])),('maintenance + health gates wiring',all_tokens(CORE,['in_maintenance_window()','system_guard()'])),('unified smart selector before traffic gate',CORE.index("select_smart_action('assisted', actions, context)")<CORE.index('assisted_low_traffic(current, target_ref?.runtimeName ?? null)')),('target-specific low-traffic gate wiring',all_tokens(CORE,['assisted_low_traffic(current, runtime)','assisted-previous-','resolve_target(action.applyTarget)'])),('safe allowlist only','index(SAFE_ACTIONS, action.id)' in CORE)])
phases['10'].update({'evidence':'structural: opt-in + traffic-gate wiring present'})
phases['11']=gate('Platforms',[
 ('generic/hyperv/kvm detection',all_tokens(CORE,['hyperv','kvm','generic','hv_netvsc'])),('KVM/Proxmox compatibility guidance','kvmProxmoxCompatible' in CORE)])
phases['11'].update({'evidence':'structural: platform detection present; real target hotplug/forwarding is target-only evidence'})
phases['12']=gate('Companion',[
 ('v2 context envelope wiring',all_tokens(COMP,['pm-companion/v2','sessionId','phase','actionId','pathId','topologyGeneration','routeIdentity','capabilityHash'])),('no router mutation',all_tokens(COMP,['routerMutation','shell=False']) and 'shell=True' not in COMP),('Core ingest wiring',all_tokens(CORE,['pm-companion/v2','companion_evidence_valid','controlEvidence','candidateEvidence']))])
phases['12'].update({'evidence':'structural: companion envelope + ingest wiring present'})
for n in phases:
    phases[n]['verificationLayer']='structural-source'
report={'planningBaseline':'external Rill Runtime v3 migration','scope':'structural-source-only','forbiddenApi':forbidden_api_gates(),'phases':phases,'allPassed':all(x['status']=='pass' for x in phases.values()) and all(ok for _,ok in forbidden_api_gates()),'note':'These gates are STRUCTURAL evidence only: file/schema/function-wiring presence plus ownership/tooling policy guards. They do NOT prove complex behavior is correct. Real behavior is verified by the generic Runtime v3 subprocess integration, LuCI render smoke, Remote OpenWrt SDK build, and exact APK metadata validation. Target build/runtime/virtualization/forwarding/soak gates are tracked separately.'}
out=ROOT/'docs/SOURCE_GATES.json'; out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for n,g in phases.items(): print(f"Phase {n}: {g['status'].upper()} — {g['name']}" + (f"; failed: {', '.join(g['failed'])}" if g['failed'] else ''))
print("Forbidden-API guards:", "PASS" if all(ok for _,ok in report['forbiddenApi']) else "FAIL", " — " + "; ".join(d for d,ok in report['forbiddenApi'] if not ok) or "no violations")
if not report['allPassed']: sys.exit(1)
