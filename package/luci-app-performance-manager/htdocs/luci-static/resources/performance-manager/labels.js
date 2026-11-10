'use strict';
'require baseclass';

/*
 * Presentation-layer dictionary for Performance Manager.
 *
 * The ubus/ucode backend owns the contract: it returns stable machine values
 * (enum ids, action ids, UUIDs, hashes, millisecond counters).  Those values
 * must never be shown to the user directly.  Every view renders text through
 * this module, which maps a contract value to a translated label and always
 * falls back to a translated "unknown" label instead of leaking the raw value.
 *
 * Raw values stay available for troubleshooting, but only inside a collapsed
 * "technical details" block that the views build themselves.
 */

const UNKNOWN = _('Unknown');
const UNKNOWN_STATE = _('Unknown state');
const DASH = '—';

const AUTOMATION = {
	manual: _('Manual'),
	conservative: _('Conservative'),
	assisted: _('Assisted')
};

const GOAL = {
	balanced: _('Balanced'),
	throughput: _('Throughput first'),
	latency: _('Latency first'),
	cpu_efficiency: _('CPU efficiency first')
};

const RUNTIME_STATUS = {
	'Runtime · Disabled': _('Runtime disabled'),
	'Runtime · Binary invalid': _('Runtime binary invalid'),
	'Runtime · Not provisioned': _('Runtime not provisioned'),
	'Runtime · Unavailable': _('Runtime unavailable'),
	'Runtime · Version mismatch': _('Runtime version mismatch'),
	'Runtime · Error': _('Runtime error'),
	'Runtime · Missing capabilities': _('Runtime missing capabilities'),
	'Runtime · Unhealthy': _('Runtime unhealthy'),
	'Runtime · Learning': _('Runtime learning'),
	'Runtime · Available': _('Runtime available'),
	'Runtime · Collecting': _('Runtime collecting data')
};

const GUARD_REASON = {
	'low-memory': _('Low available memory'),
	'recent-oom': _('Recent out-of-memory kill'),
	'high-cpu-load': _('High CPU load'),
	'high-cpu-steal': _('High CPU steal from virtualisation'),
	'thermal-hot': _('Device temperature too high'),
	'state-storage-unavailable': _('State storage unavailable'),
	'persistent-storage-unavailable': _('Persistent storage unavailable')
};

const SMART_REASON = {
	'deterministic-core-fallback': _('Using the deterministic core policy'),
	'no-legal-action': _('No action is allowed right now'),
	'smart-rill-opt-out': _('Rill smart decisions are turned off'),
	'confidence-below-policy': _('Confidence is below the policy threshold'),
	'recommended-for-benchmark': _('Recommended for a performance test only'),
	'missing-exact-decision': _('No exact decision is available'),
	'rill-selected-noop': _('The Rill selection requires no change'),
	'runtime-selected-eligible-candidate': _('Rill selected an eligible candidate'),
	'evaluation-route-unresolved': _('The evaluation path could not be resolved'),
	'health-regression': _('Health regressed during the test'),
	'validated-controlled-ab': _('Validated by a controlled A/B test'),
	'same-attempt-already-applied': _('The same attempt was already applied')
};

const RILL_REASON = {
	disabled: _('Runtime disabled'),
	'binary-invalid': _('Runtime binary invalid'),
	'not-provisioned': _('Runtime not provisioned'),
	'unavailable': _('Runtime unavailable'),
	'runtime-version-mismatch': _('Runtime version mismatch'),
	'missing-required-capability': _('Required capability is missing'),
	'model-unhealthy': _('Model is unhealthy'),
	'invalid-observe-response': _('Observation response was invalid'),
	'binding-registration-failed': _('Decision binding could not be registered'),
	'duplicate-candidate-id': _('Duplicate candidate identifier'),
	'rill-selected-candidate-missing': _('The selected candidate no longer exists'),
	'rill-score-invalid': _('The reported score is invalid'),
	'rill-ranking-candidate-unknown': _('The ranking contains an unknown candidate'),
	'mode-policy-blocked': _('Blocked by the current mode policy'),
	'target-unresolved': _('The target could not be resolved'),
	'compatibility-blocked': _('Compatibility check failed'),
	'action-cooldown': _('The action is cooling down')
};

const LEARNING_STAGE = {
	cold: _('Cold start (not enough samples)'),
	warming: _('Learning'),
	ready: _('Ready'),
	drifted: _('Drifted')
};

const RISK = {
	safe: _('Safe'),
	caution: _('Use with caution'),
	benchmark: _('Test only'),
	dangerous: _('High risk'),
	none: _('None')
};

const SCOPE = {
	system: _('System'),
	device: _('Device'),
	interface: _('Network interface'),
	service: _('Service'),
	radio: _('Wireless'),
	storage: _('Storage')
};

const AVAILABILITY = {
	available: _('Available'),
	unavailable: _('Unavailable'),
	degraded: _('Limited'),
	unknown: _('Unknown')
};

const MEASUREMENT_QUALITY = {
	controlled_ab: _('Controlled A/B comparison'),
	passive_before_after: _('Passive before and after'),
	health_only: _('Health observation only'),
	invalid: _('Invalid (not adopted)')
};

const STATE = {
	planned: _('Planned'),
	locked: _('Locked'),
	snapshotted: _('Snapshot taken'),
	pending: _('Pending'),
	applied: _('Applied'),
	verified: _('Verified'),
	awaiting_confirm: _('Waiting for confirmation'),
	committed: _('Committed'),
	rolled_back: _('Rolled back'),
	failed: _('Failed'),
	awaiting_control: _('Waiting for baseline evidence'),
	candidate_applied: _('Candidate applied'),
	completed: _('Completed'),
	stopped: _('Stopped')
};

const ROUTE_PROVIDER = {
	'ip-full+rtnl-events': _('Full routing tools (ip-full with route events)'),
	'netifd-fallback': _('netifd fallback'),
	unresolved: _('Not resolved')
};

const WORKLOAD_CLASS = {
	plain_forwarding: _('Plain forwarding'),
	local_endpoint: _('Local endpoint'),
	transparent_proxy: _('Transparent proxy'),
	vpn_tunnel: _('VPN tunnel'),
	pppoe: _('PPPoE'),
	wireless: _('Wireless'),
	storage_service: _('Storage service')
};

const PROVIDER = {
	'openwrt-netifd': _('OpenWrt netifd'),
	'linux-kernel': _('Linux kernel'),
	'linux-sysctl': _('Linux sysctl'),
	'driver-ethtool': _('Network driver (ethtool)'),
	'netifd-fallback': _('netifd fallback'),
	'nl80211/iw': _('Wireless stack (nl80211/iw)'),
	'firewall4/external': _('Firewall (firewall4 or third party)')
};

const OWNERSHIP = {
	user: _('User configuration'),
	external: _('Managed externally'),
	preexisting: _('Pre-existing configuration'),
	performance_manager: _('Performance Manager'),
	unknown: _('Unknown')
};

const POLICY = {
	'observe-respect': _('Observe only (respect existing configuration)'),
	'observe-protect-preexisting': _('Observe only (protect pre-existing configuration)'),
	'benchmark-only': _('Test only'),
	'discover-only-until-explicit-controlled-ab': _('Discover only (requires an explicit controlled A/B test)'),
	'conditional-capacity-benchmark-only': _('Capacity test only when conditions are met'),
	'observe-analyze; channel/width/txpower require explicit benchmark': _('Observe and analyse only (channel, width and transmit power require an explicit test)'),
	'observe; benchmark-only; functional-correctness-hard-fail': _('Observe only; test only; functional correctness is a hard requirement')
};

const AUTHORITY = {
	'advisory-only': _('Advisory only (never applied automatically)')
};

const TRANSPORT = {
	unavailable: _('Not connected'),
	connected: _('Connected'),
	subprocess: _('Local subprocess')
};

const PROFILE = {
	minimal: _('Minimal'),
	recommended: _('Recommended'),
	wireless: _('Wireless'),
	diagnostics: _('Diagnostics'),
	'performance-x86': _('High performance (x86)')
};

const CONFIDENCE_LEVEL = {
	high: _('High'),
	medium: _('Medium'),
	low: _('Low')
};

const EVALUATION_SEMANTICS = {
	local: _('Local path'),
	forwarding: _('Forwarding path')
};

const BENCHMARK_STATUS = {
	'endpoint-required': _('Needs endpoint test'),
	blocked: _('Unavailable')
};

const CLIENT_ROLE = {
	'lan-client': _('LAN client'),
	'router-local-client': _('Router local client')
};

const DISPOSITION = {
	respect: _('Respect existing configuration'),
	analyze: _('Analyse only')
};

const INTEGRATION = {
	openclash: _('OpenClash proxy'),
	passwall: _('PassWall proxy'),
	homeproxy: _('HomeProxy proxy'),
	sqm: _('SQM shaping'),
	qosify: _('qosify classification'),
	mwan3: _('mwan3 multi-WAN'),
	pbr: _('PBR policy routing'),
	wireguard: _('WireGuard'),
	openvpn: _('OpenVPN'),
	docker: _('Docker'),
	transparentProxy: _('Transparent proxy')
};

/* Name and one-line description for every action capability id the backend
 * can return.  Used for both action cards and capability cards. */
const ENTITIES = {
	'nic.ring.floor': {
		name: _('NIC ring buffer (conservative floor)'),
		desc: _('Raise the network card ring buffer to the conservative floor of 1024 to reduce packet drops under load.')
	},
	'nic.ring': {
		name: _('NIC ring buffer'),
		desc: _('Observe the receive and transmit ring buffer sizes of the network card.')
	},
	'nic.coalescing': {
		name: _('NIC interrupt coalescing'),
		desc: _('Adjust interrupt coalescing to trade latency against CPU usage.')
	},
	'nic.offload': {
		name: _('NIC offload features'),
		desc: _('Observe hardware offload features of the network card without changing existing settings.')
	},
	'network.backlog': {
		name: _('Kernel receive backlog'),
		desc: _('Adjust the maximum length of the kernel receive backlog queue.')
	},
	'network.budget': {
		name: _('Kernel polling budget'),
		desc: _('Adjust how many packets the kernel processes per soft-interrupt poll.')
	},
	'network.buffers': {
		name: _('Socket buffer limits'),
		desc: _('Adjust the kernel socket receive buffer limit.')
	},
	'network.busy_poll': {
		name: _('Socket busy polling'),
		desc: _('Adjust busy polling to reduce latency at the cost of CPU time.')
	},
	'netdev.tx_queue_len': {
		name: _('NIC transmit queue length'),
		desc: _('Adjust the transmit queue length to absorb traffic bursts.')
	},
	'service.irqbalance': {
		name: _('Interrupt balancing service'),
		desc: _('Enable or stop irqbalance, which spreads interrupts across CPU cores.')
	},
	'tcp.cc': {
		name: _('TCP congestion control'),
		desc: _('Switch the TCP congestion control algorithm.')
	},
	'qdisc.replace': {
		name: _('Traffic scheduler replacement'),
		desc: _('Replace the network card queueing discipline; no reversible provider is available.')
	},
	'fastpath.firewall': {
		name: _('Firewall fast path'),
		desc: _('Observe software and hardware flow offloading and third-party fast path support.')
	},
	'fastpath.software_flow_offload': {
		name: _('Software flow offloading'),
		desc: _('Enable or disable firewall software flow offloading.')
	},
	'fastpath.hardware_flow_offload': {
		name: _('Hardware flow offloading'),
		desc: _('Enable or disable firewall hardware flow offloading.')
	},
	'fastpath.third_party_sfe': {
		name: _('Third-party fast path'),
		desc: _('Observe third-party Shortcut-FE style fast path support.')
	},
	'cpu.governor': {
		name: _('CPU frequency governor'),
		desc: _('Adjust the CPU frequency governor (performance or schedutil).')
	},
	'network.packet_steering.native': {
		name: _('Native packet steering'),
		desc: _('Built-in OpenWrt packet steering. It is observed only; existing ownership is never seized.')
	},
	'network.local_port_capacity': {
		name: _('Local port capacity'),
		desc: _('Local port range, reserved ports and connection tracking capacity. Relevant under proxy or high connection pressure.')
	},
	'benchmark.kernel-network': {
		name: _('Kernel network baseline'),
		desc: _('Collect kernel network parameters and available benchmark candidates for explicit controlled tests.')
	},
	'wireless.observe': {
		name: _('Wireless observation'),
		desc: _('Observe radios and driver details without changing channel or transmit power.')
	},
	'pm.noop': {
		name: _('Keep the current configuration'),
		desc: _('No change is recommended right now.')
	}
};

/* Static sentences produced by the backend.  The backend is the contract
 * owner, so these are matched by exact text and translated here. */
const SENTENCES = {
	'Native OpenWrt provider detected; no ownership seizure.':
		_('The native OpenWrt provider was detected; existing ownership is preserved.'),
	'Local port capacity is relevant under proxy/high-connection pressure; reserved ports and ownership must be preserved. Any change remains benchmark-only.':
		_('Local port capacity matters under proxy or high-connection pressure. Reserved ports and existing ownership are preserved, and any change is limited to a performance test.'),
	'Hyper-V hv_netvsc ring is below the conservative 1024 floor while hardware maximum supports it.':
		_('The Hyper-V hv_netvsc ring buffer is below the conservative floor of 1024 even though the hardware maximum allows raising it.')
};

const ERROR_CODE = {
	UBUS_STATUS_OK: _('Succeeded'),
	UBUS_STATUS_INVALID_COMMAND: _('The backend command is not valid'),
	UBUS_STATUS_INVALID_ARGUMENT: _('The request parameters are not valid'),
	UBUS_STATUS_METHOD_NOT_FOUND: _('The backend method does not exist'),
	UBUS_STATUS_NOT_FOUND: _('The target was not found'),
	UBUS_STATUS_NO_DATA: _('No data is available'),
	UBUS_STATUS_PERMISSION_DENIED: _('Permission denied'),
	UBUS_STATUS_TIMEOUT: _('The operation timed out'),
	UBUS_STATUS_NOT_SUPPORTED: _('The operation is not supported'),
	UBUS_STATUS_UNKNOWN_ERROR: _('The backend reported an unknown error'),
	UBUS_STATUS_CONNECTION_FAILED: _('Could not connect to the backend'),
	'runtime-version-mismatch': _('The runtime version does not match'),
	'runtime-unavailable': _('The runtime is unavailable'),
	'runtime-bin-invalid': _('The runtime binary is invalid'),
	'provider-unavailable': _('The provider is unavailable on this device'),
	'compatibility-blocked': _('The compatibility check failed'),
	'route-unresolved': _('The route could not be resolved'),
	'goal-unsupported-for-controlled-ab': _('This goal cannot be validated with a controlled A/B test'),
	'invalid-config-explicit-start-disabled': _('Explicit test start is disabled in the configuration'),
	'one-variable-contract-disabled': _('The single-variable test contract is disabled')
};

function has(table, key) {
	return Object.prototype.hasOwnProperty.call(table, key);
}

function pick(table, value, fallback) {
	if (value == null || value === '') return fallback || UNKNOWN;
	const key = String(value);
	if (has(table, key)) return table[key];
	return fallback || UNKNOWN;
}

function fmt(value) {
	return value == null || value === '' ? DASH : String(value);
}

function shortId(value) {
	return typeof value === 'string' && value.length ? value.slice(0, 8) : DASH;
}

function percent(value) {
	const n = typeof value === 'number' ? value : Number(value);
	if (value == null || value === '' || !isFinite(n)) return DASH;
	if (n < -1 || n > 1) return n.toFixed(3);
	return Math.round(n * 100) + '%';
}

function duration(ms) {
	const n = typeof ms === 'number' ? ms : Number(ms);
	if (ms == null || ms === '' || !isFinite(n) || n < 0) return DASH;
	const total = Math.ceil(n / 1000);
	if (total < 60) return _('About %s seconds').format(total);
	const minutes = Math.floor(total / 60), seconds = total % 60;
	if (seconds === 0) return _('About %s minutes').format(minutes);
	return _('About %s min %s sec').format(minutes, seconds);
}

function errorRaw(err) {
	if (err == null) return DASH;
	if (typeof err === 'string') return err;
	if (err.message) return String(err.message);
	const text = String(err);
	return text === '[object Object]' ? JSON.stringify(err) : text;
}

function errorSummary(err) {
	const raw = errorRaw(err);
	if (raw === DASH) return _('Unknown error, see technical details');
	if (has(ERROR_CODE, raw)) return ERROR_CODE[raw];
	const ubus = raw.match(/UBUS_STATUS_[A-Z_]+/);
	if (ubus && has(ERROR_CODE, ubus[0])) return ERROR_CODE[ubus[0]];
	const head = raw.split(':')[0];
	if (has(ERROR_CODE, head)) return ERROR_CODE[head];
	if (head !== raw) return _('%s, see technical details').format(errorSummary(head));
	return _('Unknown error, see technical details');
}

function smartReason(value) {
	if (value == null || value === '') return UNKNOWN_STATE;
	const key = String(value);
	if (has(SMART_REASON, key)) return SMART_REASON[key];
	if (has(RILL_REASON, key)) return RILL_REASON[key];
	if (key.indexOf('rill-') === 0) {
		const rest = key.slice(5);
		if (has(RILL_REASON, rest)) return RILL_REASON[rest];
		if (has(LEARNING_STAGE, rest)) return LEARNING_STAGE[rest];
	}
	if (key.indexOf('missing-evidence:') === 0)
		return _('Missing evidence: %s').format(key.slice(16).split(',').join('、'));
	if (key.indexOf('provider-unavailable:') === 0) return ERROR_CODE['provider-unavailable'];
	return UNKNOWN_STATE;
}

function path(value) {
	if (value == null || value === '') return UNKNOWN;
	const id = String(value).replace(/^path:/, '');
	if (id === 'lan-to-wan') return _('LAN to WAN');
	if (id === 'local-endpoint') return _('Local endpoint');
	const m = id.match(/^path:lan-to-(.+)$/) || id.match(/^lan-to-(.+)$/);
	if (m) return _('LAN to %s').format(m[1]);
	return UNKNOWN;
}

function target(value) {
	if (value == null || value === '') return DASH;
	const ref = String(value);
	if (ref.indexOf('path:') === 0) return path(ref);
	const idx = ref.indexOf(':');
	if (idx < 0) return UNKNOWN;
	const kind = ref.slice(0, idx), name = ref.slice(idx + 1);
	if (kind === 'netdev') return _('Network interface %s').format(name);
	if (kind === 'service') return _('Service %s').format(name);
	if (kind === 'system' && name === 'kernel') return _('System kernel');
	if (kind === 'system' && name === 'cpu') return _('CPU');
	if (kind === 'system') return _('System %s').format(name);
	if (kind === 'device') return _('Device %s').format(name);
	if (kind === 'radio') return _('Wireless radio %s').format(name);
	return UNKNOWN;
}

function candidate(value) {
	if (value == null || value === '') return DASH;
	const id = String(value);
	const m = id.match(/^([^@]+)@target=/);
	if (!m) return actionName(id);
	return _('%s candidate').format(actionName(m[1]));
}

function transaction(value) {
	if (value == null || value === '') return UNKNOWN;
	return _('Transaction %s').format(shortId(value));
}

function routeIdentity(value) {
	if (value == null || value === '') return UNKNOWN;
	if (String(value) === 'unresolved') return _('Not resolved');
	return _('Resolved');
}

function entity(id) {
	return id != null && has(ENTITIES, String(id)) ? ENTITIES[String(id)] : null;
}

function actionName(id) {
	const e = entity(id);
	return e ? e.name : UNKNOWN;
}

function actionDesc(id) {
	const e = entity(id);
	return e ? e.desc : UNKNOWN;
}

function action(id) {
	return actionName(id);
}

function capabilityName(id) {
	return actionName(id);
}

function capabilityDesc(id) {
	return actionDesc(id);
}

function observationDetail(detail) {
	if (detail == null || detail === '') return _('This capability was detected on the device.');
	if (has(SENTENCES, String(detail))) return SENTENCES[String(detail)];
	return _('This capability was detected on the device. Open technical details for the raw output.');
}

function actionReason(reason) {
	if (reason == null || reason === '') return DASH;
	if (has(SENTENCES, String(reason))) return SENTENCES[String(reason)];
	return smartReason(reason);
}

function confidence(value) {
	if (value == null || value === '') return DASH;
	if (typeof value === 'string' && has(CONFIDENCE_LEVEL, value)) return CONFIDENCE_LEVEL[value];
	if (typeof value === 'number' || /^-?[0-9.]+$/.test(String(value))) return percent(value);
	return UNKNOWN;
}

function integrationSummary(state) {
	if (!state || typeof state !== 'object') return DASH;
	const on = [];
	Object.keys(state).forEach(function(key) {
		if (state[key] === true) on.push(has(INTEGRATION, key) ? INTEGRATION[key] : UNKNOWN);
	});
	return on.length ? on.join('、') : _('None');
}

function map(kind, value) {
	const tables = {
		automation: AUTOMATION, goal: GOAL, runtimeStatus: RUNTIME_STATUS,
		guardReason: GUARD_REASON, smartReason: SMART_REASON, learningStage: LEARNING_STAGE,
		risk: RISK, scope: SCOPE, availability: AVAILABILITY, measurementQuality: MEASUREMENT_QUALITY,
		state: STATE, routeProvider: ROUTE_PROVIDER, workloadClass: WORKLOAD_CLASS,
		provider: PROVIDER, ownership: OWNERSHIP, policy: POLICY, authority: AUTHORITY,
		transport: TRANSPORT, profile: PROFILE, confidence: CONFIDENCE_LEVEL,
		evaluationSemantics: EVALUATION_SEMANTICS, benchmarkStatus: BENCHMARK_STATUS,
		clientRole: CLIENT_ROLE, disposition: DISPOSITION, integration: INTEGRATION
	};
	const table = tables[kind];
	if (!table) return UNKNOWN;
	if (kind === 'smartReason') return smartReason(value);
	return pick(table, value, UNKNOWN_STATE);
}

return baseclass.extend({
	fmt: fmt,
	unknown: UNKNOWN,
	shortId: shortId,
	percent: percent,
	score: percent,
	duration: duration,
	action: action,
	actionName: actionName,
	actionDesc: actionDesc,
	actionReason: actionReason,
	capability: capabilityName,
	capabilityName: capabilityName,
	capabilityDesc: capabilityDesc,
	observationDetail: observationDetail,
	target: target,
	path: path,
	routeIdentity: routeIdentity,
	transaction: transaction,
	candidate: candidate,
	automation: function(v) { return pick(AUTOMATION, v, UNKNOWN_STATE); },
	goal: function(v) { return pick(GOAL, v, UNKNOWN_STATE); },
	runtimeStatus: function(v) { return pick(RUNTIME_STATUS, v, UNKNOWN_STATE); },
	guardReason: function(v) { return pick(GUARD_REASON, v, UNKNOWN_STATE); },
	smartReason: smartReason,
	learningStage: function(v) { return pick(LEARNING_STAGE, v, UNKNOWN_STATE); },
	risk: function(v) { return pick(RISK, v, UNKNOWN_STATE); },
	scope: function(v) { return pick(SCOPE, v, UNKNOWN_STATE); },
	availability: function(v) { return pick(AVAILABILITY, v, UNKNOWN_STATE); },
	measurementQuality: function(v) { return pick(MEASUREMENT_QUALITY, v, UNKNOWN_STATE); },
	state: function(v) { return pick(STATE, v, UNKNOWN_STATE); },
	routeProvider: function(v) { return pick(ROUTE_PROVIDER, v, UNKNOWN_STATE); },
	workloadClass: function(v) { return pick(WORKLOAD_CLASS, v, UNKNOWN_STATE); },
	provider: function(v) { return pick(PROVIDER, v, UNKNOWN_STATE); },
	ownership: function(v) { return pick(OWNERSHIP, v, UNKNOWN_STATE); },
	policy: function(v) { return pick(POLICY, v, UNKNOWN_STATE); },
	authority: function(v) { return pick(AUTHORITY, v, UNKNOWN_STATE); },
	transport: function(v) { return pick(TRANSPORT, v, UNKNOWN_STATE); },
	profile: function(v) { return pick(PROFILE, v, UNKNOWN_STATE); },
	confidence: confidence,
	evaluationSemantics: function(v) { return pick(EVALUATION_SEMANTICS, v, UNKNOWN_STATE); },
	benchmarkStatus: function(v) { return pick(BENCHMARK_STATUS, v, UNKNOWN_STATE); },
	clientRole: function(v) { return pick(CLIENT_ROLE, v, UNKNOWN_STATE); },
	disposition: function(v) { return pick(DISPOSITION, v, UNKNOWN_STATE); },
	integrationSummary: integrationSummary,
	errorSummary: errorSummary,
	errorDetail: errorRaw,
	map: map
});
