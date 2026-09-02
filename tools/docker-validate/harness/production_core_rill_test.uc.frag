/* Production Core -> real Runtime -> production selector/transaction gate.
 * This fragment is appended to the raw production Core library by
 * build-harness.py. It only replaces ambient providers (filesystem, topology,
 * target and mutation seams); selector, binding and transaction construction
 * remain the shipped Core implementation. The Runtime executable is real and
 * supplied by the CI job at /usr/bin/rill-runtime. */

let _production_failures = 0;
let _production_context = 'ctx-production-candidate-isolation';
let _production_a = { id: 'nic.ring.floor', applyTarget: 'NIC-A', evaluationPaths: [ 'WAN-A' ], affectedPaths: [ 'WAN-A' ], risk: 'safe', executionAuthority: 'safe-direct', available: true, params: { rxFloor: 1024 }, requiredLocks: [ 'netdev:NIC-A' ], applyScope: 'device', requiresCommitConfirm: false };
let _production_b = { id: 'nic.ring.floor', applyTarget: 'NIC-B', evaluationPaths: [ 'WAN-B' ], affectedPaths: [ 'WAN-B' ], risk: 'safe', executionAuthority: 'safe-direct', available: true, params: { rxFloor: 1024 }, requiredLocks: [ 'netdev:NIC-B' ], applyScope: 'device', requiresCommitConfirm: false };

function production_check(condition, label, detail) {
	if (condition) print('PASS  ' + label + '\n');
	else { _production_failures++; print('FAIL  ' + label + '  ' + (detail == null ? '' : sprintf('%.J', detail)) + '\n'); }
}

let _production_cfg = cfg;
cfg = function(key, fallback) {
	if (key == 'shadow.enabled') return '1';
	if (key == 'shadow.binary') return '/usr/bin/rill-runtime';
	if (key == 'shadow.state_file') return '/tmp/pm-production-runtime/runtime-state.json';
	if (key == 'main.persistent_dir') return '/tmp/pm-production';
	if (key == 'main.state_dir') return '/tmp/pm-production-state';
	if (key == 'main.profile') return 'recommended';
	if (key == 'main.goal') return 'balanced';
	return _production_cfg(key, fallback);
};

candidate_actions = function() { return [ _production_a, _production_b ]; };
target_refs = function() { return [
	{ stableId: 'NIC-A', runtimeName: 'eth-a', driver: 'fixture', targetRef: 'NIC-A' },
	{ stableId: 'NIC-B', runtimeName: 'eth-b', driver: 'fixture', targetRef: 'NIC-B' }
]; };
resolve_target = function(stable_id) { for (let ref in target_refs()) if (ref.stableId == stable_id) return ref; return null; };
primary_path = function(path_id) { return { id: path_id ?? 'path:lan-to-wan', routeIdentity: 'route-fixture', routeResolved: true, routeProvider: 'ip-full+rtnl-events', workloadClass: [ 'plain_forwarding' ], wanInterface: path_id == 'WAN-B' ? 'wan-b' : 'wan-a', targetRefs: [ path_id == 'WAN-B' ? 'NIC-B' : 'NIC-A' ], underlayChain: [ path_id == 'WAN-B' ? 'eth-b' : 'eth-a' ] }; };
rill_context_scope = function(paths) { return { pathId: 'path-scope-fixture', routeIdentity: 'route-fixture', rows: [ 'WAN-A|route-fixture', 'WAN-B|route-fixture' ] }; };
rill_context_key_build = function() { return _production_context; };
capabilities = function() { return { schemaVersion: 2, capabilities: [] }; };
topology = function() { return { schemaVersion: 1, topologyGeneration: 1, paths: [ primary_path('WAN-A'), primary_path('WAN-B') ] }; };
integration_state = function() { return { openclash: false, passwall: false, homeproxy: false, sqm: false, qosify: false, mwan3: false, pbr: false, transparentProxy: false }; };
integration_fingerprint = function() { return 'integration-fixture'; };
telemetry_snapshot = function() { return { monotonicMs: monotonic_ms(), bootId: boot_id(), topologyGeneration: 1, trafficUtilization: 0, ppsPressure: 0, dropErrorPressure: 0, cpuBusyInterval: 0.25, softirqPressure: 0, queuePressure: 0, memoryPressure: 0, pathFeatures: { 'WAN-A': { available: true, trafficUtilization: 1.0, ppsPressure: 1.0, dropErrorPressure: 1.0 }, 'WAN-B': { available: true, trafficUtilization: 0.0, ppsPressure: 0.0, dropErrorPressure: 0.0 } } }; };
goal = function() { return 'balanced'; };
system_guard = function() { return { pass: true, reasons: [], health: {} }; };
compatibility = function() { return { allowed: true, blockers: [], warnings: [] }; };
let _production_ring = { rxCurrent: 512, txCurrent: 512, rxMax: 4096, txMax: 4096 };
ring_snapshot = function() { return { rxCurrent: _production_ring.rxCurrent, txCurrent: _production_ring.txCurrent, rxMax: _production_ring.rxMax, txMax: _production_ring.txMax }; };
ring_apply = function(ref, params) {
	if (params.rxFloor != null) _production_ring.rxCurrent = params.rxFloor;
	if (params.txFloor != null) _production_ring.txCurrent = params.txFloor;
	return { rc: 0, out: '' };
};
ring_restore = function(ref, snap) {
	if (snap.rxCurrent != null) _production_ring.rxCurrent = snap.rxCurrent;
	if (snap.txCurrent != null) _production_ring.txCurrent = snap.txCurrent;
	return { rc: 0, out: '' };
};
ring_matches = function() { return true; };
link_ok = function() { return true; };
persist_ring_policy = function() { return true; };

/* Exercise the production interval gate directly.  These are counter
 * windows, not a Python reimplementation: zero deltas and counter resets
 * must never become measured zero CPU or a usable reward. */
let _cpu_valid = cpu_interval({ total: 100, idle: 60 }, { total: 120, idle: 70 });
let _cpu_zero_delta = cpu_interval({ total: 100, idle: 60 }, { total: 100, idle: 60 });
let _cpu_reset = cpu_interval({ total: 100, idle: 60 }, { total: 90, idle: 50 });
production_check(_cpu_valid.valid === true && _cpu_valid.busyInterval == 0.5, 'CPU interval accepts positive counter window', _cpu_valid);
production_check(_cpu_zero_delta.valid === false, 'CPU interval rejects zero counter delta', _cpu_zero_delta);
production_check(_cpu_reset.valid === false, 'CPU interval rejects counter reset', _cpu_reset);
let _invalid_cpu_reward = build_reward('balanced',
	{ bitsPerSecond: 100, latencyMedianMs: 10, latencyP95Ms: 20 },
	{ bitsPerSecond: 110, latencyMedianMs: 9, latencyP95Ms: 18 },
	{ cpuBusyInterval: 0, cpuWindowValid: false, health: { cpu: { busyPct: 0.1 } } },
	{ cpuBusyInterval: 0.8, cpuWindowValid: true }, false);
production_check(_invalid_cpu_reward.validated === false && _invalid_cpu_reward.components.cpuEfficiency == null && _invalid_cpu_reward.components.cpuBusyInterval.control == null,
	'CPU invalid window fails closed without cumulative fallback', _invalid_cpu_reward);

let _production_stats_a = { candidateId: smart_candidate_identity(_production_a), businessActionId: 'nic.ring.floor', attemptCount: 0, successCount: 0, failureCount: 0, rollbackCount: 0, validatedOutcomeCount: 0, recentRewards: [], recentRewardMean: 0, negativeStreak: 0, lastExecution: null, cooldownUntil: 0, cooldownReason: null };
let _production_stats_b = { candidateId: smart_candidate_identity(_production_b), businessActionId: 'nic.ring.floor', attemptCount: 0, successCount: 0, failureCount: 0, rollbackCount: 0, validatedOutcomeCount: 0, recentRewards: [], recentRewardMean: 0, negativeStreak: 0, lastExecution: null, cooldownUntil: 0, cooldownReason: null };
let _production_actions = {};
_production_actions[_production_stats_a.candidateId] = _production_stats_a;
_production_actions[_production_stats_b.candidateId] = _production_stats_b;
let _production_contexts = {};
_production_contexts[_production_context] = { goal: 'balanced', validatedSamples: 8, ewmaReward: 0.4, rewardMean: 0.4, rewardM2: 0, recentRewards: [ 0.4 ], drifted: false, driftRecoverySamples: 0, actions: _production_actions };
smart_state_save({ schemaVersion: 3, contexts: _production_contexts });

let _production_observed = rill_observe('conservative');
production_check(_production_observed.ok === true, 'production Core observe reaches real Runtime', _production_observed);
let _production_selection = select_smart_action('conservative', candidate_actions(), smart_selector_context());
production_check(_production_selection.source == 'rill', 'production selector accepts real Runtime decision', _production_selection);
production_check(_production_selection.selectedCandidateId == smart_candidate_identity(_production_b), 'real Runtime selects candidate B', _production_selection);
production_check(_production_selection.selectedActionId == 'nic.ring.floor', 'production selector preserves businessActionId', _production_selection);
let _production_action = smart_selector_action(_production_selection, candidate_actions());
production_check(_production_action?.applyTarget == 'NIC-B' && (_production_action?.evaluationPaths ?? [])[0] == 'WAN-B', 'selected production action binds target and path B', _production_action);
let _production_result = apply_action({ actionId: 'nic.ring.floor', target: 'NIC-B', executionSource: 'rill-advisory', decisionId: _production_selection.decisionId });
let _production_tx = _production_result.transaction ?? {};
production_check(_production_result.ok === true, 'production transaction completes through Core safety path', _production_result);
production_check(_production_tx.candidateId == smart_candidate_identity(_production_b), 'transaction carries exact candidateId B', _production_tx);
production_check(_production_tx.businessActionId == 'nic.ring.floor' && _production_tx.actionId == 'nic.ring.floor', 'transaction preserves business action separately', _production_tx);
production_check(_production_tx.applyTarget == 'NIC-B', 'transaction carries applyTarget B', _production_tx);
production_check((_production_tx.evaluationPaths ?? [])[0] == 'WAN-B', 'transaction carries evaluation path B', _production_tx);
let _production_after = smart_context_stats(_production_context, smart_candidate_identity(_production_b), false).stats;
let _production_other = smart_context_stats(_production_context, smart_candidate_identity(_production_a), false).stats;
production_check((_production_after?.successCount ?? 0) == 1 && (_production_other?.successCount ?? 0) == 0, 'candidate success history remains isolated', { selected: _production_after, other: _production_other });
print('PRODUCTION_CORE_EVIDENCE ' + sprintf('%.J', { candidateA: smart_candidate_identity(_production_a), candidateB: smart_candidate_identity(_production_b), runtimeSelectedCandidateId: _production_selection.selectedCandidateId, coreSelectedCandidateId: _production_selection.selectedCandidateId, businessActionId: _production_selection.selectedActionId, transactionCandidateId: _production_tx.candidateId, transactionApplyTarget: _production_tx.applyTarget, transactionEvaluationPaths: _production_tx.evaluationPaths, verdict: _production_failures == 0 ? 'PASS' : 'FAIL' }) + '\n');
if (_production_failures > 0) exit(1);
exit(0);
