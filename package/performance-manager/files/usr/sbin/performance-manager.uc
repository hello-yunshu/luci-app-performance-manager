#!/usr/bin/env ucode
'use strict';

import * as fs from 'fs';
import * as ubusmod from 'ubus';
import * as uloop from 'uloop';
import * as socket from 'socket';
import * as rtnl from 'rtnl';
const basename = fs.basename;
import { VERSION, SCHEMA_VERSION, WORKLOAD_CLASSES, SAFE_ACTIONS, BENCHMARK_ACTIONS } from '/usr/share/performance-manager/contracts.uc';

const UBUS_NAME = 'performance-manager';
const DEFAULT_STATE_DIR = '/tmp/performance-manager';
const DEFAULT_PERSIST_DIR = '/etc/performance-manager';
const PROFILE_DIR = '/usr/share/performance-manager/profiles';
const MAX_HISTORY_LINES = 512;
/* PM<->Rill integration contract.  Rill is an external runtime: the Core only
 * negotiates capability via the bounded Unix-socket protocol and never
 * compiles or bundles Rill.  A missing runtime, unreachable service or protocol
 * major mismatch is fail-closed (integration unavailable/incompatible). */
const RILL_CONTRACT = 'pm-rill-shadow';
const RILL_PROTOCOL_VERSION = 1;
const RILL_REQUIRED_CAPABILITIES = [ 'context-partitioned-model', 'goal-partition', 'validated-outcome', 'decision-ledger', 'model-health' ];
const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ];
const RILL_STATES = { disabled: 'disabled', notProvisioned: 'not-provisioned', binaryInvalid: 'binary-invalid', starting: 'starting', available: 'available', learning: 'learning', incompatible: 'incompatible', unhealthy: 'unhealthy', unavailable: 'unavailable' };
const RILL_BINDINGS_SCHEMA_VERSION = 2;
const RILL_EXECUTION_SCHEMA_VERSION = 1;
const RILL_BINDINGS_MAX = 64;
const RILL_BINDINGS_TTL_MS = 3600000;
const RILL_ADVISORY_TTL_MS = 3600000;
const RILL_MODEL_GENERATION = 1;
const RILL_OBSERVE_MIN_INTERVAL_MS = 30000;
const RILL_PINNED_RELEASE_VERSION = '1.2.0';
const RILL_PINNED_ADAPTER_VERSION = '0.15.0';
const GOALS = [ 'balanced', 'throughput', 'latency', 'cpu_efficiency' ];
/* Only throughput A/B is measurable with the current iperf3 methodology.
 * Other goals fail-closed rather than silently degrading to throughput. */
const GOAL_MEASURABLE = { balanced: 'throughput', throughput: 'throughput', latency: null, cpu_efficiency: null };

let topology_generation = 1;
let topology_cache = null;
let topology_cache_ms = 0;
const TOPOLOGY_MIN_INTERVAL_MS = 5000;
let tx_counter = 0;
let event_timer = null;
let telemetry_timer = null;
let deep_timer = null;
let rill_outcome_timer = null;
let rill_outcome_schedule_hook = null;
let rill_recover_execution_hook = null;
let rill_prepare_outcome = null;
let rill_arm_outcome = null;
let rill_report_outcome = null;
let rill_binding_release_reservation = null;
let listeners = [];
let tx_timers = {};
let last_topology_signature = null;
let persistent_write_count = 0;
let persistent_write_bytes = 0;
let rill_runtime_counters = {
	rillObserveAttempts: 0,
	rillObserveAccepted: 0,
	rillOutcomeAttempts: 0,
	rillOutcomeAccepted: 0,
	rillOutcomeReconciled: 0,
	rillOutcomeRetryableFailures: 0,
	rillOutcomeTerminalFailures: 0,
	rillDecisionReserved: 0,
	rillOutcomeSentUnknown: 0,
	rillOutcomeRecoveredAfterCoreRestart: 0,
	rillOutcomeRecoveredAfterBoot: 0,
	rillBindingHighWater: 0
};
let conn = ubusmod.connect();
if (!conn) {
	warn('performance-manager: unable to connect to ubus\n');
	exit(1);
}

function shell_quote(arg) {
	let s = `${arg}`;
	/* Plain safe characters need no quoting; everything else is single-quoted
	 * with the POSIX \' escape so argv elements survive the shell round-trip. */
	if (match(s, /^[A-Za-z0-9_@%+=:,./\-]+$/))
		return s;
	return sprintf("'%s'", replace(s, /'/g, "'\\''"));
}

function run(argv) {
	/* ucode's fs.popen rejects an argv ARRAY on the supported OpenWrt runtime
	 * (returns null, so every command would silently fail). A shell-joined
	 * string is the portable form that works on real OpenWrt 25.12.5. Each
	 * element is POSIX-quoted so arguments survive the /bin/sh round-trip. */
	let cmd = join(' ', map(argv ?? [], shell_quote));
	let p = fs.popen(cmd, 'r');
	if (!p)
		return { rc: 127, out: '' };
	let out = p.read('all') ?? '';
	let rc = p.close();
	return { rc: rc ?? 127, out: out };
}

function trimstr(s) {
	return trim(s ?? '');
}

function read(path, limit) {
	return fs.readfile(path, limit) ?? null;
}

function file_exists(path) {
	return fs.stat(path) != null;
}

function file_executable(path) {
	/* Regular (non-directory) existing file with the executable bit set,
	 * matching resolve_binary() in the performance-manager-rill init guard.
	 * A directory is never a usable adapter binary. */
	if (!file_exists(path)) return false;
	if (run([ 'test', '-d', path ]).rc == 0) return false;
	return run([ 'test', '-x', path ]).rc == 0;
}

function ensure_dir(path) {
	run([ 'mkdir', '-p', path ]);
}

function cfg(key, fallback) {
	let r = run([ 'uci', '-q', 'get', `performance-manager.${key}` ]);
	if (r.rc == 0 && length(trimstr(r.out)))
		return trimstr(r.out);
	return fallback;
}

function bool_cfg(key, fallback) {
	let v = cfg(key, fallback ? '1' : '0');
	return v == '1' || v == 'true' || v == 'yes' || v == 'on';
}

function int_cfg(key, fallback) {
	let v = +cfg(key, `${fallback}`);
	return v >= 0 ? v : fallback;
}

function str_cfg(key, fallback) {
	return cfg(key, fallback) ?? fallback;
}

function state_dir() {
	return cfg('main.state_dir', DEFAULT_STATE_DIR);
}

function persist_dir() {
	return cfg('main.persistent_dir', DEFAULT_PERSIST_DIR);
}

function boot_id() {
	return trimstr(read('/proc/sys/kernel/random/boot_id')) || 'unknown-boot';
}

function monotonic_ms() {
	let u = split(trimstr(read('/proc/uptime') ?? '0 0'), ' ')[0] ?? '0';
	return int(+u * 1000);
}

function safe_name(s) {
	return replace(`${s}`, /[^A-Za-z0-9_.-]/g, '_');
}

function fnv1a32(value) {
	let text = `${value ?? ''}`;
	let h = 2166136261;
	for (let i = 0; i < length(text); i++)
		h = ((h ^ ord(text, i)) * 16777619) & 0xffffffff;
	return sprintf('%08x', h);
}

function stable_list_hash(prefix, values) {
	let rows = map(values ?? [], function(v) { return `${v}`; });
	sort(rows);
	return `${prefix}:${fnv1a32(join('\n', rows))}`;
}

function json_read(path, fallback) {
	let data = read(path);
	if (data == null || !length(trimstr(data)))
		return fallback;
	try {
		return json(data);
	}
	catch (e) {
		return fallback;
	}
}

function note_persistent_write(path, bytes) {
	let root=persist_dir();
	if (path == root || substr(path,0,length(root)+1) == `${root}/`) {
		persistent_write_count++;
		persistent_write_bytes += max(0, bytes ?? 0);
	}
}

function json_write(path, obj) {
	let dir = join('/', slice(split(path, '/'), 0, -1));
	if (!length(dir))
		dir = '/';
	ensure_dir(dir);
	let tmp = `${path}.tmp`, wire=sprintf('%.J\n', obj);
	if (fs.writefile(tmp, wire) == null)
		return false;
	let mv = run([ 'mv', '-f', tmp, path ]);
	if (mv.rc != 0) { fs.unlink(tmp); return false; }
	note_persistent_write(path,length(wire));
	return true;
}

function append_line(path, obj) {
	let dir = join('/', slice(split(path, '/'), 0, -1));
	if (!length(dir))
		dir = '/';
	ensure_dir(dir);
	let f = fs.open(path, 'a');
	if (!f)
		return false;
	/* %J is compact single-line JSON. %.J is pretty-printed multi-line JSON
	 * and would corrupt the JSONL reader's one-record-per-line contract. */
	let wire=sprintf('%J\n', obj), n=f.write(wire);
	f.close();
	if (n == null) return false;
	note_persistent_write(path,length(wire));
	return true;
}

function read_lines(path, max_lines) {
	let text = read(path) ?? '';
	let lines = filter(split(text, '\n'), function(x) { return length(trimstr(x)); });
	if (length(lines) > max_lines)
		lines = slice(lines, length(lines) - max_lines);
	let out = [];
	for (let line in lines) {
		try { push(out, json(line)); } catch (e) {}
	}
	return out;
}

function stable_target(runtime) {
	let base = `/sys/class/net/${runtime}`;
	let devlink = fs.realpath(`${base}/device`);
	let driverlink = fs.realpath(`${base}/device/driver`);
	let driver = driverlink ? basename(driverlink) : null;
	let stable = null;
	let evidence = [];

	if (devlink) {
		let parts = split(devlink, '/');
		let bdf = null;
		let vmbus = null;
		for (let p in parts) {
			if (match(p, /^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$/))
				bdf = p;
			if (match(p, /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/))
				vmbus = p;
		}
		if (bdf)
			stable = `nic:pci:${bdf}`;
		else if (vmbus)
			stable = `nic:vmbus:${vmbus}`;
		else
			stable = `nic:device:${basename(devlink)}`;
		push(evidence, { source: 'sysfs-device', value: devlink });
	}

	return {
		schemaVersion: 1,
		stableId: stable,
		kind: 'netdev',
		logicalRole: null,
		selector: {},
		runtimeName: runtime,
		topologyGeneration: topology_generation,
		driver: driver,
		evidence: evidence
	};
}

function netdevs() {
	let out = [];
	for (let p in fs.glob('/sys/class/net/*') ?? []) {
		let name = basename(p);
		let target = stable_target(name);
		let oper = trimstr(read(`${p}/operstate`));
		let type = +trimstr(read(`${p}/type`) ?? '0');
		push(out, {
			name: name,
			operstate: oper || 'unknown',
			type: type,
			mtu: +trimstr(read(`${p}/mtu`) ?? '0'),
			address: trimstr(read(`${p}/address`)),
			driver: target.driver,
			targetRef: target.stableId,
			tunable: target.stableId != null && name != 'lo'
		});
	}
	return out;
}

function stable_ref_for_runtime(runtime) {
	if (!runtime) return null;
	let ref = stable_target(runtime);
	return ref?.stableId ? ref : null;
}

function device_dump() {
	/* netifd device dump carries parent relations (VLAN -> bridge -> L3 ->
	 * physical) that the interface dump omits.  Used to walk a real underlay
	 * chain so a PPPoE/VLAN/tunnel logical interface resolves to the NIC that
	 * actually owns the tunable. */
	try {
		return conn.call('network.device', 'dump', {}) ?? { device: [] };
	}
	catch (e) {
		return { device: [] };
	}
}

function underlay_chain(iface) {
	/* Resolve a logical interface to its real underlay NIC chain.  Walks
	 * logical -> L3 -> VLAN -> bridge -> PPPoE -> tunnel -> physical/virtual
	 * NIC so the affected path points at the device that owns the underlying
	 * tunable, not a synthetic L3 name. */
	let start = iface?.device ?? iface?.l3_device ?? null;
	let devs = device_dump(), parent = {};
	for (let d in devs.device ?? []) {
		let n = d?.name;
		if (!n) continue;
		parent[n] = d?.parent ?? null;
	}
	let chain = [], seen = {}, cur = start;
	while (cur && !seen[cur]) {
		seen[cur] = true;
		push(chain, cur);
		let ref = stable_ref_for_runtime(cur);
		if (ref) return { chain: chain, target: ref };
		cur = parent[cur] ?? null;
	}
	/* No device-parent relation resolved to a stable NIC; accept the direct
	 * device/l3_device only if it maps to a stable device. */
	let direct = stable_ref_for_runtime(start);
	if (direct) return { chain: start ? [ start ] : [], target: direct };
	return { chain: chain, target: null };
}

function interface_underlay_ref(iface) {
	if (!iface) return null;
	return underlay_chain(iface)?.target ?? null;
}

function push_unique_wl(dst, value) {
	if (index(dst, value) < 0) push(dst, value);
}

function device_type_map() {
	/* netifd device dump carries the device TYPE (bridge/vlan/tunnel/wireless/
	 * ppp/...), which is the runtime-shaped evidence used to classify a path
	 * instead of guessing from interface names. */
	let devs = device_dump(), m = {};
	for (let d in devs.device ?? []) if (d?.name) m[d.name] = d?.type ?? null;
	return m;
}

function interface_dump() {
	try {
		return conn.call('network.interface', 'dump', {}) ?? { interface: [] };
	}
	catch (e) {
		return { interface: [] };
	}
}

function route_row_matches_devices(row, devices) {
	if (!row) return false;
	if (index(devices, row.dev ?? '') >= 0) return true;
	for (let nh in row.nexthops ?? []) if (index(devices, nh.dev ?? '') >= 0) return true;
	return false;
}

function json_rows(text) {
	try {
		let rows=json(text ?? '[]');
		return rows ?? [];
	} catch (e) { return []; }
}

function canonical_rows(rows) {
	let encoded=map(rows,function(r){return sprintf('%.J',r);}); sort(encoded); return encoded;
}

function wan_candidates_evidence() {
	/* Derive real WAN candidates from runtime route/rule evidence, not from
	 * interface NAME patterns.  A custom interface (isp-b, fiber, backup,
	 * lte_uplink, wwan, ...) is a WAN because a default/policy route or a
	 * policy-routing rule references its device, not because it matches
	 * `wan[0-9]+`.  Minimal images without ip route evidence fall back to an
	 * explicit `wan`/`wan-N` name only as a last resort. */
	let dump = interface_dump(), by_dev = {};
	for (let i in dump.interface ?? []) {
		for (let d in [ i.device, i.l3_device ]) {
			if (!d) continue;
			by_dev[d] = by_dev[d] ?? [];
			if (index(by_dev[d], i.interface) < 0) push(by_dev[d], i.interface);
		}
	}
	let route_devs = {};
	for (let rows in [ json_rows(run([ 'ip', '-j', '-4', 'route', 'show', 'table', 'all', 'default' ]).out),
	                   json_rows(run([ 'ip', '-j', '-6', 'route', 'show', 'table', 'all', 'default' ]).out) ]) {
		for (let r in rows) {
			let devs = r.dev ? [ r.dev ] : [];
			for (let nh in r.nexthops ?? []) if (nh.dev) push(devs, nh.dev);
			for (let d in devs) if (d) route_devs[d] = true;
		}
	}
	for (let rows in [ json_rows(run([ 'ip', '-j', '-4', 'rule', 'show' ]).out),
	                   json_rows(run([ 'ip', '-j', '-6', 'rule', 'show' ]).out) ]) {
		for (let r in rows) {
			for (let k in [ 'oif', 'iif', 'dev' ]) if (r[k]) route_devs[r[k]] = true;
		}
	}
	let out = [], seen = {};
	for (let d in keys(route_devs)) {
		for (let name in by_dev[d] ?? []) {
			if (seen[name]) continue;
			seen[name] = true;
			for (let i in dump.interface ?? []) if (i.interface == name) { push(out, i); break; }
		}
	}
	return out;
}

function wan_underlay_devices() {
	/* Devices that underlay a real WAN candidate, derived from route/rule
	 * evidence so a custom-named WAN (isp-b, fiber, ...) is classified as
	 * wan-underlay rather than falling through to physical-underlay. */
	let devs = {};
	for (let w in wan_candidates_evidence())
		for (let d in [ w.device, w.l3_device ]) if (d) devs[d] = true;
	return devs;
}

function target_refs() {
	let refs = [];
	let topo = interface_dump();
	let roles = {};
	let runtime_interfaces = {};
	for (let iface in topo.interface ?? []) {
		/* A logical L3 device (e.g. pppoe-wan) is not necessarily the NIC
		 * that owns a device-scoped knob.  Record both identities and later
		 * only attach the role to netdevs that resolve to a stable device. */
		for (let runtime in [ iface.device, iface.l3_device ]) {
			if (!runtime) continue;
			let role = iface.interface;
			/* Prefer WAN/LAN role over a weaker role if aliases overlap. */
			if (!roles[runtime] || role == 'wan' || role == 'lan' || match(role ?? '', /^wan[0-9]*$/))
				roles[runtime] = role;
			/* Keep the owning interface name so a WAN/LAN underlay ref can be
			 * matched back to its logical interface without guessing names. */
			if (!runtime_interfaces[runtime])
				runtime_interfaces[runtime] = [];
			if (index(runtime_interfaces[runtime], role) < 0)
				push(runtime_interfaces[runtime], role);
		}
	}
	let wan_devs = wan_underlay_devices();
	for (let d in netdevs()) {
		if (!d.targetRef)
			continue;
		let r = stable_target(d.name);
		let ifrole = roles[d.name];
		if (wan_devs[d.name] || ifrole == 'wan' || match(ifrole ?? '', /^wan[0-9]*$/))
			r.logicalRole = 'wan-underlay';
		else if (ifrole == 'lan')
			r.logicalRole = 'lan-underlay';
		else
			r.logicalRole = 'physical-underlay';
		/* Selector must be consistent with the WAN fallback join: the same
		 * key (interface) used by topology() to match a target back to its
		 * logical WAN, so a non-default WAN is never picked by name guess. */
		r.selector = { deviceRole: r.logicalRole, interface: runtime_interfaces[d.name]?.[0] ?? null, device: d.name };
		push(refs, r);
	}
	return refs;
}

function resolve_target(stable_id) {
	for (let r in target_refs())
		if (r.stableId == stable_id)
			return r;
	return null;
}

function integration_present(name) {
	return file_exists(`/etc/config/${name}`) || file_exists(`/etc/init.d/${name}`);
}

function integration_state() {
	let state = {
		openclash: integration_present('openclash'),
		passwall: integration_present('passwall') || integration_present('passwall2'),
		homeproxy: integration_present('homeproxy'),
		sqm: integration_present('sqm'),
		qosify: integration_present('qosify'),
		mwan3: integration_present('mwan3'),
		pbr: integration_present('pbr'),
		wireguard: length(fs.glob('/sys/module/wireguard') ?? []) > 0 || integration_present('wireguard'),
		openvpn: integration_present('openvpn'),
		docker: integration_present('dockerd') || file_exists('/var/run/docker.sock')
	};
	state.transparentProxy = state.openclash || state.passwall || state.homeproxy;
	return state;
}

function derive_workload(entry) {
	/* Workload Class is derived from the CURRENT path's own evidence, never
	 * from global system state.  A globally-installed VPN must NOT label an
	 * unrelated plain WAN path as vpn_tunnel: a path is vpn_tunnel only when
	 * it actually traverses a tunnel device/proto.  wireless is decided by the
	 * netifd device type (or sysfs), not by a `wlan` name.  storage_service is
	 * not guessed from device NAMES (ethN-swp / storage): there is no reliable
	 * storage-bound workload evidence here, so it is deliberately not emitted
	 * rather than guessed. */
	let wl = [];
	let proto = entry?.proto ?? null;
	let chain = entry?.underlayChain ?? [];
	let types = device_type_map();
	let is_tunnel = index([ 'wireguard', 'openvpn', 'gre', 'gretap', 'vti', 'sit', 'ip6tnl', 'tun', 'pptp' ], proto ?? '') >= 0;
	for (let name in chain) {
		let t = types[name] ?? '';
		if (index([ 'wireguard', 'tun', 'tunnel', 'gre', 'gretap', 'vti', 'sit', 'ip6tnl' ], t) >= 0) is_tunnel = true;
		if (t == 'wireless') push_unique_wl(wl, 'wireless');
	}
	if (proto == 'pppoe') push_unique_wl(wl, 'pppoe');
	if (is_tunnel) push_unique_wl(wl, 'vpn_tunnel');
	if (entry?.id == 'path:local-endpoint') push_unique_wl(wl, 'local_endpoint');
	/* transparent_proxy is a system-wide policy signal: every forwarding path
	 * traverses the proxy, so it is deliberately not path-specific. */
	if (integration_state().transparentProxy) push_unique_wl(wl, 'transparent_proxy');
	if (!length(wl)) push_unique_wl(wl, 'plain_forwarding');
	return wl;
}

function masked_uci_digest(name, masked_keys) {
	let r = run([ 'uci', 'show', name ]);
	if (r.rc != 0) return null;
	let rows = [];
	for (let line in split(r.out, '\n')) {
		let t = trimstr(line);
		if (!length(t)) continue;
		let masked = false;
		for (let key in masked_keys ?? [])
			if (substr(t, 0, length(key)) == key) { masked = true; break; }
		push(rows, masked ? `${split(t, '=')[0] ?? t}=<benchmark-controlled>` : t);
	}
	if (!length(rows)) return null;
	return `${name}:${fnv1a32(join('\n', rows))}`;
}

function benchmark_masked_keys(action_id) {
	/* A fastpath A/B candidate itself mutates these UCI keys; they must not
	 * create a false integration-drift between control and candidate.  Every
	 * other observed UCI value stays part of the fingerprint.
	 * The live nft ruleset is NOT masked (Blocker B): the extra
	 * 'fastpath-expected-delta' marker tells the benchmark context that the
	 * nft component must be verified by EXACT expected delta (nft_comparable)
	 * instead of being folded into the fingerprint, so only the candidate's
	 * own flowtable/flow-rule toggle is allowed to differ. */
	if (action_id == 'fastpath.software_flow_offload' || action_id == 'fastpath.hardware_flow_offload')
		return [ 'firewall.@defaults[0].flow_offloading', 'firewall.@defaults[0].flow_offloading_hw', 'fastpath-expected-delta' ];
	return [];
}

/* -- Expected Delta (Blocker B) -------------------------------------------
 * fastpath A/B attribution no longer uses a global "ignore all flowtable/flow
 * rule" mask, which also hid unrelated external changes.  Instead the control
 * and candidate nft rulesets are structurally compared and the delta must be
 * EXACTLY the PM candidate's own flowtable/flow-rule toggle.  Anything else
 * (an unrelated rule, a second flowtable, an in-place mutation of the PM
 * flowtable/rule) invalidates the experiment (fail-closed). */

/* Exact identity of the ONLY nft structures a firewall4 fastpath candidate is
 * allowed to toggle.  Everything else must stay byte-identical across the
 * control/candidate snapshots. */
const FASTPATH_FLOWTABLE = { family: 'inet', table: 'fw4', name: 'ft' };
const FASTPATH_FLOW_RULE  = { family: 'inet', table: 'fw4', chain: 'forward', ref: '@ft' };

function nft_item_matches_spec(item, spec) {
	/* Does one parsed nft element match the exact PM fastpath structure?
	 * `spec` is 'flowtable' (exact family/table/name) or 'flowrule' (exact
	 * family/table/chain + `flow add @ft`).  Structural content beyond the
	 * identity is intentionally NOT matched, so an in-place mutation of the PM
	 * flowtable/rule surfaces as a delta instead of being silently accepted. */
	let t = type(item);
	let kind = (t == 'object' && length(keys(item))) ? keys(item)[0] : null;
	if (spec == 'flowtable') {
		if (kind != 'flowtable') return false;
		let ft = item.flowtable ?? {};
		return ft.family == FASTPATH_FLOWTABLE.family && ft.table == FASTPATH_FLOWTABLE.table && ft.name == FASTPATH_FLOWTABLE.name;
	}
	if (spec == 'flowrule') {
		if (kind != 'rule') return false;
		let r = item.rule ?? {};
		if (r.family != FASTPATH_FLOW_RULE.family || r.table != FASTPATH_FLOW_RULE.table || r.chain != FASTPATH_FLOW_RULE.chain) return false;
		return (r.flow?.add ?? null) == FASTPATH_FLOW_RULE.ref;
	}
	return false;
}

function nft_canon(value) {
	/* Canonical structural serialization of one nft item.  Volatile identity
	 * (handle) and live counters (packets/bytes) are dropped so the snapshot
	 * reflects topology, not transient traffic or allocation order. */
	let t = type(value);
	if (t == 'object') {
		let parts = [], ks = keys(value);
		sort(ks);
		for (let k in ks) {
			if (k == 'handle' || k == 'packets' || k == 'bytes') continue;
			push(parts, sprintf('%s=%s', k, nft_canon(value[k])));
		}
		return sprintf('{%s}', join(',', parts));
	}
	if (t == 'array') {
		let parts = [];
		for (let v in value) push(parts, nft_canon(v));
		sort(parts);
		return sprintf('[%s]', join(',', parts));
	}
	if (t == 'number') return sprintf('%d', value);
	if (t == 'bool') return value ? 'true' : 'false';
	if (t == 'null' || t == 'undefined') return 'null';
	return sprintf('"%s"', value);
}

function nft_item_in(list, item) {
	let canon = nft_canon(item);
	for (let it in list) if (nft_canon(it) == canon) return true;
	return false;
}

function nft_delta_is_expected(control, candidate) {
	/* Structural delta between two parsed nft element arrays (metainfo
	 * dropped).  ok == true ONLY when the delta is exactly the PM flowtable
	 * `ft` + `flow add @ft` rule toggled on one side (add or remove), with no
	 * unrelated change and no in-place mutation of those structures. */
	let added = [], removed = [];
	for (let c in candidate) if (!nft_item_in(control, c)) push(added, c);
	for (let c in control) if (!nft_item_in(candidate, c)) push(removed, c);
	let ft_added = 0, rule_added = 0, ft_removed = 0, rule_removed = 0, unrelated = [];
	for (let it in added) {
		if (nft_item_matches_spec(it, 'flowtable')) ft_added++;
		else if (nft_item_matches_spec(it, 'flowrule')) rule_added++;
		else push(unrelated, sprintf('added:%s', nft_canon(it)));
	}
	for (let it in removed) {
		if (nft_item_matches_spec(it, 'flowtable')) ft_removed++;
		else if (nft_item_matches_spec(it, 'flowrule')) rule_removed++;
		else push(unrelated, sprintf('removed:%s', nft_canon(it)));
	}
	let add_side = ft_added + rule_added, rm_side = ft_removed + rule_removed;
	let ok = length(unrelated) == 0 &&
		((add_side == 2 && rm_side == 0 && ft_added == 1 && rule_added == 1) ||
		 (rm_side == 2 && add_side == 0 && ft_removed == 1 && rule_removed == 1));
	return { ok: ok, added: map(added, nft_canon), removed: map(removed, nft_canon), unrelated: unrelated };
}

function nft_comparable(control_snapshot, candidate_snapshot) {
	/* Expected-delta comparability for controlled fastpath A/B.  The control
	 * and candidate snapshots must differ by EXACTLY the PM flowtable/flow-rule
	 * toggle.  If either snapshot is unavailable, the experiment FAILS CLOSED
	 * (not comparable) rather than guessing. */
	let a = control_snapshot ?? null, b = candidate_snapshot ?? null;
	if (a == null || b == null) return { comparable: false, reason: 'nft-snapshot-unavailable', control: a, candidate: b };
	let d = nft_delta_is_expected(a.parsed ?? [], b.parsed ?? []);
	return { comparable: d.ok, reason: d.ok ? 'expected-delta' : 'unexpected-nft-delta', delta: d };
}

function queue_topology() {
	let out = [];
	for (let d in netdevs()) {
		if (!d.targetRef) continue;
		push(out, {
			runtimeName: d.name, targetRef: d.targetRef,
			rxQueues: length(fs.glob(`/sys/class/net/${d.name}/queues/rx-*`) ?? []),
			txQueues: length(fs.glob(`/sys/class/net/${d.name}/queues/tx-*`) ?? [])
		});
	}
	return out;
}

function packet_steering_capability() {
	let service = file_exists('/etc/init.d/packet_steering');
	let generic = file_exists('/usr/libexec/network/packet-steering.uc');
	let platform = file_exists('/usr/libexec/platform/packet-steering.sh');
	let mode_r = run([ 'uci', '-q', 'get', 'network.@globals[0].packet_steering' ]);
	let flows_r = run([ 'uci', '-q', 'get', 'network.@globals[0].steering_flows' ]);
	let mode = mode_r.rc == 0 ? trimstr(mode_r.out) : null;
	let flows = flows_r.rc == 0 ? +trimstr(flows_r.out) : 0;
	return {
		schemaVersion: 2,
		id: 'network.packet_steering.native',
		domain: 'network',
		provider: 'openwrt-netifd',
		availability: service && (generic || platform) ? 'available' : 'unavailable',
		scope: 'service',
		targetRef: null,
		confidence: service ? 'high' : 'medium',
		adjustable: false,
		dynamic: true,
		active: mode != null && mode != '0',
		evidence: [{
			source: 'openwrt-native-packet-steering',
			observed: {
				nativeServiceAvailable: service,
				genericProviderAvailable: generic,
				platformOverrideAvailable: platform,
				currentMode: mode,
				steeringFlows: flows
			}
		}],
		ownership: mode != null ? 'preexisting' : 'unknown',
		policy: 'observe-respect'
	};
}

function ethtool_ring(runtime) {
	if (!file_exists('/usr/sbin/ethtool') && !file_exists('/usr/bin/ethtool'))
		return null;
	let r = run([ 'ethtool', '-g', runtime ]);
	if (r.rc != 0)
		return null;
	let lines = split(r.out, '\n');
	let section = '';
	let max_rx = null, max_tx = null, cur_rx = null, cur_tx = null;
	for (let line in lines) {
		if (match(line, /^Pre-set maximums:/)) { section = 'max'; continue; }
		if (match(line, /^Current hardware settings:/)) { section = 'cur'; continue; }
		let m = match(line, /^RX:\s*([0-9]+)/);
		if (m) { if (section == 'max') max_rx = +m[1]; else if (section == 'cur') cur_rx = +m[1]; continue; }
		m = match(line, /^TX:\s*([0-9]+)/);
		if (m) { if (section == 'max') max_tx = +m[1]; else if (section == 'cur') cur_tx = +m[1]; continue; }
	}
	if (max_rx == null && max_tx == null)
		return null;
	return { rxCurrent: cur_rx, rxMax: max_rx, txCurrent: cur_tx, txMax: max_tx };
}

function read_pair(path) {
	let p = filter(split(trimstr(read(path) ?? ''), /\s+/), function(x) { return length(x); });
	if (length(p) < 2) return null;
	return [ +p[0], +p[1] ];
}

function port_capacity_capability() {
	let range = read_pair('/proc/sys/net/ipv4/ip_local_port_range');
	let reserved = trimstr(read('/proc/sys/net/ipv4/ip_local_reserved_ports'));
	let count = +trimstr(read('/proc/sys/net/netfilter/nf_conntrack_count') ?? '0');
	let maxct = +trimstr(read('/proc/sys/net/netfilter/nf_conntrack_max') ?? '0');
	return {
		schemaVersion: 2, id: 'network.local_port_capacity', domain: 'network', provider: 'linux-sysctl',
		availability: range ? 'available' : 'unavailable', scope: 'system', targetRef: null,
		confidence: range ? 'high' : 'medium', adjustable: range != null, dynamic: true, active: range != null,
		evidence: [{ source: 'procfs', observed: {
			localPortRange: range, reservedPorts: reserved || null, conntrackCount: count,
			conntrackMax: maxct, conntrackPressure: maxct > 0 ? count / maxct : null
		} }], ownership: 'preexisting', policy: 'conditional-capacity-benchmark-only'
	};
}

function wireless_capability() {
	let radios = fs.glob('/sys/class/ieee80211/*') ?? [];
	let iw = file_exists('/usr/sbin/iw') || file_exists('/usr/bin/iw');
	let detail = null;
	if (iw) {
		let r = run([ 'iw', 'dev' ]);
		if (r.rc == 0) detail = r.out;
	}
	return {
		schemaVersion: 2, id: 'wireless.observe', domain: 'wireless', provider: 'nl80211/iw',
		availability: length(radios) > 0 ? 'available' : 'unavailable', scope: 'radio', targetRef: null,
		confidence: length(radios) > 0 ? 'high' : 'medium', adjustable: false, dynamic: true,
		active: length(radios) > 0, evidence: [{ source: 'sysfs+iw', observed: { radioCount: length(radios), iwAvailable: iw, iwDev: detail } }],
		policy: 'observe-analyze; channel/width/txpower require explicit benchmark'
	};
}

function fastpath_capability() {
	let sw = run([ 'uci', '-q', 'get', 'firewall.@defaults[0].flow_offloading' ]);
	let hw = run([ 'uci', '-q', 'get', 'firewall.@defaults[0].flow_offloading_hw' ]);
	let swv = sw.rc == 0 ? trimstr(sw.out) : null;
	let hwv = hw.rc == 0 ? trimstr(hw.out) : null;
	let sfe = file_exists('/etc/init.d/turboacc') || file_exists('/etc/config/turboacc') || file_exists('/sys/module/shortcut_fe');
	return {
		schemaVersion: 2, id: 'fastpath.firewall', domain: 'network', provider: 'firewall4/external',
		availability: (swv != null || hwv != null || sfe) ? 'available' : 'unknown', scope: 'service', targetRef: null,
		confidence: (swv != null || hwv != null) ? 'high' : 'medium', adjustable: false, dynamic: true,
		active: swv == '1' || hwv == '1' || sfe, evidence: [{ source: 'uci/module', observed: { softwareFlowOffload: swv, hardwareFlowOffload: hwv, thirdPartySfeDetected: sfe } }],
		ownership: (swv != null || hwv != null || sfe) ? 'preexisting' : 'unknown', policy: 'observe; benchmark-only; functional-correctness-hard-fail'
	};
}

function kernel_benchmark_capability() {
	let observed = {
		netdevMaxBacklog: trimstr(read('/proc/sys/net/core/netdev_max_backlog')) || null,
		netdevBudget: trimstr(read('/proc/sys/net/core/netdev_budget')) || null,
		netdevBudgetUsecs: trimstr(read('/proc/sys/net/core/netdev_budget_usecs')) || null,
		rmemMax: trimstr(read('/proc/sys/net/core/rmem_max')) || null,
		wmemMax: trimstr(read('/proc/sys/net/core/wmem_max')) || null,
		busyPoll: trimstr(read('/proc/sys/net/core/busy_poll')) || null,
		busyRead: trimstr(read('/proc/sys/net/core/busy_read')) || null,
		tcpCongestionControl: trimstr(read('/proc/sys/net/ipv4/tcp_congestion_control')) || null,
		tcpAvailableCongestionControl: trimstr(read('/proc/sys/net/ipv4/tcp_available_congestion_control')) || null,
		irqbalanceInstalled: file_exists('/etc/init.d/irqbalance') || file_exists('/usr/sbin/irqbalance')
	};
	return {
		schemaVersion: 2, id: 'benchmark.kernel-network', domain: 'network', provider: 'linux-kernel',
		availability: 'available', scope: 'system', targetRef: null, confidence: 'high', adjustable: false,
		dynamic: true, active: true, evidence: [{ source: 'procfs+service', observed: observed }],
		policy: 'discover-only-until-explicit-controlled-ab'
	};
}

function capabilities() {
	let caps = [ packet_steering_capability(), port_capacity_capability(), fastpath_capability(), kernel_benchmark_capability(), wireless_capability() ];
	for (let ref in target_refs()) {
		let ring = ethtool_ring(ref.runtimeName);
		if (ring) {
			push(caps, {
				schemaVersion: 2,
				id: 'nic.ring', domain: 'nic', provider: 'driver-ethtool', availability: 'available',
				scope: 'device', targetRef: ref.stableId, confidence: 'high', adjustable: true,
				dynamic: true, active: true,
				evidence: [{ source: `ethtool -g ${ref.runtimeName}`, observed: ring }]
			});
		}
		let off = run([ 'ethtool', '-k', ref.runtimeName ]);
		if (off.rc == 0)
			push(caps, {
				schemaVersion: 2,
				id: 'nic.offload', domain: 'nic', provider: 'driver-ethtool', availability: 'available',
				scope: 'device', targetRef: ref.stableId, confidence: 'high', adjustable: false,
				dynamic: true, active: true,
				evidence: [{ source: `ethtool -k ${ref.runtimeName}`, observed: { protected: true } }],
				policy: 'observe-protect-preexisting'
			});
		let coal = run([ 'ethtool', '-c', ref.runtimeName ]);
		if (coal.rc == 0)
			push(caps, {
				schemaVersion: 2, id: 'nic.coalescing', domain: 'nic', provider: 'driver-ethtool', availability: 'available',
				scope: 'device', targetRef: ref.stableId, confidence: 'high', adjustable: false, dynamic: true, active: true,
				evidence: [{ source: `ethtool -c ${ref.runtimeName}`, observed: { discovered: true } }], policy: 'benchmark-only'
			});
	}
	return { schemaVersion: SCHEMA_VERSION, topologyGeneration: topology_generation, capabilities: caps };
}

function capability_hash(snapshot) {
	let rows=[];
	/* Hash capability identity and availability, not mutable active state. A
	 * benchmark is allowed to change active configuration without creating a
	 * false capability-drift event. */
	for (let c in snapshot?.capabilities ?? [])
		push(rows,sprintf('%s|%s|%s|%s|%s',c.id ?? '',c.targetRef ?? '',c.provider ?? '',c.availability ?? '',c.adjustable ? '1':'0'));
	return stable_list_hash('fnv1a32',rows);
}

function meminfo() {
	let map = {};
	for (let line in split(read('/proc/meminfo') ?? '', '\n')) {
		let m = match(line, /^([A-Za-z_()]+):\s+([0-9]+)/);
		if (m) map[m[1]] = +m[2];
	}
	return map;
}

function cpu_stat() {
	let lines = split(read('/proc/stat') ?? '', '\n');
	let line = lines[0] ?? '';
	let p = filter(split(line, /\s+/), function(x) { return length(x); });
	let count = 0;
	for (let row in lines)
		if (match(row, /^cpu[0-9]+\s/)) count++;
	if (length(p) < 9)
		return { stealPct: 0, total: 0, count: max(1, count) };
	let nums = map(slice(p, 1), function(x) { return +x; });
	let total = 0;
	for (let n in nums) total += n;
	let steal = nums[7] ?? 0;
	return { stealPct: total > 0 ? steal / total : 0, total: total, count: max(1, count) };
}

function service_running(name) {
	let script = `/etc/init.d/${name}`;
	if (!file_exists(script)) return null;
	return run([ script, 'running' ]).rc == 0;
}

function integration_fingerprint(masked_keys, nft) {
	/* Canonical context fingerprint: installed-boolean detection (the old
	 * integration_state) is NOT evidence of unchanged runtime behavior, so the
	 * fingerprint adds per-service running state, UCI config digests and the
	 * live ip rule policy set (PBR/mwan3/policy routing surfaces). */
	let rows = [];
	for (let name in [ 'openclash', 'passwall', 'passwall2', 'homeproxy', 'sqm', 'qosify', 'mwan3', 'pbr', 'openvpn' ]) {
		if (!integration_present(name)) continue;
		let running = service_running(name);
		push(rows, `svc:${name}:${running == null ? 'na' : running ? '1' : '0'}`);
	}
	for (let name in [ 'openclash', 'passwall', 'passwall2', 'homeproxy', 'sqm', 'qosify', 'mwan3', 'pbr', 'firewall' ]) {
		if (!file_exists(`/etc/config/${name}`)) continue;
		let d = masked_uci_digest(name, masked_keys);
		if (d != null) push(rows, `cfg:${d}`);
	}
	let rules = run([ 'ip', '-j', 'rule', 'show' ]);
	if (rules.rc == 0 && length(trimstr(rules.out)))
		push(rows, `rules:${fnv1a32(join('|', canonical_rows(json_rows(rules.out))))}`);
	/* Live firewall/route fingerprint (9.6): a file hash of /etc/config/firewall
	 * is not evidence of an unchanged running ruleset.  Add the FULL canonical
	 * structural identity of the live nft ruleset (no flow mask, Blocker B) so
	 * control/candidate drift in the running firewall is detected.  Fastpath
	 * sessions pass an explicit snapshot and verify it by expected delta in
	 * nft_comparable; they pass `null` here so the nft row is not folded into
	 * the raw fingerprint (the candidate legitimately toggles the flowtable).
	 * ucode has no distinct `undefined` value and no arity introspection in
	 * strict mode, so the caller ALWAYS supplies the snapshot explicitly: a
	 * real snapshot (or `null` when nft is unavailable) to fold the nft row in,
	 * or `null` to suppress it (fastpath Blocker B sessions). */
	if (nft != null && length(nft.items)) push(rows, `nft:${fnv1a32(nft.canonical)}`);
	return `integ-v1:${fnv1a32(join('\n', rows))}`;
}

function proxy_health() {
	let integ = integration_state();
	if (!integ.transparentProxy) return null;
	let seen = false;
	for (let name in [ 'openclash', 'passwall', 'passwall2', 'homeproxy' ]) {
		if (!integration_present(name)) continue;
		let running = service_running(name);
		if (running == null) continue;
		seen = true;
		if (running) return true;
	}
	return seen ? false : null;
}

function vpn_health() {
	let integ = integration_state();
	if (!integ.wireguard && !integ.openvpn) return null;
	if (integ.openvpn) {
		let running = service_running('openvpn');
		if (running != null) return running;
	}
	/* WireGuard is commonly interface-managed rather than a procd service.
	 * Presence of an up WireGuard interface is therefore the relevant signal. */
	for (let i in interface_dump().interface ?? [])
		if ((i.proto ?? '') == 'wireguard') return i.up ?? false;
	return null;
}

function thermal_health() {
	let max_temp = null;
	for (let p in fs.glob('/sys/class/thermal/thermal_zone*/temp') ?? []) {
		let v = +trimstr(read(p) ?? '0');
		if (v > 0 && (max_temp == null || v > max_temp)) max_temp = v;
	}
	let throttle = 0;
	for (let p in fs.glob('/sys/devices/system/cpu/cpu*/thermal_throttle/*_throttle_count') ?? [])
		throttle += +trimstr(read(p) ?? '0');
	return { available: max_temp != null, maxMilliCelsius: max_temp, throttleCount: throttle };
}

function storage_writable(path) {
	ensure_dir(path);
	return fs.access(path, 'w') ? true : false;
}

function recent_oom_state() {
	let r = run([ 'logread', '-e', 'Out of memory' ]);
	if (r.rc != 0) return false;
	let text = trimstr(r.out);
	let signature = fnv1a32(text);
	let path = `${state_dir()}/health/oom-state.json`;
	let prev = json_read(path, null);
	let now = monotonic_ms();
	let window = max(60, int_cfg('main.oom_window_seconds', 600)) * 1000;
	if (!length(text)) {
		json_write(path, { signature: signature, lastNewMonotonicMs: null });
		return false;
	}
	let last = prev?.lastNewMonotonicMs ?? null;
	if (!prev || prev.signature != signature) last = now;
	json_write(path, { signature: signature, lastNewMonotonicMs: last });
	return last != null && now - last <= window;
}

function compare_health(before, after) {
	let failures = [];
	for (let key in [ 'lan', 'wan', 'dns', 'ipv4', 'ipv6', 'proxy', 'vpn', 'route' ]) {
		if (before[key] === true && after[key] !== true)
			push(failures, `${key}:healthy-to-unhealthy`);
	}
	if ((before.memAvailableKiB ?? 0) > 0 && (after.memAvailableKiB ?? 0) < 8192)
		push(failures, 'memory:critical');
	if (!before.recentOom && after.recentOom)
		push(failures, 'oom:new');
	if (before.thermal?.throttleCount != null && after.thermal?.throttleCount > before.thermal.throttleCount)
		push(failures, 'thermal:new-throttle');
	return { pass: length(failures) == 0, failures: failures };
}

function softnet() {
	let processed = 0, dropped = 0, squeezed = 0;
	for (let line in split(read('/proc/net/softnet_stat') ?? '', '\n')) {
		let p = filter(split(trimstr(line), /\s+/), function(x) { return length(x); });
		if (length(p) >= 3) {
			processed += +`0x${p[0]}`;
			dropped += +`0x${p[1]}`;
			squeezed += +`0x${p[2]}`;
		}
	}
	return { processed: processed, dropped: dropped, timeSqueezed: squeezed };
}

function platform_info() {
	let hv = false, kvm = false;
	for (let r in target_refs()) if (r.driver == 'hv_netvsc') hv = true;
	let product = trimstr(read('/sys/class/dmi/id/product_name'));
	let vendor = trimstr(read('/sys/class/dmi/id/sys_vendor'));
	if (match(lc(vendor), /microsoft/) || match(lc(product), /virtual machine/)) hv = true;
	if (match(lc(vendor), /qemu|red hat/) || match(lc(product), /kvm|qemu/)) kvm = true;
	let arch_r = run([ 'uname', '-m' ]);
	let arch = arch_r.rc == 0 ? trimstr(arch_r.out) : null;
	let virt = hv ? 'hyperv' : (kvm ? 'kvm' : 'generic');
	return {
		architecture: arch, virtualization: virt, hyperv: hv, kvm: kvm,
		kvmProxmoxCompatible: kvm,
		dmi: { sysVendor: vendor || null, productName: product || null },
		hostRecommendations: hv ? [ 'Enable sufficient vCPU count and Hyper-V vRSS/VMMQ on the host when available.' ] :
			(kvm ? [ 'For KVM/Proxmox VE guests, align virtio-net multiqueue with guest vCPU topology when the host supports it.' ] : [])
	};
}

function benchmark_semantics(action_id) {
	if (index([ 'network.buffers', 'network.busy_poll', 'tcp.cc', 'qdisc.replace' ], action_id) >= 0) return 'local';
	return 'forwarding';
}

function policy_owned(stable_id, action_id) {
	let p = `${persist_dir()}/policies/${safe_name(stable_id)}.${safe_name(action_id)}.json`;
	return json_read(p, null);
}

function lock_path(resource) {
	return `${state_dir()}/locks/${safe_name(resource)}.json`;
}

function acquire_locks(resources, txid) {
	ensure_dir(`${state_dir()}/locks`);
	let acquired = [];
	for (let r in resources) {
		let p = lock_path(r);
		let existing = json_read(p, null);
		if (existing && existing.bootId == boot_id() && existing.transactionId != txid) {
			for (let a in acquired) fs.unlink(lock_path(a));
			return { ok: false, conflict: r, holder: existing };
		}
		let lock = { schemaVersion: 1, resource: r, transactionId: txid, bootId: boot_id(), acquiredMonotonicMs: monotonic_ms() };
		if (!json_write(p, lock)) {
			for (let a in acquired) fs.unlink(lock_path(a));
			return { ok: false, conflict: r, holder: null };
		}
		push(acquired, r);
	}
	return { ok: true, resources: acquired };
}

function release_locks(resources, txid) {
	for (let r in resources ?? []) {
		let p = lock_path(r);
		let cur = json_read(p, null);
		if (!cur || cur.transactionId == txid)
			fs.unlink(p);
	}
}

function tx_path(txid) {
	return `${state_dir()}/transactions/${safe_name(txid)}.json`;
}

function pending_marker_path(txid) {
	return `${persist_dir()}/pending/${safe_name(txid)}.json`;
}

function tx_is_active(tx) {
	return index([ 'pending', 'applied', 'verified', 'awaiting_confirm' ], tx?.state) >= 0;
}

function tx_save(tx) {
	/* Active transactions are safety-critical. Persist the durable marker
	 * before the tmpfs journal so a crash or tmpfs write failure can never
	 * erase the only recovery evidence after state mutation. Terminal states
	 * do the inverse: journal the terminal decision before removing the marker. */
	ensure_dir(`${persist_dir()}/pending`);
	tx.updatedMonotonicMs = monotonic_ms();
	let marker = pending_marker_path(tx.transactionId), active = tx_is_active(tx);
	tx.pendingMarker = active ? marker : null;
	if (active) {
		if (!json_write(marker, tx)) return false;
		if (!json_write(tx_path(tx.transactionId), tx)) return false;
	} else {
		if (!json_write(tx_path(tx.transactionId), tx)) return false;
		fs.unlink(marker);
	}
	return true;
}

function cancel_tx_timer(txid) {
	let t = tx_timers[txid];
	if (t) t.cancel();
	delete tx_timers[txid];
}

function compact_jsonl(path, limit) {
	let rows = read_lines(path, limit + 32);
	if (length(rows) <= limit) return;
	rows = slice(rows, length(rows) - limit);
	let text = '';
	for (let row in rows) text += sprintf('%J\n', row);
	if (fs.writefile(path, text) != null) note_persistent_write(path,length(text));
}

function history(event, data) {
	if (!bool_cfg('main.history', true))
		return;
	let path = `${persist_dir()}/history.jsonl`;
	append_line(path, { bootId: boot_id(), monotonicMs: monotonic_ms(), event: event, data: data });
	compact_jsonl(path, MAX_HISTORY_LINES);
}

function runtime_history(event, data) {
	let path = `${state_dir()}/history.jsonl`;
	append_line(path, { bootId: boot_id(), monotonicMs: monotonic_ms(), event: event, data: data });
	compact_jsonl(path, MAX_HISTORY_LINES);
}

function tx_new(action, execution_source, rill_decision) {
	tx_counter++;
	let id = sprintf('tx-%s-%d-%d', substr(boot_id(), 0, 8), monotonic_ms(), tx_counter);
	return {
		schemaVersion: 2, transactionId: id, state: 'planned', actionId: action.id,
		executionSource: execution_source ?? 'manual', rillDecision: rill_decision ?? null,
		applyScope: action.applyScope, applyTarget: action.applyTarget, evaluationPaths: action.evaluationPaths ?? [],
		owner: 'performance_manager', topologyGeneration: topology_generation, bootId: boot_id(),
		before: null, applied: null, requiredLocks: action.requiredLocks ?? [], deadlineMonotonicMs: null,
		commitPolicy: action.commitPolicy ?? null, requiresCommitConfirm: action.requiresCommitConfirm ? true : false,
		pendingMarker: null,
		verification: { readBack: 'pending', healthRegression: 'unknown', commitConfirm: action.requiresCommitConfirm ? 'pending' : 'not_required' },
		result: null
	};
}

function ring_snapshot(ref) {
	return ethtool_ring(ref.runtimeName);
}

function ring_apply(ref, params) {
	let argv = [ 'ethtool', '-G', ref.runtimeName ];
	if (params.rxFloor != null) { push(argv, 'rx'); push(argv, `${params.rxFloor}`); }
	if (params.txFloor != null) { push(argv, 'tx'); push(argv, `${params.txFloor}`); }
	return run(argv);
}

function ring_restore(ref, snap) {
	if (!snap) return { rc: 1, out: 'missing snapshot' };
	let argv = [ 'ethtool', '-G', ref.runtimeName ];
	if (snap.rxCurrent != null) { push(argv, 'rx'); push(argv, `${snap.rxCurrent}`); }
	if (snap.txCurrent != null) { push(argv, 'tx'); push(argv, `${snap.txCurrent}`); }
	return run(argv);
}

function link_ok(ref) {
	let state = trimstr(read(`/sys/class/net/${ref.runtimeName}/operstate`));
	return state == 'up' || state == 'unknown' || state == 'dormant';
}

function ring_matches(ref, expected) {
	let cur = ring_snapshot(ref);
	if (!cur || !expected) return false;
	return (expected.rxCurrent == null || cur.rxCurrent == expected.rxCurrent) &&
		(expected.txCurrent == null || cur.txCurrent == expected.txCurrent);
}

function ring_policy_path(stable_id) {
	return `${persist_dir()}/policies/${safe_name(stable_id)}.nic.ring.floor.json`;
}

function persist_ring_policy(ref, params, transaction_id, before_ring, owned_ring) {
	let policy = {
		schemaVersion: 2, actionId: 'nic.ring.floor', owner: 'performance_manager', ownerTransactionId: transaction_id, targetRef: ref,
		params: params, persistenceClass: 'pm_policy_replay', reapplyTriggers: [ 'boot', 'device_up', 'topology_change' ],
		runtimeLease: {
			bootId: boot_id(), runtimeName: ref.runtimeName, topologyGeneration: topology_generation,
			beforeRing: before_ring ?? null, ownedRing: owned_ring ?? null
		}
	};
	ensure_dir(`${persist_dir()}/policies`);
	return json_write(ring_policy_path(ref.stableId), policy);
}

function sysctl_value(path) {
	let v = trimstr(read(path));
	return length(v) ? v : null;
}

function sysctl_set(path, value) {
	if (!file_exists(path)) return { rc: 1, out: 'sysctl-path-missing' };
	let f = fs.open(path, 'w');
	if (!f) return { rc: 1, out: 'sysctl-open-failed' };
	let n = f.write(`${value}\n`); f.close();
	return { rc: n == null ? 1 : 0, out: n == null ? 'sysctl-write-failed' : '' };
}

function uci_get(path) {
	let r = run([ 'uci', '-q', 'get', path ]);
	return r.rc == 0 ? trimstr(r.out) : null;
}

function uci_set_runtime(path, value) {
	if (value == null) return run([ 'uci', '-q', 'delete', path ]);
	return run([ 'uci', '-q', 'set', `${path}=${value}` ]);
}

function benchmark_provider_apply(plan, value) {
	if (plan.kind == 'sysctl') return sysctl_set(plan.path, value);
	if (plan.kind == 'txqueuelen') return run([ 'ip', 'link', 'set', 'dev', plan.targetRef.runtimeName, 'txqueuelen', `${value}` ]);
	if (plan.kind == 'coalescing') return run([ 'ethtool', '-C', plan.targetRef.runtimeName, 'rx-usecs', `${value}` ]);
	if (plan.kind == 'service') return run([ `/etc/init.d/${plan.service}`, value == 'running' ? 'start' : 'stop' ]);
	if (plan.kind == 'uci-firewall') {
		let r=uci_set_runtime(plan.key, value); if (r.rc != 0) return r;
		return run([ '/etc/init.d/firewall', 'reload' ]);
	}
	if (plan.kind == 'governor') {
		for (let row in plan.rows) {
			let target = value == 'candidate' ? row.candidate : row.before;
			let r=sysctl_set(row.path, target); if (r.rc != 0) return r;
		}
		return { rc:0, out:'' };
	}
	return { rc:1, out:'unsupported-provider-kind' };
}

function benchmark_provider_matches(plan, value) {
	if (plan.kind == 'sysctl') return sysctl_value(plan.path) == `${value}`;
	if (plan.kind == 'txqueuelen') return sysctl_value(`/sys/class/net/${plan.targetRef.runtimeName}/tx_queue_len`) == `${value}`;
	if (plan.kind == 'coalescing') {
		let r=run([ 'ethtool', '-c', plan.targetRef.runtimeName ]), m=match(r.out, /rx-usecs:\s*([0-9]+)/);
		return r.rc == 0 && m && m[1] == `${value}`;
	}
	if (plan.kind == 'service') return (service_running(plan.service) ? 'running' : 'stopped') == value;
	if (plan.kind == 'uci-firewall') { let cur=uci_get(plan.key); return value == null ? cur == null : cur == `${value}`; }
	if (plan.kind == 'governor') {
		for (let row in plan.rows) if (sysctl_value(row.path) != (value == 'candidate' ? row.candidate : row.before)) return false;
		return true;
	}
	return false;
}

function benchmark_restore_transaction(tx, reason) {
	let plan=tx.before?.benchmark;
	if (!plan) return { ok:false, error:'benchmark-snapshot-missing' };
	/* Refuse to overwrite somebody else's same-knob change. */
	let expected = plan.kind == 'governor' ? 'candidate' : plan.candidate;
	if (!benchmark_provider_matches(plan, expected)) return { ok:false, error:'live-state-drift-refuses-stale-rollback' };
	let restore_value = plan.kind == 'governor' ? 'before' : plan.before;
	let r=benchmark_provider_apply(plan, restore_value);
	let restored=r.rc == 0 && benchmark_provider_matches(plan, restore_value);
	if (!restored) return { ok:false, error:'rollback-apply-or-readback-failed', output:r.out ?? '' };
	return { ok:true, reason:reason ?? 'benchmark-rollback' };
}

function transaction_list() {
	let items = [];
	for (let p in fs.glob(`${state_dir()}/transactions/*.json`) ?? []) {
		let tx = json_read(p, null); if (tx) push(items, tx);
	}
	sort(items, function(a,b) { return (b.updatedMonotonicMs ?? 0) - (a.updatedMonotonicMs ?? 0); });
	return items;
}

function lock_list() {
	let items = [];
	for (let p in fs.glob(`${state_dir()}/locks/*.json`) ?? []) {
		let x = json_read(p, null); if (x) push(items, x);
	}
	return items;
}

function clean_stale_locks() {
	for (let p in fs.glob(`${state_dir()}/locks/*.json`) ?? []) {
		let lock = json_read(p, null);
		if (!lock || lock.bootId != boot_id()) { fs.unlink(p); continue; }
		let tx = json_read(tx_path(lock.transactionId), null);
		if (!tx || !tx_is_active(tx)) fs.unlink(p);
	}
}

function recover_persistent_markers() {
	ensure_dir(`${persist_dir()}/pending`);
	for (let p in fs.glob(`${persist_dir()}/pending/*.json`) ?? []) {
		let marker = json_read(p, null);
		if (!marker) { fs.unlink(p); continue; }
		if (marker.bootId != boot_id()) {
			/* Runtime-only and uncommitted UCI deltas reset across reboot. Never
			 * replay a stale snapshot into a newly resolved target. The marker is
			 * durable evidence that recovery happened. */
			history('transaction.boot_recovered', { transactionId: marker.transactionId, actionId: marker.actionId, previousBootId: marker.bootId, state: marker.state, result: { reason: 'boot-recovery-runtime-reset-no-stale-replay' } });
			fs.unlink(p);
			continue;
		}
		let local = json_read(tx_path(marker.transactionId), null);
		if (!local) json_write(tx_path(marker.transactionId), marker);
	}
}

function benchmark_path(id) {
	return `${state_dir()}/benchmarks/${safe_name(id)}.json`;
}

function benchmark_lock_dir() {
	return `${state_dir()}/benchmark-locks`;
}

function benchmark_lock_path(domain) {
	return `${benchmark_lock_dir()}/${safe_name(domain)}.json`;
}

function benchmark_lock_domain(action_id, plan, path_id) {
	/* Active A/B experiments are globally exclusive.  Any two simultaneous
	 * candidates — backlog+budget, irqbalance+governor, or coalescing on two
	 * different NICs — would attribute one throughput delta to two changed
	 * variables and feed a polluted result into Rill.  System/service and
	 * device/path experiments therefore share one experiment domain lock; the
	 * per-resource transaction lock is applied on top at candidate time. */
	return 'benchmark:global';
}

function benchmark_session_active(s) {
	return index([ 'awaiting_control', 'candidate_applied' ], s?.state) >= 0;
}

function benchmark_session_expired(s, now) {
	if (s?.state == 'awaiting_control' && s.createdMonotonicMs != null)
		return now - s.createdMonotonicMs > max(60, int_cfg('benchmark.session_idle_seconds', 600)) * 1000;
	return false;
}

function acquire_benchmark_lock(domain, session_id) {
	ensure_dir(benchmark_lock_dir());
	let p = benchmark_lock_path(domain);
	let existing = json_read(p, null);
	if (existing && existing.bootId == boot_id() && existing.sessionId != session_id)
		return { ok: false, conflict: existing };
	if (!json_write(p, { schemaVersion: 1, domain: domain, sessionId: session_id, bootId: boot_id(), acquiredMonotonicMs: monotonic_ms() }))
		return { ok: false, conflict: null };
	return { ok: true };
}

function release_benchmark_lock(domain, session_id) {
	if (!domain || !session_id) return;
	let p = benchmark_lock_path(domain);
	let cur = json_read(p, null);
	if (!cur || cur.sessionId == session_id)
		fs.unlink(p);
}

function rollback_transaction(txid, reason) {
	let tx = json_read(tx_path(txid), null);
	if (!tx) return { ok: false, error: 'transaction-not-found' };
	if (tx.state == 'rolled_back') return { ok: false, error: 'transaction-already-rolled-back' };
	if (tx.bootId != boot_id()) return { ok: false, error: 'rollback-snapshot-from-different-boot' };
	cancel_tx_timer(tx.transactionId);
	let lock = acquire_locks(tx.requiredLocks ?? [], tx.transactionId);
	if (!lock.ok) return { ok:false, error:'rollback-lock-conflict', detail:lock };
	if (tx.actionId == 'nic.ring.floor' && tx.before?.targetRef && tx.before?.ring) {
		let ref = resolve_target(tx.before.targetRef.stableId);
		if (!ref) { release_locks(tx.requiredLocks,tx.transactionId); return { ok: false, error: 'rollback-target-unresolved' }; }
		if (tx.state == 'committed') {
			let policy = json_read(ring_policy_path(ref.stableId), null);
			if (!policy || policy.owner != 'performance_manager' || policy.ownerTransactionId != tx.transactionId) { release_locks(tx.requiredLocks,tx.transactionId); return { ok: false, error: 'stale-transaction-policy-owner-changed' }; }
			if (tx.result?.ring && !ring_matches(ref, tx.result.ring)) { release_locks(tx.requiredLocks,tx.transactionId); return { ok: false, error: 'live-state-drift-refuses-stale-rollback' }; }
		}
		let r = ring_restore(ref, tx.before.ring);
		let restored = r.rc == 0 && ring_matches(ref, tx.before.ring);
		if (!restored) {
			tx.state = 'failed'; tx.result = { error: 'rollback-apply-or-readback-failed', output: r.out ?? '' };
			tx.verification.rollbackReadBack = 'fail'; tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
			history('transaction.rollback_failed', tx); return { ok: false, transaction: tx };
		}
		let policy = json_read(ring_policy_path(ref.stableId), null);
		if (policy?.ownerTransactionId == tx.transactionId) fs.unlink(ring_policy_path(ref.stableId));
		tx.verification.rollbackReadBack = 'pass';
	} else if (tx.before?.benchmark) {
		let r=benchmark_restore_transaction(tx, reason);
		if (!r.ok) {
			tx.state='failed'; tx.verification.rollbackReadBack='fail'; tx.result={error:r.error,output:r.output ?? '',benchmarkSessionId:tx.result?.benchmarkSessionId ?? tx.applied?.benchmarkSessionId ?? null};
			tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId); history('transaction.rollback_failed',tx); return {ok:false,transaction:tx};
		}
		tx.verification.rollbackReadBack='pass';
	}
	let bench_id=tx.result?.benchmarkSessionId ?? tx.applied?.benchmarkSessionId ?? null;
	tx.state = 'rolled_back'; tx.deadlineMonotonicMs=null; tx.result = { reason: reason ?? 'manual', benchmarkSessionId:bench_id }; tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
	history('transaction.rollback', tx);
	if (bench_id) {
		let sp=benchmark_path(bench_id), sess=json_read(sp,null);
		if (sess && sess.state == 'candidate_applied' && reason != 'benchmark-complete') {
			sess.state='failed'; sess.result={validated:false,error:reason ?? 'candidate-rolled-back'}; json_write(sp,sess);
		}
		/* A terminal session must release its experiment-domain lock; the next
		 * benchmark may then start.  The benchmark-complete reason is the
		 * success path and releases in benchmark_start itself. */
		if (reason != 'benchmark-complete')
			release_benchmark_lock(sess?.benchmarkLock?.domain, bench_id);
	}
	return { ok: true, transaction: tx };
}

function arm_tx_timer(tx) {
	cancel_tx_timer(tx.transactionId);
	if (tx.state != 'awaiting_confirm' || tx.deadlineMonotonicMs == null) return false;
	let remaining = max(1, tx.deadlineMonotonicMs - monotonic_ms());
	tx_timers[tx.transactionId] = uloop.timer(remaining, function() {
		rollback_transaction(tx.transactionId, 'confirm-timeout');
		delete tx_timers[tx.transactionId];
	});
	return true;
}

function arm_commit_confirm(tx, timeout_ms) {
	tx.deadlineMonotonicMs = monotonic_ms() + max(1000, timeout_ms);
	tx.verification.commitConfirm = 'pending';
	tx.state = 'awaiting_confirm';
	if (!tx_save(tx)) return { ok: false, error: 'pending-marker-write-failed' };
	arm_tx_timer(tx);
	return { ok: true, transaction: tx };
}

function confirm_transaction(txid) {
	let tx = json_read(tx_path(txid), null);
	if (!tx) return { ok: false, error: 'transaction-not-found' };
	if (tx.state != 'awaiting_confirm') return { ok: false, error: 'not-awaiting-confirm' };
	if (tx.bootId != boot_id()) return rollback_transaction(txid, 'boot-changed-before-confirm');
	if (tx.deadlineMonotonicMs == null) return rollback_transaction(txid, 'missing-confirm-deadline');
	if (monotonic_ms() > tx.deadlineMonotonicMs) return rollback_transaction(txid, 'confirm-timeout');
	if (tx.commitPolicy == 'rollback_after_benchmark')
		return { ok: false, error: 'benchmark-transactions-cannot-be-manually-committed' };
	if (tx.actionId == 'nic.ring.floor' && tx.before?.targetRef) {
		let ref = resolve_target(tx.before.targetRef.stableId);
		if (!ref) return rollback_transaction(txid, 'confirm-target-unresolved');
		if (!persist_ring_policy(ref, tx.applied ?? {}, tx.transactionId, tx.before?.ring, tx.result?.ring))
			return rollback_transaction(txid, 'confirm-persistence-failed');
	}
	tx.verification.commitConfirm = 'confirmed'; tx.state = 'committed'; tx.deadlineMonotonicMs = null;
	if (tx.rillDecision) {
		let intent = rill_prepare_outcome(tx.rillDecision, 'health_only', 0.0, tx.transactionId, 'committed');
		if (!intent.ok) return rollback_transaction(txid, 'rill-outcome-intent-write-failed');
	}
	if (!tx_save(tx)) {
		/* The durable marker/journal must agree before a connectivity-critical
		 * change can be considered committed. Fall back to the previous journal
		 * state and restore through the normal stale-safe rollback path. */
		let rr=rollback_transaction(txid,'confirm-journal-write-failed');
		return {ok:false,error:'confirm-journal-write-failed',rollback:rr};
	}
	if (tx.rillDecision) {
		let armed = rill_arm_outcome(tx.rillDecision);
		if (!armed.ok) return {ok:false,error:'rill-outcome-arm-failed',transaction:tx,detail:armed};
	}
	cancel_tx_timer(tx.transactionId); release_locks(tx.requiredLocks, tx.transactionId);
	history('transaction.commit', tx);
	if (tx.rillDecision)
		rill_report_outcome(tx.rillDecision, 'health_only', 0.0, tx.transactionId, {});
	return { ok: true, transaction: tx };
}

function clean_stale_benchmark_locks() {
	for (let p in fs.glob(`${benchmark_lock_dir()}/*.json`) ?? []) {
		let lock = json_read(p, null);
		if (!lock || lock.bootId != boot_id()) { fs.unlink(p); continue; }
		let session = json_read(benchmark_path(lock.sessionId), null);
		if (!session || !benchmark_session_active(session) || benchmark_session_expired(session, monotonic_ms())) {
			if (session && session.state == 'awaiting_control' && benchmark_session_expired(session, monotonic_ms())) {
				session.state = 'failed'; session.result = { validated: false, error: 'benchmark-session-idle-expired' };
				json_write(benchmark_path(lock.sessionId), session);
			}
			fs.unlink(p);
		}
	}
}

function recover_pending() {
	ensure_dir(`${state_dir()}/transactions`);
	recover_persistent_markers();
	clean_stale_locks();
	for (let tx in transaction_list()) {
		if (!tx_is_active(tx)) continue;
		if (tx.bootId != boot_id()) {
			tx.state = 'rolled_back'; tx.deadlineMonotonicMs = null;
			tx.verification.rollbackReadBack = 'not_applicable_new_boot';
			tx.result = { reason: 'boot-recovery-runtime-reset-no-stale-replay' };
			tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId); history('transaction.boot_recovered', tx);
			continue;
		}
		if (tx.state == 'awaiting_confirm') {
			if (tx.deadlineMonotonicMs == null) {
				rollback_transaction(tx.transactionId, 'missing-confirm-deadline-recovery');
				continue;
			}
			if (monotonic_ms() >= tx.deadlineMonotonicMs) {
				rollback_transaction(tx.transactionId, 'confirm-timeout-recovery');
				continue;
			}
			arm_tx_timer(tx);
			continue;
		}
		/* A same-boot daemon crash during pending/applied/verified has no trusted
		 * caller left to finish the transaction. Fail closed and restore now. */
		rollback_transaction(tx.transactionId, 'core-crash-recovery');
	}
	clean_stale_locks();
	/* Benchmark experiment locks belong to sessions; any session that died with
	 * the daemon is no longer active and must not block the next experiment. */
	clean_stale_benchmark_locks();
}

function cleanup_owned(reason) {
	let summary={ok:true,reason:reason ?? 'package-remove',activeTransactions:[],policies:[],remainingLocks:[]};
	/* First close every live transaction through the normal stale-safe rollback
	 * engine. Never delete its recovery marker merely to make uninstall look
	 * clean: a failed rollback is evidence that needs operator attention. */
	for (let tx in transaction_list()) {
		if (!tx_is_active(tx)) continue;
		let r=rollback_transaction(tx.transactionId,'package-remove');
		push(summary.activeTransactions,{transactionId:tx.transactionId,ok:r.ok,error:r.error ?? null});
		if (!r.ok) summary.ok=false;
	}

	for (let p in fs.glob(`${persist_dir()}/policies/*.json`) ?? []) {
		let pol=json_read(p,null);
		if (!pol || pol.owner != 'performance_manager') continue;
		if (pol.actionId != 'nic.ring.floor') {
			/* Unknown PM policy is safer to make non-replayable than to guess a
			 * runtime inverse for a provider this build does not own. */
			fs.unlink(p); push(summary.policies,{actionId:pol.actionId,status:'intent-removed-runtime-untouched'}); continue;
		}
		let ref=resolve_target(pol.targetRef?.stableId), lease=pol.runtimeLease;
		if (!ref || !lease || lease.bootId != boot_id() || !lease.beforeRing || !lease.ownedRing) {
			fs.unlink(p); push(summary.policies,{actionId:pol.actionId,target:pol.targetRef?.stableId ?? null,status:'intent-removed-runtime-untouched'}); continue;
		}
		/* If the live knob no longer equals the exact PM-owned value, somebody
		 * else has taken ownership. Preserve that state and only remove replay
		 * intent; never stale-rollback over user/external changes. */
		if (!ring_matches(ref,lease.ownedRing)) {
			fs.unlink(p); push(summary.policies,{actionId:pol.actionId,target:ref.stableId,status:'live-drift-preserved-intent-removed'}); continue;
		}
		let cleanup_id=sprintf('cleanup-%d',monotonic_ms()), resources=[`netdev:${ref.stableId}`], lock=acquire_locks(resources,cleanup_id);
		if (!lock.ok) { summary.ok=false; push(summary.policies,{actionId:pol.actionId,target:ref.stableId,status:'lock-conflict',detail:lock}); continue; }
		let rr=ring_restore(ref,lease.beforeRing), restored=rr.rc==0 && ring_matches(ref,lease.beforeRing);
		release_locks(resources,cleanup_id);
		if (!restored) { summary.ok=false; push(summary.policies,{actionId:pol.actionId,target:ref.stableId,status:'runtime-restore-failed',output:rr.out ?? ''}); continue; }
		fs.unlink(p); push(summary.policies,{actionId:pol.actionId,target:ref.stableId,status:'runtime-restored-and-intent-removed'});
	}
	clean_stale_locks();
	clean_stale_benchmark_locks();
	for (let x in lock_list()) push(summary.remainingLocks,x);
	if (length(summary.remainingLocks)) summary.ok=false;
	history('ownership.cleanup',summary);
	return summary;
}

function benchmark_fail_session(sp, sid, error) {
	let sess = json_read(sp, null);
	if (!sess) return;
	/* A Rill-owned session which never reached the mutation boundary may give
	 * the reservation back. Once mutationStarted is durable this helper is a
	 * no-op, preserving exactly-once ownership for every later failure path. */
	if (sess.rillDecision) rill_binding_release_reservation(sess.rillDecision, `benchmark-failed-before-mutation:${error}`);
	if (benchmark_session_active(sess)) {
		sess.state = 'failed'; sess.result = { validated: false, error: error };
		json_write(sp, sess);
	}
	release_benchmark_lock(sess.benchmarkLock?.domain, sid);
}

function benchmark_context_frozen(session) {
	return {
		capabilityHash: session?.capabilityHash, topologyGeneration: session?.topologyGeneration,
		routeIdentity: session?.routeIdentity, routeProvider: null,
		integrationState: session?.integrationState, integrationFingerprint: session?.integrationFingerprint,
		workloadClass: session?.workloadClass, goal: session?.goal
	};
}

/* -- Goal semantics (Blocker 2) -------------------------------------------
 * The configured goal must genuinely partition the model, select benchmark
 * measurement, drive reward and appear in the Rill request and UI.  A goal
 * with no measurable methodology fails-closed instead of silently degrading
 * to throughput. */
function goal() {
	let g = cfg('main.goal', 'balanced');
	return index(GOALS, g) >= 0 ? g : 'balanced';
}

function goal_measurable(g) {
	return GOAL_MEASURABLE[g] ?? null;
}

/* -- Controlled A/B measurement methodology fingerprint (Blocker 3) -------
 * A controlled experiment is one-variable-at-a-time only if the measurement
 * methodology is identical between control and candidate.  The canonical
 * fingerprint covers endpoint identity, port, direction, parallel streams,
 * duration, protocol/mode and tool version.  A mismatch invalidates the
 * experiment: no reward is emitted and no Rill outcome is sent. */
function measurement_methodology(e) {
	let m = e?.methodology ?? {};
	let ep = e?.endpoint ?? {};
	return {
		host: m.host ?? ep.host ?? null,
		port: m.port ?? ep.port ?? null,
		reverse: (m.reverse ?? ep.reverse) ? true : false,
		parallel: max(1, +((m.parallel ?? ep.parallel) ?? 1)),
		duration: +((m.duration ?? e?.resultDuration) ?? 0),
		protocol: m.protocol ?? 'iperf3-tcp',
		tool: (m.tool ?? ep.tool) ?? 'iperf3',
		toolVersion: m.toolVersion ?? null
	};
}

function methodology_key(m) {
	return sprintf('m:%s|%s|%s|%d|%d|%s|%s|%s',
		m.host ?? '', m.port ?? '', m.reverse ? 'R' : 'F', m.parallel, m.duration,
		m.protocol ?? '', m.tool ?? '', m.toolVersion ?? '');
}

function methodology_matches(a, b) {
	return methodology_key(measurement_methodology(a)) == methodology_key(measurement_methodology(b));
}

function companion_evidence_valid(e, session, phase) {
	if (!e || e.contract != 'pm-companion/v2' || e.role != session.companion?.requiredRole || e.ok != true || !(+e.bitsPerSecond > 0)) return {ok:false,error:'invalid-companion-evidence'};
	if (e.sessionId != session.sessionId || e.phase != phase || e.actionId != session.actionId || e.pathId != session.evaluationPath)
		return {ok:false,error:'companion-context-mismatch'};
	if (+e.topologyGeneration != +session.topologyGeneration || e.routeIdentity != session.routeIdentity || e.capabilityHash != session.capabilityHash)
		return {ok:false,error:'companion-context-drift'};
	return {ok:true};
}

function benchmark_list() {
	let out=[]; for (let p in fs.glob(`${state_dir()}/benchmarks/*.json`) ?? []) { let x=json_read(p,null); if (x) push(out,x); }
	sort(out,function(a,b){return (b.sessionId??'') > (a.sessionId??'') ? 1 : -1;}); return out;
}

function benchmark_stop(session_id) {
	let session=session_id ? json_read(benchmark_path(session_id),null) : null;
	if (!session) return {ok:false,error:'benchmark-session-not-found'};
	if (session.state == 'candidate_applied' && session.transactionId) {
		let r=rollback_transaction(session.transactionId,'benchmark-stopped');
		if (!r.ok) return {ok:false,error:'candidate-rollback-failed',detail:r};
	}
	if (session.state == 'completed' || session.state == 'failed' || session.state == 'stopped') return {ok:false,error:'benchmark-session-not-running',session:session};
	if (session.rillDecision) rill_binding_release_reservation(session.rillDecision, 'benchmark-stopped-before-mutation');
	session.state='stopped'; session.result={validated:false,error:'stopped-by-user'};
	if (!json_write(benchmark_path(session_id),session)) return {ok:false,error:'benchmark-session-write-failed-after-stop',session:session};
	release_benchmark_lock(session.benchmarkLock?.domain, session_id);
	history('benchmark.stopped',session); return {ok:true,session:session};
}

function rill_socket_path() {
	return cfg('shadow.socket', '/run/performance-manager/rill.sock');
}

function rill_recv_frame(s, maxMsg, timeout) {
	/* Read ONE newline-delimited JSON frame from the Rill socket, bounded and
	 * fail-closed.  Handles partial reads, oversized replies, empty replies,
	 * a peer that closes early, and a read timeout — none of which may be
	 * parsed as a truncated/garbage JSON.  Returns the raw frame body (without
	 * the trailing newline) on success, or an error object { state } on
	 * failure.  The protocol is strictly framed by a single trailing newline;
	 * trailing bytes after the first frame are ignored for this request. */
	let buf = '';
	let deadline = monotonic_ms() + max(1, timeout);
	let closed = false, timed_out = false;
	while (length(buf) < maxMsg) {
		let remaining = max(1, deadline - monotonic_ms());
		let events = socket.poll(remaining, s);
		if (!events || !length(events) || !((events[0][1] ?? 0) & socket.POLLIN)) {
			timed_out = true;
			break;
		}
		let chunk = s.recv(max(1, maxMsg - length(buf)));
		if (chunk == null || chunk == '') { closed = true; break; }
		buf += chunk;
		if (index(buf, '\n') >= 0) break;
	}
	if (closed) return { state: 'peer-closed' };
	if (timed_out) return { state: 'timeout-or-peer-error' };
	/* Frame never terminated within the per-message bound. */
	if (index(buf, '\n') < 0) return { state: length(buf) >= maxMsg ? 'oversized-response' : 'truncated-frame' };
	/* ucode's global slice() is array-only and returns null for strings.  Use
	 * substr() so a valid adapter JSON line is not misclassified as empty. */
	let body = trimstr(substr(buf, 0, index(buf, '\n')));
	if (!length(body)) return { state: 'empty-response' };
	return { body: body };
}

function rill_send(payload, outcome_attempt, mark_sent_unknown) {
	if (!bool_cfg('shadow.enabled', true)) return { ok: false, state: 'disabled', connected: false, fullySent: false, responseReceived: false };
	let maxMsg = min(262144, max(4096, int_cfg('shadow.max_message', 65536)));
	let timeout = min(5000, max(100, int_cfg('shadow.timeout_ms', 1000)));
	/* The adapter protocol is newline-delimited JSON. ucode %.J pretty-prints
	 * internal newlines, so use compact %J and add exactly one frame newline. */
	let wire = sprintf('%J\n', payload);
	if (length(wire) > maxMsg) return { ok: false, state: 'oversized-local-context', connected: false, fullySent: false, responseReceived: false };
	let s = socket.connect({ path: rill_socket_path() }, null, null, timeout);
	if (!s) return { ok: false, state: 'connect-failed', connected: false, fullySent: false, responseReceived: false };
	let sent = s.send(wire);
	if (sent == null || sent != length(wire)) { s.close(); return { ok: false, state: 'send-failed', connected: true, fullySent: false, responseReceived: false }; }
	/* Once the complete request has entered the socket, persist uncertainty
	 * BEFORE waiting for the peer response. A crash in recv() can therefore be
	 * reconciled only for this exact durable outcome fingerprint. */
	if (outcome_attempt && (!mark_sent_unknown || !mark_sent_unknown(outcome_attempt))) {
		s.close();
		return { ok: false, state: 'sent-unknown-journal-failed', connected: true, fullySent: true, responseReceived: false };
	}
	let frame = rill_recv_frame(s, maxMsg, timeout);
	s.close();
	if (frame.state) return { ok: false, state: `${frame.state}-after-send`, connected: true, fullySent: true, responseReceived: false };
	/* Strict single-frame JSON parse; any malformed body fails closed. */
	let parsed = null;
	try { parsed = json(frame.body); } catch (e) { return { ok: false, state: 'bad-response-after-send', connected: true, fullySent: true, responseReceived: true }; }
	if (parsed == null) return { ok: false, state: 'bad-response-after-send', connected: true, fullySent: true, responseReceived: true };
	return { ok: true, response: parsed, connected: true, fullySent: true, responseReceived: true };
}

function rill_context_key_build(profile, capability_hash, topo_gen, path_id, route_identity, workload_class, integ_fingerprint, goal_id) {
	/* Canonical bounded ContextKey.  The same construction must be used by
	 * observe and by every outcome so Rill can partition its model per
	 * context.  Identity components are hashed to keep the key bounded.
	 * Goal is a first-class partition component (Blocker 2). */
	let route_class = route_identity == 'unresolved' ? 'unresolved' : fnv1a32(route_identity);
	let integ_class = fnv1a32(integ_fingerprint ?? '');
	let workload_class_h = stable_list_hash('w', workload_class ?? [ 'plain_forwarding' ]);
	let goal_class = safe_name(goal_id ?? 'balanced');
	return sprintf('ctx-v1:profile=%s;cap=%s;topo=%d;path=%s;route=%s;workload=%s;integ=%s;goal=%s',
		safe_name(profile ?? 'recommended'), capability_hash ?? 'unknown', topo_gen ?? 0,
		safe_name(path_id ?? 'path:lan-to-wan'), route_class, workload_class_h, integ_class, goal_class);
}

function rill_binary_path() {
	/* UNIQUE PM<->init binary resolution contract.  Kept in sync with
	 * resolve_binary() in the performance-manager-rill init guard.  An
	 * explicit shadow.binary wins EXCLUSIVELY (must be absolute and
	 * executable, otherwise reason 'binary-invalid', never a silent
	 * fallback); an empty shadow.binary resolves the default install
	 * path (/usr/bin then /usr/sbin); none found -> reason
	 * 'not-provisioned'.  Returns { ok, binary, effective, source,
	 * reason }. */
	let configured = str_cfg('shadow.binary', '');
	if (configured != '') {
		if (substr(configured, 0, 1) != '/' || !file_executable(configured))
			return { ok: false, binary: configured, effective: null, source: 'explicit', reason: 'binary-invalid' };
		return { ok: true, binary: configured, effective: configured, source: 'explicit', reason: 'ok' };
	}
	for (let path in [ '/usr/bin/rill-pm-adapter', '/usr/sbin/rill-pm-adapter' ])
		if (file_executable(path))
			return { ok: true, binary: path, effective: path, source: 'default', reason: 'ok' };
	return { ok: false, binary: '', effective: null, source: 'default', reason: 'not-provisioned' };
}

/* ucode resolves function names when the caller is defined, so protocol
 * validators must precede rill_status()/observe/outcome callers in the raw
 * shipped daemon.  The runtime harness intentionally loads this same order
 * without a semantic source transformation. */
function rill_validate_response_envelope(request, response) {
	if (type(response) != 'object') return { ok: false, error: 'response-not-object' };
	if (response.contract != RILL_CONTRACT) return { ok: false, error: 'wrong-contract' };
	if (response.protocolVersion != RILL_PROTOCOL_VERSION) return { ok: false, error: 'wrong-protocol' };
	if ((response.requestId ?? '') != (request?.requestId ?? '')) return { ok: false, error: 'request-id-mismatch' };
	if (type(response.ok) != 'bool') return { ok: false, error: 'ok-not-boolean' };
	return { ok: true };
}

function rill_validate_status_response(request, response) {
	let envelope = rill_validate_response_envelope(request, response);
	if (!envelope.ok) return envelope;
	if (response.ok !== true) return { ok: false, error: response.error?.code ?? 'status-rejected' };
	if (type(response.capabilities) != 'array' || type(response.modelHealth) != 'object') return { ok: false, error: 'status-fields-invalid' };
	if (!length(response.adapterVersion ?? '') || !length(response.rillVersion ?? '')) return { ok: false, error: 'status-version-missing' };
	return { ok: true };
}

function rill_validate_observe_response(request, response) {
	let envelope = rill_validate_response_envelope(request, response);
	if (!envelope.ok) return envelope;
	if (response.ok !== true) return { ok: false, error: response.error?.code ?? 'observe-rejected' };
	if (!match(response.decisionId ?? '', /^[0-9a-f]{32}$/)) return { ok: false, error: 'decision-id-invalid' };
	let rec = response.recommendation;
	if (type(rec) != 'object' || !length(rec.actionId ?? '') || rec.advisory !== true) return { ok: false, error: 'recommendation-invalid' };
	let ct = type(rec.confidence);
	if ((ct != 'int' && ct != 'double') || rec.confidence != rec.confidence || rec.confidence < 0 || rec.confidence > 1)
		return { ok: false, error: 'confidence-invalid' };
	let advertised = false;
	for (let action in request.availableActions ?? []) if (action.id == rec.actionId && (action.executionAuthority == 'safe-direct' || action.executionAuthority == 'benchmark')) { advertised = true; break; }
	if (!advertised) return { ok: false, error: 'recommendation-action-unknown' };
	return { ok: true };
}

function rill_validate_outcome_response(request, response) {
	let envelope = rill_validate_response_envelope(request, response);
	if (!envelope.ok) return envelope;
	if (response.ok !== true) return { ok: false, error: response.error?.code ?? 'outcome-rejected' };
	if (response.accepted !== true) return { ok: false, error: 'outcome-not-accepted' };
	return { ok: true };
}

function rill_status() {
	let enabled = bool_cfg('shadow.enabled', true);
	if (!enabled) return { enabled: false, mode: 'shadow', status: 'Shadow · Disabled', state: RILL_STATES.disabled, reason: 'disabled', compatibility: 'not-applicable', transport: 'unavailable', protocolVersion: RILL_PROTOCOL_VERSION, binary: { configured: str_cfg('shadow.binary', ''), effective: null, source: 'n/a' } };
	/* External dependency check driven by the unique binary-resolution
	 * contract.  Explicit binary wins exclusively and must be absolute and
	 * present; an empty binary resolves the default install path; a missing
	 * runtime is reported not-provisioned, never assumed available. */
	let bin = rill_binary_path();
	let bmeta = { configured: str_cfg('shadow.binary', ''), effective: bin.effective, source: bin.source };
	if (!bin.ok) {
		if (bin.reason == 'binary-invalid')
			return { enabled: true, mode: 'shadow', status: 'Shadow · Binary invalid', state: RILL_STATES.binaryInvalid, reason: 'binary-invalid', compatibility: 'not-provisioned', transport: 'unavailable', protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta };
		return { enabled: true, mode: 'shadow', status: 'Shadow · Not provisioned', state: RILL_STATES.notProvisioned, reason: 'external-runtime-not-provisioned', compatibility: 'not-provisioned', transport: 'unavailable', protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta };
	}
	let requestId = sprintf('status-%d', monotonic_ms());
	let request = { contract: RILL_CONTRACT, protocolVersion: RILL_PROTOCOL_VERSION, requestId: requestId, op: 'status' };
	let r = rill_send(request);
	if (!r.ok) return { enabled: true, mode: 'shadow', status: 'Shadow · Unavailable', state: RILL_STATES.unavailable, reason: r.state ?? 'unavailable', compatibility: 'unknown', transport: r.state ?? 'unavailable', protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta };
	let resp = r.response ?? {};
	let valid = rill_validate_status_response(request, resp);
	if (!valid.ok && valid.error == 'wrong-contract')
		return { enabled: true, mode: 'shadow', status: 'Shadow · Incompatible contract', state: RILL_STATES.incompatible, reason: 'contract-mismatch', compatibility: 'incompatible', transport: 'connected', requestedContract: RILL_CONTRACT, advertisedContract: resp.contract ?? null, protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
	if (!valid.ok && valid.error == 'wrong-protocol')
		return { enabled: true, mode: 'shadow', status: 'Shadow · Incompatible protocol', state: RILL_STATES.incompatible, reason: 'protocol-version-mismatch', compatibility: 'incompatible', transport: 'connected', requestedProtocolVersion: RILL_PROTOCOL_VERSION, advertisedProtocolVersion: resp.protocolVersion ?? null, protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
	if (!valid.ok)
		return { enabled: true, mode: 'shadow', status: 'Shadow · Adapter error', state: RILL_STATES.unhealthy, reason: valid.error, compatibility: 'incompatible', transport: 'connected', protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
	/* Required capabilities: the adapter must declare every capability the
	 * integration depends on; a missing one is fail-closed. */
	let caps = resp.capabilities ?? [];
	for (let need in RILL_REQUIRED_CAPABILITIES)
		if (index(caps, need) < 0)
			return { enabled: true, mode: 'shadow', status: 'Shadow · Missing capabilities', state: RILL_STATES.incompatible, reason: 'missing-required-capability', compatibility: 'incompatible', transport: 'connected', missingCapability: need, protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
	/* Model health: advisory is only allowed when the adapter reports a
	 * healthy model; a degraded adapter is fail-closed unhealthy. */
	let health = resp.modelHealth ?? {};
	if (health.overall != 'healthy')
		return { enabled: true, mode: 'shadow', status: 'Shadow · Unhealthy', state: RILL_STATES.unhealthy, reason: 'model-unhealthy', compatibility: 'compatible', transport: 'connected', modelHealth: health, protocolVersion: RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
	let learning = resp.state == 'learning';
	return { enabled: true, mode: 'shadow', authority: 'advisory-only', status: learning ? 'Shadow · Learning' : 'Shadow · Available', state: learning ? RILL_STATES.learning : RILL_STATES.available, reason: null, compatibility: 'compatible', transport: 'connected', adapterVersion: resp.adapterVersion ?? RILL_PINNED_ADAPTER_VERSION, rillVersion: resp.rillVersion ?? RILL_PINNED_RELEASE_VERSION, releaseVersion: RILL_PINNED_RELEASE_VERSION, protocolVersion: resp.protocolVersion ?? RILL_PROTOCOL_VERSION, binary: bmeta, detail: r.response };
}

function rill_integrations_payload() {
	/* Stable, bounded array projection of integration_state() for the Rill
	 * wire contract.  Rill v1.2.0 Observe.integrations is Vec<Value> (an
	 * array), never an object; a deterministic key order keeps the payload
	 * reproducible across observes. */
	let st = integration_state();
	let order = [ 'openclash', 'passwall', 'homeproxy', 'sqm', 'qosify', 'mwan3', 'pbr', 'wireguard', 'openvpn', 'docker' ];
	return map(order, function(k) { return { id: k, present: !!st[k] }; });
}

/* Unexecuted advisories are runtime cache only.  Flash is used only when an
 * exact decision is frozen into an already-durable transaction/session. */
let rill_bindings = {};
let rill_last_observe_ms = null;
let rill_advisory = null;

function rill_binding_valid(binding) {
	if (type(binding) != 'object' || binding.schemaVersion != RILL_BINDINGS_SCHEMA_VERSION) return false;
	if (!match(binding.decisionId ?? '', /^[0-9a-f]{32}$/) || !length(binding.actionId ?? '') || !length(binding.contextKey ?? '')) return false;
	if (!length(binding.goal ?? '') || binding.modelGeneration != RILL_MODEL_GENERATION || binding.bootId != boot_id()) return false;
	if (binding.executionAuthority != 'safe-direct' && binding.executionAuthority != 'benchmark') return false;
	if (binding.atMs == null || binding.atMs > monotonic_ms() || (monotonic_ms() - binding.atMs) > RILL_BINDINGS_TTL_MS) return false;
	return true;
}

function rill_bindings_prune() {
	let rows = [];
	for (let decision_id in keys(rill_bindings)) {
		let binding = rill_bindings[decision_id];
		if (!rill_binding_valid(binding)) delete rill_bindings[decision_id];
		else push(rows, { decisionId: decision_id, atMs: binding.atMs });
	}
	sort(rows, function(a, b) { return (a.atMs ?? 0) - (b.atMs ?? 0); });
	while (length(rows) > RILL_BINDINGS_MAX) {
		let oldest = rows[0];
		rows = slice(rows, 1);
		delete rill_bindings[oldest.decisionId];
	}
}

function rill_binding_register(payload, response) {
	let rec = response.recommendation;
	let advertised = null;
	for (let action in payload.availableActions ?? []) if (action.id == rec.actionId) { advertised = action; break; }
	if (!advertised) return null;
	let binding = {
		schemaVersion: RILL_BINDINGS_SCHEMA_VERSION,
		decisionId: response.decisionId, contextKey: payload.contextKey,
		actionId: rec.actionId, goal: payload.goal, modelGeneration: RILL_MODEL_GENERATION,
		advisory: true, confidence: rec.confidence, executionAuthority: advertised.executionAuthority,
		bootId: boot_id(), atMs: monotonic_ms()
	};
	if (!rill_binding_valid(binding)) return null;
	rill_bindings[binding.decisionId] = binding;
	rill_bindings_prune();
	rill_runtime_counters.rillBindingHighWater = max(rill_runtime_counters.rillBindingHighWater, length(keys(rill_bindings)));
	return binding;
}

function rill_binding_peek(decision_id) {
	rill_bindings_prune();
	let binding = rill_bindings[decision_id];
	return rill_binding_valid(binding) ? binding : null;
}

function rill_execution_path(decision_id) {
	return `${persist_dir()}/rill-executions/${safe_name(decision_id)}.json`;
}

function rill_binding_reserve(decision_id, action_id, authority, owner_type, owner_id) {
	let binding = rill_binding_peek(decision_id);
	if (!binding || binding.actionId != action_id || binding.executionAuthority != authority) return null;
	if (owner_type != 'transaction' && owner_type != 'benchmark') return null;
	if (!length(owner_id ?? '') || json_read(rill_execution_path(decision_id), null)) return null;
	/* Bound persistent flash state without evicting live or pending evidence.
	 * Completed outcomes are removed immediately; abandoned executions remain
	 * auditable and new reservations fail closed at the runtime binding bound. */
	let journals = fs.glob(`${persist_dir()}/rill-executions/*.json`) ?? [];
	if (length(journals) >= RILL_BINDINGS_MAX) return null;
	let frozen = {
		schemaVersion: binding.schemaVersion, decisionId: binding.decisionId, contextKey: binding.contextKey,
		actionId: binding.actionId, goal: binding.goal, modelGeneration: binding.modelGeneration,
		advisory: true, confidence: binding.confidence, bootId: binding.bootId, atMs: binding.atMs,
		executionAuthority: authority, ownerType: owner_type, ownerId: owner_id
	};
	let journal = {
		schemaVersion: RILL_EXECUTION_SCHEMA_VERSION, decisionId: frozen.decisionId,
		actionId: frozen.actionId, contextKey: frozen.contextKey, goal: frozen.goal,
		modelGeneration: frozen.modelGeneration, frozenDecision: frozen,
		executionAuthority: authority, ownerType: owner_type, ownerId: owner_id,
		executionState: 'reserved', mutationStarted: false, transportState: 'not-sent',
		mayHaveReachedPeer: false, attemptCount: 0, createdBootId: boot_id(),
		createdMonotonicMs: monotonic_ms(), nextRetryMonotonicMs: null
	};
	if (!json_write(rill_execution_path(decision_id), journal)) return null;
	delete rill_bindings[decision_id];
	if (rill_advisory?.decisionId == decision_id) rill_advisory = null;
	rill_runtime_counters.rillDecisionReserved++;
	runtime_history('rill.binding.reserved', { decisionId: decision_id, actionId: action_id, ownerType: owner_type, ownerId: owner_id, executionAuthority: authority });
	return frozen;
}

rill_binding_release_reservation = function(binding, reason) {
	let path = rill_execution_path(binding?.decisionId), journal = json_read(path, null);
	if (!journal || journal.mutationStarted === true || journal.executionState != 'reserved') return false;
	if (journal.ownerId != binding?.ownerId || journal.ownerType != binding?.ownerType) return false;
	fs.unlink(path);
	let restored = journal.frozenDecision;
	if (rill_binding_valid(restored)) rill_bindings[restored.decisionId] = restored;
	runtime_history('rill.binding.reservation-released', { decisionId: binding.decisionId, ownerId: binding.ownerId, reason: reason ?? 'pre-mutation-owner-journal-failed' });
	return true;
};

function rill_execution_mark_mutation_started(binding) {
	let path = rill_execution_path(binding?.decisionId), journal = json_read(path, null);
	if (!journal || journal.ownerId != binding?.ownerId || journal.executionState != 'reserved') return false;
	journal.mutationStarted = true;
	journal.executionState = 'executing';
	journal.mutationBootId = boot_id();
	journal.mutationStartedMonotonicMs = monotonic_ms();
	return json_write(path, journal);
}

function rill_binding_consume(binding) {
	if (!binding?.decisionId) return;
	delete rill_bindings[binding.decisionId];
	if (rill_advisory?.decisionId == binding.decisionId) rill_advisory = null;
}

function rill_binding_retire(binding, reason) {
	rill_binding_consume(binding);
	runtime_history('rill.binding.retired', { decisionId: binding?.decisionId ?? null, actionId: binding?.actionId ?? null, reason: reason });
}

function rill_invalidate_runtime_decisions(reason) {
	rill_bindings = {};
	rill_advisory = null;
	runtime_history('rill.runtime-decisions-invalidated', { reason: reason ?? 'context-drift' });
}

function rill_advisory_update(resp, payload) {
	/* Remember the latest recommendation for UI display.  Fed ONLY from a
	 * successful observe — status responses carry no recommendation, so the
	 * advisory can never be confused with "runtime available".  The stored
	 * drift-context (topology generation / route identity / integration
	 * fingerprint / goal) lets rill_advisory_get() invalidate it if the world
	 * changed under it, and expiresMonotonicMs bounds its lifetime. */
	let rec = resp.recommendation;
	let advertised = null;
	for (let action in payload.availableActions ?? []) if (action.id == rec.actionId) { advertised = action; break; }
	if (!advertised) return null;
	let now = monotonic_ms();
	rill_advisory = {
		decisionId: resp.decisionId, actionId: rec.actionId,
		confidence: rec.confidence, advisory: true, authority: 'advisory-only',
		executionAuthority: advertised.executionAuthority, kind: advertised.executionAuthority == 'benchmark' ? 'benchmark' : 'safe-direct',
		applyTarget: advertised.applyTarget ?? null, evaluationPaths: advertised.evaluationPaths ?? [],
		contextKey: payload.contextKey, goal: payload.goal,
		topologyGeneration: payload.topologyGeneration,
		routeIdentity: payload.routeIdentity,
		integrationFingerprint: payload.integrationFingerprint,
		createdMonotonicMs: now, expiresMonotonicMs: now + RILL_ADVISORY_TTL_MS
	};
	return rill_advisory;
}

function rill_outcome_attempt_path(binding) {
	return rill_execution_path(binding.decisionId);
}

function rill_outcome_fingerprint(binding, session_id, reward) {
	return sprintf('%.J', { decisionId: binding.decisionId, actionId: binding.actionId, contextKey: binding.contextKey,
		goal: binding.goal, modelGeneration: binding.modelGeneration, sessionId: session_id, reward: reward, validated: true });
}

function rill_outcome_attempt(binding, measurement, session_id, reward) {
	let path = rill_outcome_attempt_path(binding), fingerprint = rill_outcome_fingerprint(binding, session_id, reward);
	let existing = json_read(path, null);
	if (!existing || existing.fingerprint != fingerprint || existing.ownerId != binding?.ownerId)
		return { ok: false, state: 'outcome-attempt-mismatch', path: path };
	let attempt = existing;
	if (attempt.executionState != 'outcome-pending' && attempt.executionState != 'sent-unknown')
		return { ok: false, state: 'outcome-not-pending', path: path };
	return { ok: true, attempt: attempt, path: path, fingerprint: fingerprint };
}

rill_prepare_outcome = function(binding, measurement, reward, session_id, expected_owner_state) {
	let path = rill_execution_path(binding?.decisionId), journal = json_read(path, null);
	if (!journal || journal.ownerId != binding?.ownerId || journal.ownerType != binding?.ownerType || journal.mutationStarted !== true)
		return { ok: false, state: 'rill-execution-journal-owner-mismatch' };
	let fingerprint = rill_outcome_fingerprint(binding, session_id, reward);
	if (journal.fingerprint && journal.fingerprint != fingerprint) return { ok: false, state: 'outcome-attempt-mismatch' };
	if (expected_owner_state != 'committed' && expected_owner_state != 'rolled_back' && expected_owner_state != 'completed')
		return { ok: false, state: 'outcome-terminal-state-invalid' };
	journal.executionState = 'outcome-prepared';
	journal.measurementClass = measurement; journal.sessionId = session_id; journal.reward = reward;
	journal.validated = true; journal.fingerprint = fingerprint; journal.binding = binding;
	journal.expectedOwnerState = expected_owner_state;
	journal.transportState = 'not-sent';
	journal.mayHaveReachedPeer = journal.mayHaveReachedPeer === true;
	journal.nextRetryMonotonicMs = null;
	journal.outcomePreparedBootId = boot_id();
	if (!json_write(path, journal)) return { ok: false, state: 'outcome-intent-journal-failed' };
	return { ok: true, attempt: journal, path: path, fingerprint: fingerprint };
};

rill_arm_outcome = function(binding) {
	let path=rill_execution_path(binding?.decisionId), journal=json_read(path,null);
	if (!journal || journal.ownerId != binding?.ownerId || journal.ownerType != binding?.ownerType || journal.executionState != 'outcome-prepared')
		return {ok:false,state:'outcome-prepared-owner-mismatch'};
	let owner = journal.ownerType == 'transaction' ? json_read(tx_path(journal.ownerId),null) : json_read(benchmark_path(journal.ownerId),null);
	if (!owner || owner.state != journal.expectedOwnerState)
		return {ok:false,state:'outcome-owner-terminal-not-durable',expected:journal.expectedOwnerState,actual:owner?.state ?? null};
	journal.executionState='outcome-pending'; journal.transportState='pending';
	journal.nextRetryMonotonicMs=monotonic_ms(); journal.outcomeArmedBootId=boot_id();
	if (!json_write(path,journal)) return {ok:false,state:'outcome-arm-journal-failed'};
	if (rill_outcome_schedule_hook) rill_outcome_schedule_hook();
	return {ok:true,attempt:journal,path:path};
};

function rill_outcome_mark_sent_unknown(attempt) {
	let row = attempt?.attempt ?? attempt, path = attempt?.path ?? rill_execution_path(row?.decisionId);
	if (!row || !row.fingerprint || !path) return false;
	row.executionState = 'sent-unknown'; row.transportState = 'request-fully-sent';
	row.mayHaveReachedPeer = true; row.lastSentBootId = boot_id(); row.lastSentMonotonicMs = monotonic_ms();
	if (!json_write(path, row)) return false;
	rill_runtime_counters.rillOutcomeSentUnknown++;
	return true;
}

function rill_outcome_retry_mark(attempt, state, response_loss) {
	attempt.attempt.attemptCount = (attempt.attempt.attemptCount ?? 0) + 1;
	attempt.attempt.lastTransportState = state;
	if (response_loss) { attempt.attempt.mayHaveReachedPeer = true; attempt.attempt.executionState = 'sent-unknown'; }
	else attempt.attempt.executionState = 'outcome-pending';
	let shift = min(6, attempt.attempt.attemptCount);
	attempt.attempt.nextRetryMonotonicMs = monotonic_ms() + min(300000, 5000 * (1 << shift));
	return json_write(attempt.path, attempt.attempt);
}

function rill_retry_pending_outcomes() {
	let retried = 0, retired = 0;
	for (let path in fs.glob(`${persist_dir()}/rill-executions/*.json`) ?? []) {
		let attempt = json_read(path, null);
		if (!attempt) { fs.unlink(path); retired++; continue; }
		if (attempt.executionState == 'reserved' || attempt.executionState == 'executing') {
			if (attempt.createdBootId != boot_id()) { attempt.executionState = 'retired-abandoned'; attempt.retiredReason = 'boot-recovery-no-auto-actuation'; json_write(path, attempt); retired++; }
			continue;
		}
		if (attempt.executionState != 'outcome-pending' && attempt.executionState != 'sent-unknown') continue;
		if ((attempt.nextRetryMonotonicMs ?? 0) > monotonic_ms()) continue;
		rill_report_outcome(attempt.binding, attempt.measurementClass, attempt.reward, attempt.sessionId, { retry: true });
		retried++;
	}
	return { retried: retried, retired: retired };
}

rill_report_outcome = function(binding, measurement, reward, session_id, ctx) {
	ctx = ctx ?? {};
	if (type(binding) != 'object' || !match(binding.decisionId ?? '', /^[0-9a-f]{32}$/)) {
		runtime_history('rill.outcome.skipped', { actionId: binding?.actionId ?? null, reason: 'no-exact-frozen-decision' });
		return { ok: false, state: 'no-exact-frozen-decision' };
	}
	let attempt = rill_outcome_attempt(binding, measurement, session_id, reward);
	if (!attempt.ok) return attempt;
	let payload = {
		contract: RILL_CONTRACT, protocolVersion: RILL_PROTOCOL_VERSION,
		requestId: sprintf('outcome-%d', monotonic_ms()), op: 'outcome', validated: true,
		decisionId: binding.decisionId, contextKey: binding.contextKey, actionId: binding.actionId,
		sessionId: session_id, goal: binding.goal, modelGeneration: binding.modelGeneration, reward: reward
	};
	rill_runtime_counters.rillOutcomeAttempts++;
	let r = rill_send(payload, attempt, rill_outcome_mark_sent_unknown);
	if (!r.ok) {
		if (!rill_outcome_retry_mark(attempt, r.state, r.fullySent === true))
			return { ok: false, state: 'outcome-retry-journal-failed' };
		rill_runtime_counters.rillOutcomeRetryableFailures++;
		runtime_history('rill.outcome.retryable', { actionId: binding.actionId, decisionId: binding.decisionId, measurementClass: measurement, state: r.state });
		return r;
	}
	let envelope = rill_validate_response_envelope(payload, r.response);
	if (!envelope.ok) {
		if (!rill_outcome_retry_mark(attempt, envelope.error, true))
			return { ok: false, state: 'outcome-retry-journal-failed' };
		rill_runtime_counters.rillOutcomeRetryableFailures++;
		runtime_history('rill.outcome.retryable', { actionId: binding.actionId, decisionId: binding.decisionId, measurementClass: measurement, state: envelope.error });
		return { ok: false, state: envelope.error, response: r.response };
	}
	let validated = rill_validate_outcome_response(payload, r.response);
	if (validated.ok) {
		fs.unlink(attempt.path);
		rill_binding_consume(binding);
		rill_runtime_counters.rillOutcomeAccepted++;
		runtime_history('rill.outcome.accepted', { actionId: binding.actionId, decisionId: binding.decisionId, accepted: true, measurementClass: measurement });
		return { ok: true, accepted: true, decisionId: binding.decisionId, response: r.response };
	}
	let code = r.response?.error?.code ?? validated.error;
	if (code == 'duplicateFeedback' && attempt.attempt.mayHaveReachedPeer === true && attempt.attempt.fingerprint == rill_outcome_fingerprint(binding, session_id, reward) && attempt.attempt.ownerId == binding.ownerId) {
		fs.unlink(attempt.path);
		rill_binding_consume(binding);
		rill_runtime_counters.rillOutcomeReconciled++;
		runtime_history('rill.outcome.reconciled', { actionId: binding.actionId, decisionId: binding.decisionId, measurementClass: measurement, reason: 'same-attempt-already-applied' });
		return { ok: true, accepted: true, reconciled: true, decisionId: binding.decisionId, response: r.response };
	}
	if (r.response?.error?.retryable === true) {
		if (!rill_outcome_retry_mark(attempt, code, false))
			return { ok: false, state: 'outcome-retry-journal-failed' };
		rill_runtime_counters.rillOutcomeRetryableFailures++;
		runtime_history('rill.outcome.retryable', { actionId: binding.actionId, decisionId: binding.decisionId, measurementClass: measurement, state: code });
		return { ok: false, state: code, retryable: true, response: r.response };
	}
	fs.unlink(attempt.path);
	rill_binding_retire(binding, code);
	rill_runtime_counters.rillOutcomeTerminalFailures++;
	return { ok: false, state: code, retryable: false, response: r.response };
};

function push_unique(dst, value) {
	if (index(dst, value) < 0) push(dst, value);
}

function merge_profile(id, seen) {
	if (seen[id]) return { ok: false, error: `profile-cycle:${id}` };
	seen[id] = true;
	let p = json_read(`${PROFILE_DIR}/${safe_name(id)}.json`, null);
	if (!p) return { ok: false, error: `profile-not-found:${id}` };
	let out = {
		id: id, chain: [], requiredPackages: [], recommendedPackages: [], conditionalPackages: [],
		expectedCommands: [], expectedCapabilities: [], targets: []
	};
	for (let parent in p.extends ?? []) {
		let m = merge_profile(parent, seen);
		if (!m.ok) return m;
		for (let x in m.profile.chain) push_unique(out.chain, x);
		for (let x in m.profile.requiredPackages) push_unique(out.requiredPackages, x);
		for (let x in m.profile.recommendedPackages) push_unique(out.recommendedPackages, x);
		for (let x in m.profile.expectedCommands) push_unique(out.expectedCommands, x);
		for (let x in m.profile.expectedCapabilities) push_unique(out.expectedCapabilities, x);
		for (let x in m.profile.targets) push_unique(out.targets, x);
		for (let x in m.profile.conditionalPackages) push(out.conditionalPackages, x);
	}
	push_unique(out.chain, id);
	for (let x in p.requiredPackages ?? []) push_unique(out.requiredPackages, x);
	for (let x in p.recommendedPackages ?? []) push_unique(out.recommendedPackages, x);
	for (let x in p.expectedCommands ?? []) push_unique(out.expectedCommands, x);
	for (let x in p.expectedCapabilities ?? []) push_unique(out.expectedCapabilities, x);
	for (let x in p.targets ?? []) push_unique(out.targets, x);
	for (let x in p.conditionalPackages ?? []) push(out.conditionalPackages, x);
	seen[id] = false;
	return { ok: true, profile: out };
}

function command_exists(name) {
	if (!match(name, /^[A-Za-z0-9_.+-]+$/)) return false;
	for (let dir in [ '/usr/sbin', '/usr/bin', '/sbin', '/bin' ])
		if (fs.access(`${dir}/${name}`, 'x')) return true;
	return false;
}

function route_context(wan) {
	let fallback = wan ? sprintf('%s:%s:%s', wan.interface, wan.proto ?? 'unknown', wan.device ?? wan.l3_device ?? 'unknown') : 'unresolved';
	if (!command_exists('ip'))
		return { identity: fallback == 'unresolved' ? 'unresolved' : `netifd:${fnv1a32(fallback)}`, provider: 'netifd-fallback', resolved: fallback != 'unresolved', evidence: { fallback: fallback } };
	let v4 = run([ 'ip', '-j', '-4', 'route', 'show', 'table', 'all', 'default' ]);
	let v6 = run([ 'ip', '-j', '-6', 'route', 'show', 'table', 'all', 'default' ]);
	let rules4 = run([ 'ip', '-j', '-4', 'rule', 'show' ]), rules6 = run([ 'ip', '-j', '-6', 'rule', 'show' ]);
	let v4rows=json_rows(v4.out), v6rows=json_rows(v6.out), r4rows=json_rows(rules4.out), r6rows=json_rows(rules6.out);
	let devices=[];
	if (wan) for (let d in [ wan.device, wan.l3_device ]) if (d && index(devices,d)<0) push(devices,d);
	let selected4 = wan ? filter(v4rows,function(r){return route_row_matches_devices(r,devices);}) : v4rows;
	let selected6 = wan ? filter(v6rows,function(r){return route_row_matches_devices(r,devices);}) : v6rows;
	let resolved = length(selected4) > 0 || length(selected6) > 0;
	if (!resolved)
		return { identity: fallback == 'unresolved' ? 'unresolved' : `netifd:${fnv1a32(fallback)}`, provider: 'netifd-fallback', resolved: false, evidence: { fallback:fallback, expectedDevices:devices, ipErrors:[v4.rc,v6.rc,rules4.rc,rules6.rc] } };
	let c4=canonical_rows(selected4), c6=canonical_rows(selected6), cr4=canonical_rows(r4rows), cr6=canonical_rows(r6rows);
	let raw=sprintf('wan=%s\ndevices=%s\nv4=%s\nv6=%s\nrules4=%s\nrules6=%s',wan?.interface ?? 'global',join(',',devices),join('|',c4),join('|',c6),join('|',cr4),join('|',cr6));
	return {
		identity:`route-v3:${fnv1a32(raw)}`, provider:'ip-full+rtnl-events', resolved:true,
		evidence:{ expectedDevices:devices, ipv4Default:selected4, ipv6Default:selected6, ipv4Rules:r4rows, ipv6Rules:r6rows }
	};
}

function topology() {
	let now = monotonic_ms();
	if (topology_cache != null && (now - topology_cache_ms) < TOPOLOGY_MIN_INTERVAL_MS)
		return topology_cache;
	let dump=interface_dump(), interfaces=[], lan=null;
	for (let i in dump.interface ?? []) {
		let name=i.interface, l3=i.l3_device ?? i.device ?? null;
		push(interfaces,{name:name,l3Device:l3,up:i.up ?? false,proto:i.proto ?? null,device:i.device ?? null});
		if (name == 'lan') lan=i;
	}
	/* WAN candidates come from runtime route/rule evidence first; the old
	 * name-based wan/wan-N discovery is only a fallback on images with no ip
	 * route evidence, so custom-named WANs are never dropped for failing a
	 * name pattern.  An explicit `wan` interface still wins as primary. */
	let wans = wan_candidates_evidence();
	if (!length(wans)) {
		for (let i in dump.interface ?? [])
			if (i.interface == 'wan' || match(i.interface ?? '', /^wan[0-9]+$/)) push(wans, i);
	}
	sort(wans,function(a,b){ if (a.interface == 'wan') return -1; if (b.interface == 'wan') return 1; return `${a.interface}` > `${b.interface}` ? 1 : -1; });
	let devices=netdevs(), paths=[];
	for (let wi=0; wi<length(wans); wi++) {
		let wan=wans[wi], path_targets=[], underlay=underlay_chain(wan);
		let wan_target=underlay?.target?.stableId ?? null;
		if (!wan_target) for (let r in target_refs()) if (r.logicalRole == 'wan-underlay' && (r.selector?.interface == wan.interface || wi == 0)) { wan_target=r.stableId; break; }
		if (wan_target) push(path_targets,wan_target);
		let route=route_context(wan), specific=`path:lan-to-${safe_name(wan.interface ?? `wan${wi}`)}`;
		let entry={id:specific,workloadClass:derive_workload({id:specific,proto:wan?.proto ?? null,underlayChain:underlay?.chain ?? []}),lanInterface:lan?.interface ?? 'lan',wanInterface:wan?.interface ?? `wan${wi}`,routeIdentity:route.identity,routeProvider:route.provider,routeResolved:route.resolved,routeEvidence:route.evidence,targetRefs:path_targets,underlayChain:underlay?.chain ?? []};
		if (wi == 0) {
			let primary={}; for (let k in keys(entry)) primary[k]=entry[k]; primary.id='path:lan-to-wan'; push(paths,primary);
			if (specific != 'path:lan-to-wan') push(paths,entry);
		} else push(paths,entry);
	}
	if (!length(paths)) {
		let route=route_context(null);
		push(paths,{id:'path:lan-to-wan',workloadClass:['plain_forwarding'],lanInterface:lan?.interface ?? 'lan',wanInterface:'wan',routeIdentity:route.identity,routeProvider:route.provider,routeResolved:route.resolved,routeEvidence:route.evidence,targetRefs:[],underlayChain:[]});
	}
	let primary=paths[0], local_targets=primary?.targetRefs ?? [];
	/* The local-endpoint path has no LAN interface.  Emit the empty string so
	 * the runtime output conforms to the formal topology schema which declares
	 * lanInterface as a string (never null). */
	push(paths,{id:'path:local-endpoint',workloadClass:derive_workload({id:'path:local-endpoint'}),lanInterface:'',wanInterface:primary?.wanInterface ?? 'wan',routeIdentity:primary?.routeIdentity ?? 'unresolved',routeProvider:primary?.routeProvider ?? 'unresolved',routeResolved:primary?.routeResolved ?? false,routeEvidence:primary?.routeEvidence ?? {},targetRefs:local_targets,underlayChain:[]});
	topology_cache = {schemaVersion:2,topologyGeneration:topology_generation,interfaces:interfaces,devices:devices,wanCandidates:map(wans,function(w){return w.interface;}),paths:paths};
	topology_cache_ms = now;
	return topology_cache;
}

function nft_snapshot() {
	/* Canonical structural snapshot of the live nft ruleset.  Volatile fields
	 * (handle/packets/bytes) are dropped so the snapshot reflects topology,
	 * not transient traffic.  Returns { items, parsed, canonical } or null. */
	if (!command_exists('nft')) return null;
	let r = run([ 'nft', '-j', 'list', 'ruleset' ]);
	if (r.rc != 0) return null;
	let root = null;
	try { root = json(r.out); } catch (e) { return null; }
	let items = root?.nftables ?? [];
	if (!length(items)) return null;
	let parsed = [], parts = [];
	for (let it in items) {
		let kind = length(keys(it)) ? keys(it)[0] : null;
		if (kind == 'metainfo') continue;
		push(parsed, it);
		push(parts, nft_canon(it));
	}
	if (!length(parts)) return null;
	sort(parts);
	return { items: parts, parsed: parsed, canonical: join('\n', parts) };
}

function rill_advisory_get() {
	/* Latest valid advisory for UI display.  Invalidated on ANY drift
	 * (topology generation, route identity, integration fingerprint, goal) or
	 * on action disappearance / decision TTL expiry — fail-closed: a stale
	 * advisory is never surfaced as if it were current.  Keep this definition
	 * after topology()/nft_snapshot(): raw ucode resolves callees at definition
	 * time and the shipped daemon has no source transformation. */
	if (!rill_advisory) return null;
	let a = rill_advisory;
	if (monotonic_ms() > a.expiresMonotonicMs) { rill_advisory = null; return null; }
	let topo = topology();
	if ((a.topologyGeneration ?? null) != topology_generation) { rill_advisory = null; return null; }
	let route = topo?.paths?.[0]?.routeIdentity ?? 'unresolved';
	if ((a.routeIdentity ?? 'unresolved') != route) { rill_advisory = null; return null; }
	if ((a.integrationFingerprint ?? '') != integration_fingerprint([], nft_snapshot())) { rill_advisory = null; return null; }
	if ((a.goal ?? '') != goal()) { rill_advisory = null; return null; }
	if (rill_binding_peek(a.decisionId) == null) { rill_advisory = null; return null; }
	return a;
}

function nft_ruleset_fingerprint() {
	/* Canonical live nft ruleset identity, no flow masking (Blocker B).
	 * Returns the structural hash of the FULL ruleset or null when nft is
	 * unavailable. */
	let snap = nft_snapshot();
	if (snap == null) return null;
	return sprintf('nft-v2:%s', fnv1a32(snap.canonical));
}

function dns_health() {
	if (!command_exists('nslookup')) return null;
	let host = cfg('main.health_dns_name', 'openwrt.org');
	if (!match(host, /^[A-Za-z0-9.-]+$/)) return null;
	return run([ 'nslookup', host ]).rc == 0;
}

function primary_path(path_id) {
	/* An explicit path id must resolve exactly.  A caller-provided path that
	 * does not exist is an error, never a silent fallback to the primary path:
	 * recording one evaluationPath while evaluating another would pollute
	 * every A/B attribution.  Only an absent path id may default to primary. */
	if (path_id != null && length(`${path_id}`)) {
		let topo = topology();
		for (let p in topo.paths ?? []) if (p.id == path_id) return p;
		return null;
	}
	return topology().paths?.[0] ?? null;
}

function workload_for_paths(path_ids) {
	/* An action's workload is the union of its affected/evaluation paths'
	 * workload classes, never a hard-coded default. */
	let wl = [];
	for (let path_id in path_ids ?? []) {
		let p = primary_path(path_id);
		for (let w in p?.workloadClass ?? []) push_unique_wl(wl, w);
	}
	if (!length(wl)) push_unique_wl(wl, 'plain_forwarding');
	return wl;
}

function baseline_health(path_id) {
	let mem = meminfo();
	let load = split(trimstr(read('/proc/loadavg') ?? '0 0 0'), ' ');
	let dump = interface_dump();
	let wan_up = null, lan_up = null;
	let ipv4 = null, ipv6 = null;
	let path = path_id != null ? primary_path(path_id) : null;
	for (let i in dump.interface ?? []) {
		if (i.interface == 'lan') lan_up = i.up ?? false;
		let is_wan = i.interface == 'wan' || match(i.interface ?? '', /^wan[0-9]*$/);
		/* Path-specific health must watch the WAN interface of the evaluated
		 * path, not just the primary WAN.  A secondary-wan experiment must be
		 * guarded against regressions on that same interface. */
		if (path && i.interface == path.wanInterface) {
			wan_up = i.up ?? false;
			ipv4 = length(i['ipv4-address'] ?? []) > 0;
			ipv6 = length(i['ipv6-address'] ?? []) > 0 || length(i['ipv6-prefix'] ?? []) > 0;
		} else if (!path && (i.interface == 'wan' || (wan_up == null && is_wan))) {
			wan_up = i.up ?? false;
			ipv4 = length(i['ipv4-address'] ?? []) > 0;
			ipv6 = length(i['ipv6-address'] ?? []) > 0 || length(i['ipv6-prefix'] ?? []) > 0;
		}
	}
	let topo = topology();
	return {
		schemaVersion: 2, capturedMonotonicMs: monotonic_ms(), bootId: boot_id(),
		lan: lan_up, wan: wan_up, dns: dns_health(), ipv4: ipv4, ipv6: ipv6,
		proxy: proxy_health(), vpn: vpn_health(), route: ((path?.routeResolved ?? topo.paths[0]?.routeResolved ?? false) === true) ? true : false,
		evaluationPath: path?.id ?? null,
		memAvailableKiB: mem.MemAvailable ?? 0,
		load1: +(load[0] ?? '0'), cpu: cpu_stat(), recentOom: recent_oom_state(),
		stateStorageWritable: storage_writable(state_dir()), persistentStorageWritable: storage_writable(persist_dir()),
		thermal: thermal_health()
	};
}

function system_guard() {
	let h = baseline_health();
	let reasons = [];
	let max_load_per_cpu = max(1, int_cfg('main.max_load_per_cpu', 2));
	let max_steal_pct = max(1, int_cfg('main.max_cpu_steal_percent', 20)) / 100;
	let max_temp = max(60000, int_cfg('main.max_thermal_millicelsius', 90000));
	if (h.memAvailableKiB > 0 && h.memAvailableKiB < 16384) push(reasons, 'low-memory');
	if (h.recentOom) push(reasons, 'recent-oom');
	if (h.load1 > (h.cpu?.count ?? 1) * max_load_per_cpu) push(reasons, 'high-cpu-load');
	if ((h.cpu?.stealPct ?? 0) > max_steal_pct) push(reasons, 'high-cpu-steal');
	if (h.thermal?.available && (h.thermal.maxMilliCelsius ?? 0) >= max_temp) push(reasons, 'thermal-hot');
	if (!h.stateStorageWritable) push(reasons, 'state-storage-unavailable');
	if (!h.persistentStorageWritable) push(reasons, 'persistent-storage-unavailable');
	return { pass: length(reasons) == 0, reasons: reasons, health: h };
}

function telemetry_snapshot() {
	let dev = {};
	for (let line in split(read('/proc/net/dev') ?? '', '\n')) {
		let m = match(line, /^\s*([^:]+):\s*([0-9]+)\s+[0-9]+\s+[0-9]+\s+([0-9]+).*?\s([0-9]+)\s+[0-9]+\s+[0-9]+\s+([0-9]+)/);
		if (m) dev[trimstr(m[1])] = { rxBytes: +m[2], rxDrop: +m[3], txBytes: +m[4], txDrop: +m[5] };
	}
	return {
		monotonicMs: monotonic_ms(), bootId: boot_id(), topologyGeneration: topology_generation,
		softnet: softnet(), interfaces: dev, health: baseline_health()
	};
}

function compatibility(action_id, target, path_id) {
	let integ = integration_state();
	let explicit = path_id != null && length(`${path_id}`);
	let eval_path = explicit ? primary_path(path_id) : (topology().paths?.[0] ?? null);
	let blockers = [], warnings = [];
	if (explicit && !eval_path)
		push(blockers, 'evaluation-path-not-found');
	if (action_id == 'fastpath.hardware_flow_offload' && integ.sqm)
		push(blockers, 'HFO + SQM is blocked');
	if (action_id == 'qdisc.replace' && (integ.sqm || integ.qosify))
		push(blockers, 'qdisc replacement conflicts with SQM/qosify');
	if ((action_id == 'fastpath.software_flow_offload' || action_id == 'fastpath.third_party_sfe') && integ.openclash)
		push(warnings, 'SFE/SFO with OpenClash is benchmark-only');
	if ((integ.mwan3 || integ.pbr) && ((eval_path?.routeResolved ?? false) != true || eval_path?.routeProvider != 'ip-full+rtnl-events'))
		push(blockers, 'multi-WAN/PBR evaluation path has no resolved WAN-specific route identity');
	if (target && match(target.runtimeName ?? '', /^(veth|docker|br-)/))
		push(blockers, 'virtual/container device is not a physical NIC tuning target');
	return { allowed: length(blockers) == 0, blockers: blockers, warnings: warnings };
}

function candidate_actions() {
	let actions = [];
	let plat = platform_info();
	for (let ref in target_refs()) {
		let ring = ethtool_ring(ref.runtimeName);
		if (plat.hyperv && ref.driver == 'hv_netvsc' && ring) {
			let rx_need = ring.rxCurrent != null && ring.rxCurrent < 1024 && ring.rxMax != null && ring.rxMax >= 1024;
			let tx_need = ring.txCurrent != null && ring.txCurrent < 1024 && ring.txMax != null && ring.txMax >= 1024;
			if (rx_need || tx_need) {
				let affected_paths=[];
				for (let p in topology().paths ?? [])
					if (p.id != 'path:local-endpoint' && index(p.targetRefs ?? [], ref.stableId) >= 0) push_unique(affected_paths,p.id);
				if (!length(affected_paths)) continue;
				push(actions, {
					schemaVersion: 2,
					id: 'nic.ring.floor', applyScope: 'device', applyTarget: ref.stableId,
					affectedTargets: [ ref.stableId ], affectedPaths: affected_paths,
					evaluationPaths: affected_paths, workloadClass: workload_for_paths(affected_paths),
					params: { rxFloor: rx_need ? 1024 : ring.rxCurrent, txFloor: tx_need ? 1024 : ring.txCurrent },
					risk: 'safe', requiresBenchmark: false, persistenceClass: 'pm_policy_replay',
					commitPolicy: 'policy_replay_on_accept', reapplyTriggers: [ 'boot', 'device_up', 'topology_change' ],
					requiredLocks: [ `netdev:${ref.stableId}` ], requiresCommitConfirm: false,
					requiresLinkVerification: true,
					reason: 'Hyper-V hv_netvsc ring is below the conservative 1024 floor while hardware maximum supports it.'
				});
			}
		}
	}
	return actions;
}

function find_action(action_id, target) {
	for (let a in candidate_actions())
		if (a.id == action_id && (!target || a.applyTarget == target))
			return a;
	return null;
}

function benchmark_netdev(path_id) {
	let path = primary_path(path_id);
	for (let sid in path?.targetRefs ?? []) {
		let ref = resolve_target(sid);
		if (ref && ref.runtimeName && !match(ref.runtimeName, /^(lo|br-|veth|docker)/)) return ref;
	}
	return null;
}

function benchmark_provider_plan(action_id, path_id) {
	let ref = benchmark_netdev(path_id);
	if (action_id == 'network.backlog') {
		let path = '/proc/sys/net/core/netdev_max_backlog', before = sysctl_value(path);
		if (before == null) return { ok:false, error:'provider-unavailable:netdev_max_backlog' };
		let v = min(65536, max(1000, (+before) * 2));
		if (`${v}` == before) v = max(1000, int(+before * 3 / 4));
		return { ok:true, kind:'sysctl', resource:'sysctl:net.core.netdev_max_backlog', path:path, before:before, candidate:`${v}` };
	}
	if (action_id == 'network.budget') {
		let path = '/proc/sys/net/core/netdev_budget', before = sysctl_value(path);
		if (before == null) return { ok:false, error:'provider-unavailable:netdev_budget' };
		let v = min(4096, max(300, (+before) * 2));
		if (`${v}` == before) v = max(300, int(+before * 3 / 4));
		return { ok:true, kind:'sysctl', resource:'sysctl:net.core.netdev_budget', path:path, before:before, candidate:`${v}` };
	}
	if (action_id == 'network.buffers') {
		let path = '/proc/sys/net/core/rmem_max', before = sysctl_value(path);
		if (before == null) return { ok:false, error:'provider-unavailable:rmem_max' };
		let v = min(67108864, max(4194304, (+before) * 2));
		if (`${v}` == before) v = max(4194304, int(+before * 3 / 4));
		return { ok:true, kind:'sysctl', resource:'sysctl:net.core.rmem_max', path:path, before:before, candidate:`${v}` };
	}
	if (action_id == 'network.busy_poll') {
		let path = '/proc/sys/net/core/busy_poll', before = sysctl_value(path);
		if (before == null) return { ok:false, error:'provider-unavailable:busy_poll' };
		let v = (+before) > 0 ? '0' : '50';
		return { ok:true, kind:'sysctl', resource:'sysctl:net.core.busy_poll', path:path, before:before, candidate:v };
	}
	if (action_id == 'netdev.tx_queue_len') {
		if (!ref) return { ok:false, error:'provider-unavailable:path-netdev' };
		let path = `/sys/class/net/${ref.runtimeName}/tx_queue_len`, before = sysctl_value(path);
		if (before == null || !command_exists('ip')) return { ok:false, error:'provider-unavailable:txqueuelen' };
		let v = min(10000, max(1000, (+before) * 2));
		if (`${v}` == before) v = (+before) == 1000 ? 2000 : 1000;
		return { ok:true, kind:'txqueuelen', resource:`netdev:${ref.stableId}:txqueuelen`, targetRef:ref, before:before, candidate:`${v}` };
	}
	if (action_id == 'nic.coalescing') {
		if (!ref || !command_exists('ethtool')) return { ok:false, error:'provider-unavailable:coalescing-target' };
		let r = run([ 'ethtool', '-c', ref.runtimeName ]);
		if (r.rc != 0) return { ok:false, error:'provider-unavailable:coalescing' };
		let m = match(r.out, /rx-usecs:\s*([0-9]+)/);
		if (!m) return { ok:false, error:'provider-unavailable:rx-usecs' };
		let before=m[1], v=(+before)==0 ? 16 : min(256, (+before)*2);
		if (`${v}` == before) v = (+before) == 16 ? 32 : 16;
		return { ok:true, kind:'coalescing', resource:`netdev:${ref.stableId}:coalescing`, targetRef:ref, before:before, candidate:`${v}` };
	}
	if (action_id == 'tcp.cc') {
		let path='/proc/sys/net/ipv4/tcp_congestion_control', before=sysctl_value(path);
		let avail=split(trimstr(read('/proc/sys/net/ipv4/tcp_available_congestion_control') ?? ''), /\s+/);
		if (before == null || length(avail) < 2) return { ok:false, error:'provider-unavailable:tcp-cc' };
		let candidate=null;
		for (let preferred in [ 'bbr', 'cubic', 'reno' ]) if (preferred != before && index(avail, preferred) >= 0) { candidate=preferred; break; }
		if (!candidate) for (let x in avail) if (x != before) { candidate=x; break; }
		if (!candidate) return { ok:false, error:'provider-unavailable:no-alternate-cc' };
		return { ok:true, kind:'sysctl', resource:'sysctl:net.ipv4.tcp_congestion_control', path:path, before:before, candidate:candidate };
	}
	if (action_id == 'service.irqbalance') {
		if (!file_exists('/etc/init.d/irqbalance')) return { ok:false, error:'provider-unavailable:irqbalance' };
		let before = service_running('irqbalance') ? 'running' : 'stopped';
		return { ok:true, kind:'service', resource:'service:irqbalance', service:'irqbalance', before:before, candidate: before == 'running' ? 'stopped' : 'running' };
	}
	if (action_id == 'fastpath.software_flow_offload' || action_id == 'fastpath.hardware_flow_offload') {
		let option = action_id == 'fastpath.software_flow_offload' ? 'flow_offloading' : 'flow_offloading_hw';
		let key=`firewall.@defaults[0].${option}`, before=uci_get(key);
		if (action_id == 'fastpath.hardware_flow_offload' && (uci_get('firewall.@defaults[0].flow_offloading') ?? '0') != '1')
			return { ok:false, error:'provider-unavailable:hfo-requires-sfo' };
		return { ok:true, kind:'uci-firewall', resource:`uci:${key}`, key:key, before:before, candidate: (before ?? '0') == '1' ? '0' : '1' };
	}
	if (action_id == 'cpu.governor') {
		let rows=[];
		for (let p in fs.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor') ?? []) {
			let before=trimstr(read(p)); if (!length(before)) continue;
			let avail=split(trimstr(read(replace(p, /scaling_governor$/, 'scaling_available_governors')) ?? ''), /\s+/);
			let candidate = before != 'performance' && index(avail,'performance') >= 0 ? 'performance' : (before != 'schedutil' && index(avail,'schedutil') >= 0 ? 'schedutil' : null);
			if (!candidate) return { ok:false, error:'provider-unavailable:no-alternate-governor' };
			push(rows, { path:p, before:before, candidate:candidate });
		}
		if (!length(rows)) return { ok:false, error:'provider-unavailable:cpufreq' };
		return { ok:true, kind:'governor', resource:'cpu:governor', rows:rows, before:'per-cpu', candidate:'per-cpu' };
	}
	/* qdisc options are not safely round-trippable from the generic tc dump and
	 * third-party SFE has no stable provider contract.  A complete provider is
	 * therefore an explicit capability refusal rather than an inexact restore. */
	if (action_id == 'qdisc.replace') return { ok:false, error:'provider-unavailable:exact-qdisc-restore-not-proven' };
	if (action_id == 'fastpath.third_party_sfe') return { ok:false, error:'provider-unavailable:no-generic-third-party-sfe-contract' };
	return { ok:false, error:'provider-unavailable:unknown-action' };
}

function benchmark_catalog() {
	let topo=topology(), integ=integration_state(), ids=[
		'service.irqbalance','network.backlog','network.budget','network.buffers','network.busy_poll','netdev.tx_queue_len','nic.coalescing','tcp.cc','qdisc.replace','fastpath.software_flow_offload','fastpath.hardware_flow_offload','fastpath.third_party_sfe','cpu.governor'
	], out=[];
	let forwarding=[];
	for (let p in topo.paths ?? []) if (p.id != 'path:local-endpoint' && (p.routeResolved ?? false)) push(forwarding,p.id);
	for (let id in ids) {
		let semantics=benchmark_semantics(id), paths=semantics=='local' ? ['path:local-endpoint'] : forwarding, usable=[], provider_rows=[], blockers=[];
		for (let path_id in paths) {
			let path=primary_path(path_id), c=compatibility(id,null,path_id), plan=c.allowed ? benchmark_provider_plan(id,path_id) : {ok:false,error:'compatibility-blocked'};
			if (c.allowed && plan.ok && path) { push(usable,path_id); push(provider_rows,{pathId:path_id,kind:plan.kind,resource:plan.resource}); }
			else push(blockers,{pathId:path_id,error:plan.error ?? 'compatibility-blocked',compatibility:c});
		}
		/* Keep provider-level refusals visible even when no route is currently
		 * usable, so qdisc/SFE absence is a capability decision, not a hidden gap. */
		if (!length(paths)) {
			let path_id=semantics=='local'?'path:local-endpoint':'path:lan-to-wan', c=compatibility(id,null,path_id), plan=c.allowed?benchmark_provider_plan(id,path_id):{ok:false,error:'compatibility-blocked'};
			push(blockers,{pathId:path_id,error:plan.error ?? 'route-unresolved',compatibility:c});
		}
		push(out,{id:id,applyScope:length(provider_rows) && match(provider_rows[0].resource ?? '',/^netdev:/)?'device':'system',risk:'benchmark',oneVariableDefault:true,evaluationSemantics:semantics,evaluationPaths:usable,requiresExplicitEndpoints:true,requiredClientRole:semantics=='local'?'router-local-client':'lan-client',status:length(usable)?'endpoint-required':'blocked',providers:provider_rows,blockers:blockers,integrationState:integ});
	}
	return out;
}

function benchmark_action_contract(action_id, path_id, plan) {
	let scope=plan.targetRef ? 'device' : (plan.kind == 'service' || plan.kind == 'uci-firewall' ? 'service' : 'system');
	let target=plan.targetRef?.stableId ?? (plan.kind == 'service' ? `service:${plan.service}` : (plan.kind == 'uci-firewall' ? 'service:firewall' : (plan.kind == 'governor' ? 'system:cpu' : 'system:kernel')));
	return {
		schemaVersion:2,id:action_id,applyScope:scope,applyTarget:target,affectedTargets:[target],affectedPaths:[path_id],evaluationPaths:[path_id],
		workloadClass:primary_path(path_id)?.workloadClass ?? ['plain_forwarding'],risk:'benchmark',requiresBenchmark:true,persistenceClass:'runtime',
		commitPolicy:'rollback_after_benchmark',reapplyTriggers:[],requiredLocks:[plan.resource],requiresCommitConfirm:true
	};
}

function benchmark_apply_candidate(action_id, path_id, session_id, rill_decision) {
	let plan=benchmark_provider_plan(action_id, path_id);
	if (!plan.ok) return plan;
	let action=benchmark_action_contract(action_id, path_id, plan);
	let tx=tx_new(action, rill_decision ? 'benchmark-rill' : 'manual', rill_decision); tx.result={ benchmarkSessionId:session_id };
	if (!tx_save(tx)) {
		if (rill_decision) rill_binding_release_reservation(rill_decision, 'benchmark-transaction-journal-write-failed-before-mutation');
		return { ok:false, error:'transaction-journal-write-failed' };
	}
	let lock=acquire_locks(action.requiredLocks, tx.transactionId);
	if (!lock.ok) {
		tx.state='failed'; tx.result={error:'lock-conflict',detail:lock,benchmarkSessionId:session_id}; tx_save(tx);
		if (rill_decision) rill_binding_release_reservation(rill_decision, 'benchmark-transaction-lock-conflict-before-mutation');
		return {ok:false,error:'lock-conflict',transaction:tx};
	}
	tx.state='locked'; if (!tx_save(tx)) {
		release_locks(tx.requiredLocks,tx.transactionId);
		if (rill_decision) rill_binding_release_reservation(rill_decision, 'benchmark-locked-journal-write-failed-before-mutation');
		return {ok:false,error:'transaction-journal-write-failed'};
	}
	let before_health=baseline_health(path_id);
	tx.before={ benchmark:plan, health:before_health }; tx.state='snapshotted';
	if (!tx_save(tx)) {
		release_locks(tx.requiredLocks,tx.transactionId);
		if (rill_decision) rill_binding_release_reservation(rill_decision, 'benchmark-snapshot-journal-write-failed-before-mutation');
		return {ok:false,error:'transaction-journal-write-failed'};
	}
	tx.state='pending'; if (!tx_save(tx)) {
		release_locks(tx.requiredLocks,tx.transactionId);
		if (rill_decision) rill_binding_release_reservation(rill_decision, 'benchmark-pending-marker-write-failed-before-mutation');
		return {ok:false,error:'pending-marker-write-failed'};
	}
	if (rill_decision && !rill_execution_mark_mutation_started(rill_decision)) {
		tx.state='failed'; tx.result={error:'rill-mutation-journal-write-failed',benchmarkSessionId:session_id}; tx_save(tx);
		release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'rill-mutation-journal-write-failed',transaction:tx};
	}
	let candidate_value=plan.kind == 'governor' ? 'candidate' : plan.candidate;
	let restore_value=plan.kind == 'governor' ? 'before' : plan.before;
	let ap=benchmark_provider_apply(plan, candidate_value);
	if (ap.rc != 0) {
		/* Provider application may have partially changed a multi-value target
		 * (for example per-CPU governors, or a UCI delta before firewall reload).
		 * Always attempt exact snapshot restoration before releasing the lock. */
		let rr=benchmark_provider_apply(plan, restore_value), restored=rr.rc == 0 && benchmark_provider_matches(plan, restore_value);
		tx.verification={readBack:'apply-failed',healthRegression:'not-evaluated',rollbackReadBack:restored?'pass':'fail',commitConfirm:'not_armed'};
		tx.state=restored?'rolled_back':'failed'; tx.result={error:'apply-failed',output:ap.out,rollback:restored?'restored':'failed',benchmarkSessionId:session_id};
		tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'apply-failed',rollback:restored?'restored':'failed',transaction:tx};
	}
	tx.state='applied'; tx.applied={ benchmark:plan, candidate:plan.candidate, benchmarkSessionId:session_id };
	if (!tx_save(tx)) {
		let rr=benchmark_provider_apply(plan,restore_value), restored=rr.rc == 0 && benchmark_provider_matches(plan,restore_value);
		tx.verification.rollbackReadBack=restored?'pass':'fail'; tx.state=restored?'rolled_back':'failed'; tx.result={error:'transaction-journal-write-failed-after-apply',rollback:restored?'restored':'failed',benchmarkSessionId:session_id}; tx_save(tx);
		release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'transaction-journal-write-failed-after-apply',rollback:restored?'restored':'failed',transaction:tx};
	}
	let matches=benchmark_provider_matches(plan, candidate_value);
	let hcmp=compare_health(before_health, baseline_health(path_id));
	if (!matches || !hcmp.pass) {
		let rr=benchmark_provider_apply(plan, restore_value);
		let restored=rr.rc == 0 && benchmark_provider_matches(plan, restore_value);
		tx.verification={readBack:matches?'pass':'fail',healthRegression:hcmp.pass?'none':hcmp.failures,rollbackReadBack:restored?'pass':'fail',commitConfirm:'not_required'};
		tx.state=restored?'rolled_back':'failed'; tx.result={error:'verification-failed',rollback:restored?'restored':'failed',benchmarkSessionId:session_id}; tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId);
		return {ok:false,error:'verification-failed',transaction:tx};
	}
	tx.state='verified'; tx.verification={readBack:'pass',healthRegression:'none',commitConfirm:'pending'}; tx.result={benchmarkSessionId:session_id};
	if (!tx_save(tx)) {
		let rr=benchmark_provider_apply(plan,restore_value), restored=rr.rc == 0 && benchmark_provider_matches(plan,restore_value);
		tx.verification.rollbackReadBack=restored?'pass':'fail'; tx.state=restored?'rolled_back':'failed'; tx.result={error:'transaction-journal-write-failed-after-verify',rollback:restored?'restored':'failed',benchmarkSessionId:session_id}; tx_save(tx);
		release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'transaction-journal-write-failed-after-verify',rollback:restored?'restored':'failed'};
	}
	let armed=arm_commit_confirm(tx, max(15,int_cfg('benchmark.candidate_timeout_seconds',120))*1000);
	if (!armed.ok) { rollback_transaction(tx.transactionId,'benchmark-arm-failed'); return {ok:false,error:armed.error}; }
	return { ok:true, transaction:tx, plan:plan };
}

function benchmark_context(path_id, masked_keys) {
	let caps=capabilities(), topo=topology(), path=primary_path(path_id);
	/* Blocker B: fastpath sessions verify the live nft ruleset via expected
	 * delta (nft_comparable) and therefore exclude the nft row from the raw
	 * fingerprint; everything else must match exactly.  The snapshot is stored
	 * on the session so the candidate leg can compute the structural delta. */
	let fastpath = index(masked_keys ?? [], 'fastpath-expected-delta') >= 0;
	let nft = nft_snapshot();
	return {
		capabilityHash:capability_hash(caps), topologyGeneration:topology_generation,
		routeIdentity:path?.routeIdentity ?? 'unresolved', routeProvider:path?.routeProvider ?? null,
		integrationState:integration_state(), integrationFingerprint:integration_fingerprint(masked_keys, fastpath ? null : nft),
		nftSnapshot:nft,
		workloadClass:path?.workloadClass ?? [ 'plain_forwarding' ], goal:goal()
	};
}

function rill_action_descriptor(action_id) {
	for (let action in candidate_actions())
		if (action.id == action_id)
			return { exists: true, kind: 'safe-direct', authority: 'advisory-only', executionAuthority: 'safe-direct', executionPath: 'apply', action: action };
	for (let action in benchmark_catalog())
		if (action.id == action_id && action.status != 'blocked')
			return { exists: true, kind: 'benchmark', authority: 'advisory-only', executionAuthority: 'benchmark', executionPath: 'benchmark_start', action: action };
	return null;
}

function rill_available_actions() {
	let out = map(candidate_actions(), function(a) {
		return { id: a.id, applyScope: a.applyScope, applyTarget: a.applyTarget, evaluationPaths: a.evaluationPaths, risk: a.risk, authority: 'advisory-only', executionAuthority: 'safe-direct', executionPath: 'apply' };
	});
	for (let b in benchmark_catalog()) {
		if (b.status == 'blocked') continue;
		push(out, { id: b.id, applyScope: b.applyScope ?? 'system', applyTarget: null, evaluationPaths: b.evaluationPaths ?? ['path:lan-to-wan'], risk: 'benchmark', authority: 'advisory-only', executionAuthority: 'benchmark', executionPath: 'benchmark_start' });
	}
	return out;
}

function rill_context_key_observe() {
	let caps = capabilities(), topo = topology(), path = topo.paths[0];
	return rill_context_key_build(cfg('main.profile','recommended'), capability_hash(caps), topology_generation,
		path?.id ?? 'path:lan-to-wan', path?.routeIdentity ?? 'unresolved', path?.workloadClass ?? [ 'plain_forwarding' ],
		integration_fingerprint([], nft_snapshot()), goal());
}


function apply_ring(action, options) {
	options = options ?? {};
	let ref = resolve_target(action.applyTarget);
	if (!ref) { if (options.rillDecision) rill_binding_release_reservation(options.rillDecision,'target-unresolved-before-mutation'); return { ok: false, error: 'target-unresolved' }; }
	let comp = compatibility(action.id, ref, action.evaluationPaths?.[0]);
	if (!comp.allowed) { if (options.rillDecision) rill_binding_release_reservation(options.rillDecision,'compatibility-blocked-before-mutation'); return { ok: false, error: 'compatibility-blocked', compatibility: comp }; }
	let guard = system_guard();
	if (!guard.pass) { if (options.rillDecision) rill_binding_release_reservation(options.rillDecision,'health-guard-blocked-before-mutation'); return { ok: false, error: 'health-guard-blocked', guard: guard }; }

	let tx = options.transaction ?? tx_new(action, options.executionSource ?? 'manual', options.rillDecision ?? null);
	if (!tx_save(tx)) {
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'transaction-journal-write-failed');
		return { ok: false, error: 'transaction-journal-write-failed' };
	}
	let lock = acquire_locks(action.requiredLocks, tx.transactionId);
	if (!lock.ok) {
		tx.state = 'failed'; tx.result = { error: 'lock-conflict', detail: lock }; tx_save(tx);
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'lock-conflict-before-mutation');
		return { ok: false, transaction: tx };
	}
	tx.state = 'locked'; if (!tx_save(tx)) {
		release_locks(tx.requiredLocks, tx.transactionId);
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'locked-journal-write-failed-before-mutation');
		return { ok: false, error: 'transaction-journal-write-failed' };
	}
	let before_health = baseline_health();
	let snap = ring_snapshot(ref);
	if (!snap) {
		tx.state = 'failed'; tx.result = { error: 'snapshot-failed' }; tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'snapshot-failed-before-mutation');
		return { ok: false, transaction: tx };
	}
	tx.before = { ring: snap, health: before_health, targetRef: ref };
	tx.state = 'snapshotted'; if (!tx_save(tx)) {
		release_locks(tx.requiredLocks, tx.transactionId);
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'snapshot-journal-write-failed-before-mutation');
		return { ok: false, error: 'transaction-journal-write-failed' };
	}
	tx.state = 'pending';
	if (!tx_save(tx)) {
		tx.state = 'failed'; tx.result = { error: 'pending-marker-write-failed' }; tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
		if (tx.rillDecision) rill_binding_release_reservation(tx.rillDecision, 'pending-marker-write-failed-before-mutation');
		return { ok: false, transaction: tx };
	}
	if (tx.rillDecision && !rill_execution_mark_mutation_started(tx.rillDecision)) {
		tx.state='failed'; tx.result={error:'rill-mutation-journal-write-failed'}; tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId);
		rill_binding_release_reservation(tx.rillDecision, 'mutation-journal-write-failed-before-mutation');
		return {ok:false,error:'rill-mutation-journal-write-failed',transaction:tx};
	}
	let ap = ring_apply(ref, action.params);
	if (ap.rc != 0) {
		tx.state = 'failed'; tx.result = { error: 'apply-failed', output: ap.out }; tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
		return { ok: false, transaction: tx };
	}
	tx.state = 'applied'; tx.applied = action.params;
	if (!tx_save(tx)) {
		let restore=ring_restore(ref,snap), restored=restore.rc == 0 && ring_matches(ref,snap);
		tx.verification.rollbackReadBack=restored?'pass':'fail'; tx.state=restored?'rolled_back':'failed'; tx.result={error:'transaction-journal-write-failed-after-apply',rollback:restored?'restored':'failed'};
		tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'transaction-journal-write-failed-after-apply',transaction:tx};
	}
	let after_ring = ring_snapshot(ref);
	let after_health = baseline_health();
	let hcmp = compare_health(before_health, after_health);
	let readback = after_ring &&
		(action.params.rxFloor == null || after_ring.rxCurrent >= action.params.rxFloor) &&
		(action.params.txFloor == null || after_ring.txCurrent >= action.params.txFloor);
	let link = link_ok(ref);
	if (!readback || !link || !hcmp.pass) {
		let restore = ring_restore(ref, snap);
		let restored = restore.rc == 0 && ring_matches(ref, snap);
		tx.verification = { readBack: readback ? 'pass' : 'fail', link: link ? 'pass' : 'fail', healthRegression: hcmp.pass ? 'none' : hcmp.failures, rollbackReadBack: restored ? 'pass' : 'fail', commitConfirm: 'not_required' };
		tx.state = restored ? 'rolled_back' : 'failed';
		tx.result = { error: 'verification-failed', rollback: restored ? 'restored' : 'failed', rollbackOutput: restore.out ?? '' };
		if (!options.runtimeOnly && restored && tx.rillDecision) {
			let intent=rill_prepare_outcome(tx.rillDecision,'health_only',-1.0,tx.transactionId,'rolled_back');
			if (!intent.ok) { release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'rill-outcome-intent-write-failed',transaction:tx}; }
		}
		if (!tx_save(tx)) { release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'transaction-terminal-journal-write-failed',transaction:tx}; }
		if (!options.runtimeOnly && restored && tx.rillDecision) {
			let armed=rill_arm_outcome(tx.rillDecision);
			if (!armed.ok) { release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'rill-outcome-arm-failed',transaction:tx,detail:armed}; }
		}
		release_locks(tx.requiredLocks, tx.transactionId);
		(options.runtimeOnly ? runtime_history : history)(restored ? 'transaction.rollback' : 'transaction.rollback_failed', tx);
		if (!options.runtimeOnly && restored && tx.rillDecision) rill_report_outcome(tx.rillDecision,'health_only',-1.0,tx.transactionId,{});
		return { ok: false, transaction: tx };
	}
	tx.verification = { readBack: 'pass', link: 'pass', healthRegression: 'none', commitConfirm: action.requiresCommitConfirm ? 'pending' : 'not_required' };
	tx.state = 'verified'; tx.result = { ring: after_ring };
	if (!tx_save(tx)) {
		let restore = ring_restore(ref, snap);
		let restored = restore.rc == 0 && ring_matches(ref, snap);
		tx.state = restored ? 'rolled_back' : 'failed'; tx.result = { error: 'transaction-journal-write-failed', rollback: restored ? 'restored' : 'failed' };
		tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId); return { ok: false, transaction: tx };
	}
	if (action.requiresCommitConfirm) {
		let armed = arm_commit_confirm(tx, max(5, int_cfg('main.commit_confirm_seconds', 30)) * 1000);
		if (!armed.ok) { rollback_transaction(tx.transactionId, 'commit-confirm-arm-failed'); return { ok: false, error: armed.error, transaction: tx }; }
		return { ok: true, awaitingConfirm: true, transaction: tx };
	}
	if (!options.skipPersistence && !persist_ring_policy(ref, action.params, tx.transactionId, snap, after_ring)) {
		let restore = ring_restore(ref, snap);
		let restored = restore.rc == 0 && ring_matches(ref, snap);
		tx.verification.rollbackReadBack = restored ? 'pass' : 'fail';
		tx.state = restored ? 'rolled_back' : 'failed';
		tx.result = { error: 'persistence-failed', rollback: restored ? 'restored' : 'failed' };
		tx_save(tx); release_locks(tx.requiredLocks, tx.transactionId);
		history(restored ? 'transaction.rollback' : 'transaction.rollback_failed', tx);
		return { ok: false, transaction: tx };
	}
	tx.state = 'committed'; tx.result = { ring: after_ring };
	if (!options.runtimeOnly && tx.rillDecision) {
		let intent=rill_prepare_outcome(tx.rillDecision,'health_only',0.0,tx.transactionId,'committed');
		if (!intent.ok) {
			let restore=ring_restore(ref,snap), restored=restore.rc == 0 && ring_matches(ref,snap);
			tx.state=restored?'rolled_back':'failed'; tx.result={error:'rill-outcome-intent-write-failed',rollback:restored?'restored':'failed'}; tx_save(tx); release_locks(tx.requiredLocks,tx.transactionId);
			return {ok:false,error:'rill-outcome-intent-write-failed',transaction:tx};
		}
	}
	if (!tx_save(tx)) {
		/* Do not report success if terminal journal/pending-marker cleanup failed.
		 * For PM-owned policy writes, restore both runtime and policy ownership. */
		let policy=json_read(ring_policy_path(ref.stableId),null); if (policy?.ownerTransactionId == tx.transactionId) fs.unlink(ring_policy_path(ref.stableId));
		let restore=ring_restore(ref,snap), restored=restore.rc == 0 && ring_matches(ref,snap);
		tx.state=restored?'rolled_back':'failed'; tx.result={error:'commit-journal-write-failed',rollback:restored?'restored':'failed'}; tx.verification.rollbackReadBack=restored?'pass':'fail'; tx_save(tx);
		cancel_tx_timer(tx.transactionId); release_locks(tx.requiredLocks,tx.transactionId); history(restored?'transaction.rollback':'transaction.rollback_failed',tx); return {ok:false,error:'commit-journal-write-failed',transaction:tx};
	}
	if (!options.runtimeOnly && tx.rillDecision) {
		let armed=rill_arm_outcome(tx.rillDecision);
		if (!armed.ok) { cancel_tx_timer(tx.transactionId); release_locks(tx.requiredLocks,tx.transactionId); return {ok:false,error:'rill-outcome-arm-failed',transaction:tx,detail:armed}; }
	}
	cancel_tx_timer(tx.transactionId); release_locks(tx.requiredLocks, tx.transactionId);
	(options.runtimeOnly ? runtime_history : history)('transaction.commit', tx);
	if (!options.runtimeOnly && tx.rillDecision)
		rill_report_outcome(tx.rillDecision,'health_only',0.0,tx.transactionId,{});
	return { ok: true, transaction: tx };
}

function apply_action(msg) {
	let action_id = msg?.actionId;
	if (action_id == 'nic.ring.floor') {
		let a = find_action(action_id, msg?.target);
		if (!a) return { ok: false, error: 'no-legal-candidate' };
		let source = msg?.executionSource ?? 'manual', frozen = null, tx = null;
		if (source == 'rill-advisory') {
			tx = tx_new(a, source, null);
			frozen = rill_binding_reserve(msg?.decisionId, action_id, 'safe-direct', 'transaction', tx.transactionId);
			if (!frozen) return { ok: false, error: 'rill-decision-already-reserved' };
			tx.rillDecision = frozen;
		} else if (source != 'manual' || msg?.decisionId != null) {
			return { ok: false, error: 'invalid-execution-source' };
		}
		return apply_ring(a, { executionSource: source, rillDecision: frozen, transaction: tx });
	}
	return { ok: false, error: 'action-not-allowlisted-for-direct-apply', actionId: action_id };
}

function replay_policies(reason) {
	let results = [];
	for (let p in fs.glob(`${persist_dir()}/policies/*.json`) ?? []) {
		let pol = json_read(p, null);
		if (!pol || pol.owner != 'performance_manager' || pol.actionId != 'nic.ring.floor') continue;
		if (reason && length(pol.reapplyTriggers ?? []) && index(pol.reapplyTriggers, reason) < 0 && reason != 'manual') continue;
		let ref = resolve_target(pol.targetRef.stableId);
		if (!ref) { push(results, { policy: pol.actionId, target: pol.targetRef.stableId, status: 'unresolved' }); continue; }
		let ring = ethtool_ring(ref.runtimeName);
		if (!ring) { push(results, { policy: pol.actionId, target: ref.stableId, status: 'capability-missing' }); continue; }
		/* Blocker 4: cede-on-live-drift.  If the value PM left is no longer
		 * present (user/external changed it), replay must NOT overwrite that
		 * live change.  Relinquish ownership instead of reapplying. */
		let owned_ring = pol?.runtimeLease?.ownedRing ?? null;
		if (owned_ring && !ring_matches(ref, owned_ring)) {
			pol.ownershipRelinquished = { reason: 'live-drift', atMonotonicMs: monotonic_ms(), driftRing: ring_snapshot(ref), ownedRing: owned_ring };
			pol.owner = 'external';
			json_write(p, pol);
			push(results, { policy: pol.actionId, target: ref.stableId, status: 'ceded-live-drift' });
			continue;
		}
		let params = pol.params ?? {};
		let need = (params.rxFloor != null && ring.rxCurrent < params.rxFloor) || (params.txFloor != null && ring.txCurrent < params.txFloor);
		if (!need) { push(results, { policy: pol.actionId, target: ref.stableId, status: 'already-satisfied' }); continue; }
		let eval_paths=[];
		for (let path in topology().paths ?? []) if (path.id != 'path:local-endpoint' && index(path.targetRefs ?? [],ref.stableId)>=0) push_unique(eval_paths,path.id);
		if (!length(eval_paths)) { push(results,{policy:pol.actionId,target:ref.stableId,status:'path-unresolved'}); continue; }
		let a = {
			id: 'nic.ring.floor', applyScope: 'device', applyTarget: ref.stableId, affectedTargets: [ref.stableId],
			affectedPaths: eval_paths, evaluationPaths: eval_paths, workloadClass: workload_for_paths(eval_paths),
			params: params, risk: 'safe', requiresBenchmark: false, persistenceClass: 'pm_policy_replay',
			commitPolicy: 'policy_replay_on_accept', reapplyTriggers: pol.reapplyTriggers, requiredLocks: [`netdev:${ref.stableId}`],
			requiresCommitConfirm: false, requiresLinkVerification: true
		};
		let before=ring_snapshot(ref), r = apply_ring(a, { skipPersistence: true, runtimeOnly: true });
		if (r.ok) {
			let owned=ring_snapshot(ref);
			pol.targetRef=ref; pol.schemaVersion=2; pol.runtimeLease={bootId:boot_id(),runtimeName:ref.runtimeName,topologyGeneration:topology_generation,beforeRing:before,ownedRing:owned};
			if (!json_write(p,pol)) {
				let rr=ring_restore(ref,before), restored=rr.rc==0 && ring_matches(ref,before);
				push(results,{policy:pol.actionId,target:ref.stableId,status:'lease-persist-failed',rollback:restored?'restored':'failed'}); continue;
			}
		}
		push(results, { policy: pol.actionId, target: ref.stableId, status: r.ok ? 'reapplied' : 'failed', detail: r.error ?? null });
	}
	return results;
}

function benchmark_start(msg) {
	if (!bool_cfg('benchmark.require_explicit_start', true)) return { ok:false, error:'invalid-config-explicit-start-disabled' };
	let phase=msg?.phase ?? 'begin';
	if (phase != 'begin') {
		let sid=msg?.sessionId, session=sid ? json_read(benchmark_path(sid),null) : null;
		if (!session) return {ok:false,error:'benchmark-session-not-found'};
		/* Every phase re-verifies the FULL frozen context, not only capability
		 * and topology: integration runtime/config fingerprint and workload
		 * class are part of the A/B attribution and must not drift. */
		let nowctx=benchmark_context(session.evaluationPath, benchmark_masked_keys(session.actionId));
		let workload_drift=stable_list_hash('workload',nowctx.workloadClass) != stable_list_hash('workload',session.workloadClass);
		let goal_drift=nowctx.goal != session.goal;
		/* Blocker B: fastpath sessions verify the live nft ruleset by expected
		 * delta — the candidate may toggle EXACTLY the PM flowtable/flow-rule
		 * and nothing else (unrelated flowtable/rule changes fail closed). */
		let nft_drift=false, nft_cmp=null;
		if (index(benchmark_masked_keys(session.actionId) ?? [], 'fastpath-expected-delta') >= 0) {
			nft_cmp=nft_comparable(session.nftSnapshot ?? null, nowctx.nftSnapshot ?? null);
			nft_drift=!nft_cmp.comparable;
		}
		if (nowctx.capabilityHash != session.capabilityHash || nowctx.topologyGeneration != session.topologyGeneration || nowctx.routeIdentity != session.routeIdentity || nowctx.integrationFingerprint != session.integrationFingerprint || nft_drift || workload_drift || goal_drift) {
			if (session.transactionId) rollback_transaction(session.transactionId,'benchmark-context-drift');
			if (session.rillDecision) rill_binding_release_reservation(session.rillDecision, 'benchmark-context-drift-before-mutation');
			release_benchmark_lock(session.benchmarkLock?.domain, session.sessionId);
			session.state='failed'; session.result={validated:false,error:'benchmark-context-drift',nftDelta:nft_cmp}; json_write(benchmark_path(sid),session); return {ok:false,error:'benchmark-context-drift',session:session,nftDelta:nft_cmp};
		}
		if (phase == 'control') {
			if (session.state != 'awaiting_control') return {ok:false,error:'benchmark-not-awaiting-control'};
			let valid=companion_evidence_valid(msg?.evidence,session,'control'); if (!valid.ok) return valid;
			session.controlEvidence=msg.evidence;
			/* Freeze the measurement methodology from the control leg so the
			 * candidate must reproduce it exactly (Blocker 3). */
			session.companion.methodology=measurement_methodology(msg.evidence);
			let applied=benchmark_apply_candidate(session.actionId,session.evaluationPath,session.sessionId,session.rillDecision);
			if (!applied.ok) { benchmark_fail_session(benchmark_path(sid),sid,applied.error); return {ok:false,error:applied.error,session:session,detail:applied}; }
			session.transactionId=applied.transaction.transactionId; session.state='candidate_applied'; session.candidateDeadlineMonotonicMs=applied.transaction.deadlineMonotonicMs;
			if (!json_write(benchmark_path(sid),session)) {
				let rr=rollback_transaction(session.transactionId,'benchmark-session-write-failed');
				release_benchmark_lock(session.benchmarkLock?.domain, sid);
				session.state='failed'; session.result={validated:false,error:'benchmark-session-write-failed',rollback:rr.ok?'restored':'failed'};
				json_write(benchmark_path(sid),session);
				return {ok:false,error:'benchmark-session-write-failed',rollback:rr,session:session};
			}
			history('benchmark.candidate_applied',{sessionId:sid,actionId:session.actionId,transactionId:session.transactionId});
			return {ok:true,stage:'candidate',session:session,companion:session.companion};
		}
		if (phase == 'candidate') {
			if (session.state != 'candidate_applied') return {ok:false,error:'benchmark-not-awaiting-candidate'};
			let valid=companion_evidence_valid(msg?.evidence,session,'candidate'); if (!valid.ok) return valid;
			/* Candidate must reproduce the frozen control methodology exactly.
			 * A mismatch invalidates the A/B: no reward, no Rill outcome. */
			if (!session.companion?.methodology || !methodology_matches(session.companion.methodology,msg.evidence))
				return {ok:false,error:'measurement-methodology-mismatch',session:session};
			let tx=json_read(tx_path(session.transactionId),null);
			if (!tx || tx.state != 'awaiting_confirm') return {ok:false,error:'benchmark-candidate-transaction-not-live'};
			let hcmp=compare_health(tx.before?.health ?? baseline_health(session.evaluationPath),baseline_health(session.evaluationPath));
			let restore=rollback_transaction(session.transactionId,'benchmark-complete');
			if (!restore.ok || !hcmp.pass) { benchmark_fail_session(benchmark_path(sid),sid,!restore.ok?'candidate-rollback-failed':'health-regression'); return {ok:false,error:!restore.ok?'candidate-rollback-failed':'health-regression',health:hcmp,session:session}; }
			session.candidateEvidence=msg.evidence;
			let c0=+session.controlEvidence.bitsPerSecond, c1=+session.candidateEvidence.bitsPerSecond, reward=(c1-c0)/c0;
			session.state='completed'; session.result={validated:true,changedSystemState:true,rolledBack:true,oneVariable:true,reward:reward,controlBitsPerSecond:c0,candidateBitsPerSecond:c1,health:hcmp};
			if (session.rillDecision) {
				let intent=rill_prepare_outcome(session.rillDecision,'controlled_ab',reward,sid,'completed');
				if (!intent.ok) return {ok:false,error:'rill-outcome-intent-write-failed',session:session,detail:intent};
			}
			if (!json_write(benchmark_path(sid),session)) return {ok:false,error:'benchmark-result-write-failed-after-safe-rollback',session:session};
			if (session.rillDecision) {
				let armed=rill_arm_outcome(session.rillDecision);
				if (!armed.ok) return {ok:false,error:'rill-outcome-arm-failed',session:session,detail:armed};
			}
			release_benchmark_lock(session.benchmarkLock?.domain, sid);
			history('benchmark.completed',session);
			if (session.rillDecision)
				rill_report_outcome(session.rillDecision,'controlled_ab',reward,sid,{});
			return {ok:true,stage:'result',session:session};
		}
		return {ok:false,error:'invalid-benchmark-phase'};
	}
	let guard=system_guard(); if (!guard.pass) return {ok:false,error:'health-guard-blocked',guard:guard};
	let action=msg?.actionId ?? 'observe';
	if (action != 'observe' && index(BENCHMARK_ACTIONS,action) < 0) return {ok:false,error:'unknown-benchmark-action'};
	let measurement=msg?.measurementClass ?? cfg('benchmark.default_measurement_class','passive_before_after');
	if (index(['controlled_ab','passive_before_after','health_only'],measurement)<0) return {ok:false,error:'invalid-measurement-class'};
	let semantics=action == 'observe' ? 'forwarding' : benchmark_semantics(action);
	let expected_path=semantics == 'local' ? 'path:local-endpoint' : 'path:lan-to-wan';
	let path_id=msg?.pathId ?? expected_path, selected_path=primary_path(path_id), ctx=benchmark_context(path_id, benchmark_masked_keys(action)), id=sprintf('bench-%s-%d',substr(boot_id(),0,8),monotonic_ms());
	if (measurement == 'controlled_ab') {
		if (action == 'observe') return {ok:false,error:'controlled-ab-requires-action'};
		/* Goal must be measurable with the current methodology; otherwise the
		 * experiment fails-closed instead of degrading to throughput. */
		let cur_goal = goal(), goal_meas = goal_measurable(cur_goal);
		if (goal_meas == null) return {ok:false,error:'goal-unsupported-for-controlled-ab',goal:cur_goal,required:{methodology:goal_meas}};
		if (!selected_path) return {ok:false,error:'evaluation-path-not-found'};
		if ((semantics == 'local' && path_id != 'path:local-endpoint') || (semantics == 'forwarding' && path_id == 'path:local-endpoint')) return {ok:false,error:'measurement-path-semantics-mismatch',expectedSemantics:semantics};
		if (!bool_cfg('benchmark.one_variable',true)) return {ok:false,error:'one-variable-contract-disabled'};
		let comp=compatibility(action,null,path_id); if (!comp.allowed) return {ok:false,error:'compatibility-blocked',compatibility:comp};
		let plan=benchmark_provider_plan(action,path_id); if (!plan.ok) return {ok:false,error:plan.error,provider:plan};
		/* Blocker B: fastpath A/B attribution requires the live nft ruleset so
		 * the candidate delta can be verified against the EXACT expected
		 * flowtable/flow-rule toggle.  Without nft the experiment fails closed
		 * instead of expanding a mask. */
		if ((action == 'fastpath.software_flow_offload' || action == 'fastpath.hardware_flow_offload') && nft_snapshot() == null)
			return {ok:false,error:'provider-unavailable:nft-ruleset-required-for-fastpath-delta'};
		/* Forwarding A/B requires a REAL resolved route identity with explicit
		 * ip/rule evidence.  netifd-fallback identity is not evidence. */
		if (semantics == 'forwarding' && (!(selected_path.routeResolved === true) || selected_path.routeProvider != 'ip-full+rtnl-events'))
			return {ok:false,error:'evaluation-route-unresolved',required:{routeResolved:true,routeProvider:'ip-full+rtnl-events'},path:selected_path};
		/* Local benchmarks measure router-local kernel paths and therefore
		 * define their own route requirement: the local endpoint path must
		 * exist; no external WAN route evidence is required. */
		let lock_domain=benchmark_lock_domain(action, plan, path_id);
		let execution_source=msg?.executionSource ?? 'manual', frozen_decision=null;
		if (execution_source == 'benchmark-rill') {
			frozen_decision=rill_binding_reserve(msg?.decisionId,action,'benchmark','benchmark',id);
			if (!frozen_decision) return {ok:false,error:'rill-decision-already-reserved'};
		} else if (execution_source != 'manual' || msg?.decisionId != null) {
			return {ok:false,error:'invalid-execution-source'};
		}
		let lock=acquire_benchmark_lock(lock_domain, id);
		if (!lock.ok) {
			if (frozen_decision) rill_binding_release_reservation(frozen_decision,'benchmark-lock-conflict-before-mutation');
			return {ok:false,error:'benchmark-domain-lock-conflict',conflict:lock.conflict,domain:lock_domain};
		}
		let session={schemaVersion:2,sessionId:id,state:'awaiting_control',userInitiated:true,actionId:action,executionSource:execution_source,rillDecision:frozen_decision,applyTarget:plan.targetRef?.stableId ?? null,evaluationPath:path_id,workloadClass:ctx.workloadClass,capabilityHash:ctx.capabilityHash,topologyGeneration:ctx.topologyGeneration,routeIdentity:ctx.routeIdentity,integrationState:ctx.integrationState,integrationFingerprint:ctx.integrationFingerprint,nftSnapshot:ctx.nftSnapshot,deviceProfile:cfg('main.profile','recommended'),goal:cur_goal,benchmarkLock:{domain:lock_domain,sessionId:id},createdMonotonicMs:monotonic_ms(),measurementClass:'controlled_ab',variableCount:1,transactionId:null,controlEvidence:null,candidateEvidence:null,result:null,companion:{contract:'pm-companion/v2',requiredRole:semantics=='local'?'router-local-client':'lan-client',phases:['control','candidate'],methodology:null,metadata:{sessionId:id,actionId:action,pathId:path_id,topologyGeneration:ctx.topologyGeneration,routeIdentity:ctx.routeIdentity,capabilityHash:ctx.capabilityHash,goal:cur_goal}}};
		ensure_dir(`${state_dir()}/benchmarks`);
		if (!json_write(benchmark_path(id),session)) {
			release_benchmark_lock(lock_domain,id);
			if (frozen_decision) rill_binding_release_reservation(frozen_decision,'benchmark-session-write-failed-before-mutation');
			return {ok:false,error:'benchmark-session-write-failed'};
		}
		history('benchmark.started',session);
		return {ok:true,stage:'control',session:session,companion:session.companion};
	}
	let snap=telemetry_snapshot();
	let session={schemaVersion:2,sessionId:id,state:'completed',userInitiated:true,actionId:action,executionSource:'manual',rillDecision:null,applyTarget:msg?.target ?? null,evaluationPath:path_id,workloadClass:ctx.workloadClass,capabilityHash:ctx.capabilityHash,topologyGeneration:ctx.topologyGeneration,routeIdentity:ctx.routeIdentity,integrationState:ctx.integrationState,integrationFingerprint:ctx.integrationFingerprint,nftSnapshot:ctx.nftSnapshot,deviceProfile:cfg('main.profile','recommended'),measurementClass:measurement,variableCount:0,before:snap,after:snap,result:{validated:false,changedSystemState:false,note:measurement=='health_only'?'Health snapshot captured; this is not a performance validation.':'Passive observation captured; no A/B intervention occurred.'}};
	ensure_dir(`${state_dir()}/benchmarks`);
	if (!json_write(benchmark_path(id),session)) return {ok:false,error:'benchmark-session-write-failed'};
	history('benchmark.observed',session); return {ok:true,session:session};
}

function rill_observe() {
	/* Observe is a decision-registration call on the adapter's ledger.  It is
	 * throttled so PM stays inside the adapter's pending-decision capacity
	 * (each observe registers one pending decision that only an outcome or the
	 * 1h TTL resolves). */
	let now = monotonic_ms();
	if (rill_last_observe_ms && (now - rill_last_observe_ms) < RILL_OBSERVE_MIN_INTERVAL_MS)
		return { ok: false, state: 'throttled', retryAfterMs: RILL_OBSERVE_MIN_INTERVAL_MS };
	let caps = capabilities();
	let topo = topology();
	let path = topo.paths[0];
	let integ_fp = integration_fingerprint([], nft_snapshot());
	let g = goal();
	let available_actions = rill_available_actions();
	if (!length(available_actions)) return { ok: false, state: 'no-available-actions' };
	let payload = {
		contract: RILL_CONTRACT, protocolVersion: RILL_PROTOCOL_VERSION, requestId: sprintf('obs-%d', now), op: 'observe', deviceProfile: cfg('main.profile','recommended'),
		capabilityHash: capability_hash(caps), topologyGeneration: topology_generation,
		pathId: path?.id ?? 'path:lan-to-wan', routeIdentity: path?.routeIdentity ?? 'unresolved', workloadClass: path?.workloadClass ?? ['plain_forwarding'],
		measurementClass: 'passive_before_after', context: telemetry_snapshot(), integrations: rill_integrations_payload(), goal: g,
		integrationFingerprint: integ_fp,
		contextKey: rill_context_key_build(cfg('main.profile','recommended'), capability_hash(caps), topology_generation,
			path?.id ?? 'path:lan-to-wan', path?.routeIdentity ?? 'unresolved', path?.workloadClass ?? ['plain_forwarding'], integ_fp, g),
		availableActions: available_actions
	};
	rill_last_observe_ms = now;
	rill_runtime_counters.rillObserveAttempts++;
	let r = rill_send(payload);
	if (!r.ok) return r;
	let resp = r.response ?? {};
	let valid = rill_validate_observe_response(payload, resp);
	if (!valid.ok)
		return { ok: false, state: 'invalid-observe-response', reason: valid.error, requestId: payload.requestId, response: r.response };
	let binding = rill_binding_register(payload, resp);
	let advisory = binding ? rill_advisory_update(resp, payload) : null;
	if (!binding || !advisory) return { ok: false, state: 'binding-registration-failed', requestId: payload.requestId };
	rill_runtime_counters.rillObserveAccepted++;
	return { ok: true, decisionId: resp.decisionId, recommendation: resp.recommendation, binding: binding, response: r.response };
}

function recommendations(allow_observe) {
	/* Only the explicit recommendations/rill_refresh surfaces may register a
	 * decision. Diagnostics and periodic telemetry are read-only consumers of
	 * the current cache and must never create an Observe/persistence storm.
	 * Defined after rill_observe() because raw ucode does not hoist callees. */
	allow_observe = allow_observe !== false;
	let acts = candidate_actions();
	let packet = packet_steering_capability();
	let notes = [];
	if (packet.availability == 'available')
		push(notes, { id: 'network.packet_steering.native', disposition: 'respect', detail: 'Native OpenWrt provider detected; no ownership seizure.' });
	let port = port_capacity_capability();
	let po = port.evidence[0]?.observed;
	if ((po?.conntrackPressure ?? 0) >= 0.70 || integration_state().transparentProxy)
		push(notes, { id: 'network.local_port_capacity', disposition: 'analyze', detail: 'Local port capacity is relevant under proxy/high-connection pressure; reserved ports and ownership must be preserved. Any change remains benchmark-only.' });
	let rill = rill_status();
	let rill_advisory_live = rill_advisory_get();
	let rill_observation = null;
	if (allow_observe && !rill_advisory_live && (rill.state == RILL_STATES.available || rill.state == RILL_STATES.learning)) {
		rill_observation = rill_observe();
		rill_advisory_live = rill_advisory_get();
	}
	return {
		topologyGeneration: topology_generation, actions: acts, observations: notes,
		benchmarkActions: benchmark_catalog(),
		rill: rill,
		rillObservation: rill_observation,
		learnedAdvisory: rill_advisory_live ? [rill_advisory_live] : [],
	};
}

function package_installed(name) {
	if (!match(name ?? '', /^[A-Za-z0-9_.+-]+$/)) return false;
	if (command_exists('apk')) {
		let r=run([ 'apk', 'list', '-I', name ]);
		if (r.rc == 0) for (let line in split(r.out,'\n')) if (substr(trimstr(line),0,length(name)+1) == `${name}-`) return true;
	}
	if (command_exists('opkg')) return run([ 'opkg', 'status', name ]).rc == 0;
	/* Package-manager metadata may be unavailable in stripped recovery images.
	 * Do not falsely report a package as installed. */
	return false;
}

function profile_status() {
	let id=cfg('main.profile','recommended'), merged=merge_profile(id,{});
	if (!merged.ok) return {id:id,healthy:false,errors:[merged.error]};
	let p=merged.profile, caps=capabilities(), cmap={}, missing_required=[], missing_recommended=[], missing_conditional=[], missing_commands=[], missing_caps=[];
	for (let c in caps.capabilities ?? []) cmap[c.id]=c;
	for (let x in p.requiredPackages ?? []) if (!package_installed(x)) push(missing_required,x);
	for (let x in p.recommendedPackages ?? []) if (!package_installed(x)) push(missing_recommended,x);
	for (let x in p.expectedCommands ?? []) if (!command_exists(x)) push(missing_commands,x);
	for (let x in p.expectedCapabilities ?? []) if ((cmap[x]?.availability ?? 'unavailable') != 'available') push(missing_caps,x);
	for (let item in p.conditionalPackages ?? []) if ((cmap[item.whenCapability]?.availability ?? 'unavailable') == 'available' && !package_installed(item.name)) push(missing_conditional,item.name);
	let arch=trimstr(run(['uname','-m']).out), target_ok=index(p.targets ?? ['*'],'*') >= 0 || index(p.targets ?? [],arch) >= 0;
	let healthy=target_ok && !length(missing_required) && !length(missing_commands) && !length(missing_caps) && !length(missing_conditional);
	return {id:id,chain:p.chain,healthy:healthy,degraded:healthy && length(missing_recommended)>0,targetMatched:target_ok,architecture:arch,missingRequiredPackages:missing_required,missingRecommendedPackages:missing_recommended,missingConditionalPackages:missing_conditional,missingCommands:missing_commands,missingCapabilities:missing_caps,requiredPackages:p.requiredPackages,recommendedPackages:p.recommendedPackages,conditionalPackages:p.conditionalPackages,expectedCommands:p.expectedCommands,expectedCapabilities:p.expectedCapabilities,targets:p.targets};
}

function clock_hhmm() {
	let r = run([ 'date', '+%H%M' ]);
	if (r.rc != 0) return null;
	let v = +trimstr(r.out);
	return v >= 0 && v <= 2359 ? v : null;
}

function cfg_hhmm(key, fallback) {
	let raw = replace(cfg(key, fallback), /:/g, '');
	let v = +raw;
	return v >= 0 && v <= 2359 ? v : +replace(fallback, /:/g, '');
}

function in_maintenance_window() {
	let now = clock_hhmm();
	if (now == null) return false;
	let start = cfg_hhmm('main.maintenance_start', '03:00');
	let end = cfg_hhmm('main.maintenance_end', '05:00');
	if (start == end) return false;
	return start < end ? (now >= start && now < end) : (now >= start || now < end);
}

function assisted_low_traffic(current, runtime) {
	if (!runtime) return { pass: false, reason: 'path-target-unresolved' };
	/* Baseline is kept per runtime so a target-specific gate never borrows an
	 * interval measured on a different interface's counters. */
	let file = `${state_dir()}/telemetry/assisted-previous-${safe_name(runtime)}.json`;
	let prev = json_read(file, null);
	json_write(file, current);
	if (!prev || prev.bootId != current.bootId || prev.topologyGeneration != current.topologyGeneration)
		return { pass: false, reason: 'baseline-not-ready' };
	let dt = ((current.monotonicMs ?? 0) - (prev.monotonicMs ?? 0)) / 1000;
	if (dt <= 0) return { pass: false, reason: 'invalid-interval' };
	let a = prev.interfaces?.[runtime], b = current.interfaces?.[runtime];
	if (!a || !b) return { pass: false, reason: 'interface-counters-unavailable', runtimeName: runtime };
	let delta = max(0, (b.rxBytes ?? 0) - (a.rxBytes ?? 0)) + max(0, (b.txBytes ?? 0) - (a.txBytes ?? 0));
	let rate = delta / dt;
	let threshold = max(65536, int_cfg('main.assisted_max_bytes_per_second', 1048576));
	return { pass: rate <= threshold, bytesPerSecond: rate, threshold: threshold, runtimeName: runtime };
}

function assisted_auto_tick(current) {
	if (cfg('main.automation', 'conservative') != 'assisted' || !bool_cfg('main.assisted_auto', false))
		return { enabled: false, state: 'disabled' };
	if (!in_maintenance_window())
		return { enabled: true, state: 'outside-maintenance-window' };
	let guard = system_guard();
	if (!guard.pass) return { enabled: true, state: 'health-guard', guard: guard };
	let actions = candidate_actions();
	if (!length(actions)) return { enabled: true, state: 'no-safe-candidate' };
	/* Assisted Auto intentionally admits only the same v0.1 safe allowlist.
	 * Benchmark-class actions remain user-initiated and endpoint-gated. */
	let action = actions[0];
	if (index(SAFE_ACTIONS, action.id) < 0 || action.risk != 'safe')
		return { enabled: true, state: 'candidate-not-safe' };
	/* Select the Action first, then gate on the traffic of THAT action's own
	 * target/path.  Gating on the primary WAN while modifying another path's
	 * ring would let a high-traffic experiment run under a quiet primary. */
	let target_ref = resolve_target(action.applyTarget);
	let traffic = assisted_low_traffic(current, target_ref?.runtimeName ?? null);
	if (!traffic.pass) {
		runtime_history('assisted.skip', { reason: 'traffic-gate', traffic: traffic });
		return { enabled: true, state: 'traffic-gate', traffic: traffic };
	}
	let result = apply_ring(action);
	history('assisted.action', { actionId: action.id, target: action.applyTarget, ok: result.ok, traffic: traffic });
	return { enabled: true, state: result.ok ? 'applied' : 'failed', actionId: action.id, result: result };
}

function benchmark_active() {
	/* True while a controlled A/B experiment holds the global tuning domain on
	 * this boot.  Conservative must never auto-apply concurrently with it. */
	let lock = json_read(benchmark_lock_path('benchmark:global'), null);
	if (!lock || lock.bootId != boot_id()) return false;
	let session = json_read(benchmark_path(lock.sessionId), null);
	return benchmark_session_active(session);
}

function conservative_auto_tick() {
	/* Conservative is the DEFAULT automation mode (planning v0.3.2 Phase 6 /
	 * MANIFEST defaultProfile.automation=conservative): it is a real safe
	 * optimizer that auto-applies ONLY the v0.1 safe allowlist through the full
	 * transactional safety chain (capability -> compatibility -> ownership ->
	 * health guard -> locks -> snapshot -> transaction -> apply -> readback ->
	 * health verification -> commit -> rollback) inside apply_ring().  It never
	 * auto-applies benchmark/unsafe/unknown actions, and it never seizes
	 * preexisting values. */
	if (cfg('main.automation', 'conservative') != 'conservative')
		return { enabled: false, state: 'disabled' };
	if (!bool_cfg('main.conservative_auto', true))
		return { enabled: true, state: 'opt-out' };
	let guard = system_guard();
	if (!guard.pass) return { enabled: true, state: 'health-guard', guard: guard };
	/* Never race an active benchmark experiment (holds the global tuning
	 * domain). */
	if (benchmark_active()) return { enabled: true, state: 'benchmark-active' };
	/* Backoff: a transient apply failure is rolled back by apply_ring, so the
	 * candidate would otherwise reappear every telemetry tick; require a quiet
	 * gap before retrying to avoid a hot loop. */
	let attempt = json_read(`${state_dir()}/conservative-last-attempt.json`, null);
	if (attempt && attempt.bootId == boot_id() && (monotonic_ms() - (attempt.monotonicMs ?? 0)) < max(120000, int_cfg('main.conservative_retry_ms', 300000)))
		return { enabled: true, state: 'backoff' };
	let actions = candidate_actions();
	if (!length(actions)) return { enabled: true, state: 'no-safe-candidate' };
	let action = actions[0];
	if (index(SAFE_ACTIONS, action.id) < 0 || action.risk != 'safe')
		return { enabled: true, state: 'candidate-not-safe' };
	json_write(`${state_dir()}/conservative-last-attempt.json`, { bootId: boot_id(), monotonicMs: monotonic_ms(), actionId: action.id });
	let result = apply_ring(action);
	history('conservative.action', { actionId: action.id, target: action.applyTarget, ok: result.ok, state: result.ok ? 'applied' : 'failed', result: result });
	return { enabled: true, state: result.ok ? 'applied' : 'failed', actionId: action.id, result: result };
}

function analysis_report(allow_observe) {
	let caps=capabilities(), topo=topology(), guard=system_guard(), profile=profile_status(), findings=[], evidence=[];
	let unresolved=[];
	for (let p in topo.paths ?? []) {
		if (p.id == 'path:local-endpoint') continue;
		push(evidence,{kind:'path',id:p.id,routeIdentity:p.routeIdentity,routeProvider:p.routeProvider,resolved:p.routeResolved,targetRefs:p.targetRefs ?? []});
		if (!(p.routeResolved ?? false)) push(unresolved,p.id);
	}
	if (length(unresolved)) push(findings,{id:'topology.route-unresolved',severity:'block',confidence:'high',evidence:{paths:unresolved},recommendation:'Resolve the WAN-specific route identity before active forwarding benchmarks.'});
	if (!guard.pass) push(findings,{id:'system.health-guard',severity:'block',confidence:'high',evidence:{reasons:guard.reasons,health:guard.health},recommendation:'Do not auto-tune or benchmark until the health guard is clear.'});
	if (!profile.healthy) push(findings,{id:'profile.contract-degraded',severity:'degraded',confidence:'high',evidence:{missingRequiredPackages:profile.missingRequiredPackages,missingCommands:profile.missingCommands,missingCapabilities:profile.missingCapabilities,missingConditionalPackages:profile.missingConditionalPackages,targetMatched:profile.targetMatched},recommendation:'Satisfy the selected profile contract or deliberately select a smaller profile.'});
	let packet=null, port=null;
	for (let c in caps.capabilities ?? []) {
		if (c.id=='network.packet_steering.native') packet=c;
		if (c.id=='network.local_port_capacity') port=c;
	}
	if (packet?.availability=='available') push(findings,{id:'network.packet-steering-native',severity:'info',confidence:packet.confidence ?? 'high',evidence:packet.evidence,recommendation:'Respect the OpenWrt native provider; do not seize RPS ownership.'});
	let pressure=port?.evidence?.[0]?.observed?.conntrackPressure;
	if (pressure != null && pressure >= 0.70) push(findings,{id:'network.local-port-capacity',severity:'observe',confidence:port.confidence ?? 'high',evidence:port.evidence,recommendation:'Capacity pressure is relevant; preserve reserved ports and use benchmark-only changes.'});
	for (let a in candidate_actions()) push(findings,{id:`candidate.${a.id}`,severity:'recommend',confidence:'high',evidence:{applyTarget:a.applyTarget,affectedPaths:a.affectedPaths,params:a.params,risk:a.risk},recommendation:'Conservative candidate is supported by direct provider readback and remains transactional.'});
	let confidence = !length(unresolved) && guard.pass ? 'high' : (length(topo.paths ?? []) ? 'medium' : 'low');
	return {schemaVersion:2,topologyGeneration:topology_generation,confidence:confidence,evidence:evidence,findings:findings,guard:guard,profile:profile,integrations:integration_state(),platform:platform_info(),recommendations:recommendations(allow_observe)};
}

function conservative_disposition() {
	/* Conservative is a real safety optimizer, not a UI string.  It encodes
	 * exactly what the Core will and will not do automatically, so reviewers
	 * (and the behavioral tests) can assert the semantics rather than a label. */
	let automation = cfg('main.automation', 'conservative');
	let safe = candidate_actions();
	return {
		schemaVersion: 2,
		automation: automation,
		/* Conservative/Shadow: only the safe allowlist can ever auto-apply, and
		 * only through the full transactional path (ownership + precheck +
		 * backup + bounded apply + verification + rollback).  `conservative` is
		 * the default mode and drives conservative_auto_tick(); `manual` never
		 * auto-applies; `assisted` is double opt-in + additionally gated. */
		autoAppliesSafeAllowlistOnly: automation == 'conservative' && bool_cfg('main.conservative_auto', true),
		/* Assisted Auto is double opt-in and additionally gated by maintenance
		 * window, health guard and target-specific low traffic. */
		assistedAutoEnabled: automation == 'assisted' && bool_cfg('main.assisted_auto', false),
		neverAutoApplies: [ 'benchmark', 'unsafe' ],
		seizesPreexisting: false,
		packetSteeringPolicy: 'observe-respect',
		/* Every write is transactional; nothing is directly applied outside the
		 * Core.  Rill is advisory only and cannot write state. */
		writesAreTransactional: true,
		benchmarkActionsAreUserInitiated: true,
		concrete: safe,
		explicitGuarantees: [
			'safe-allowlist-only', 'never-seize-preexisting', 'observe-respect-packet-steering',
			'ownership-precheck-backup-verify-rollback', 'benchmark-user-initiated-only',
			'no-apply-outside-core', 'rill-advisory-only'
		]
	};
}

function status() {
	let guard = system_guard();
	let profile = profile_status();
	return {
		version: VERSION, running: true, automation: cfg('main.automation', 'conservative'), goal: cfg('main.goal', 'balanced'),
		telemetry: bool_cfg('main.telemetry', true), history: bool_cfg('main.history', true), failsafe: bool_cfg('main.failsafe', true),
		topologyGeneration: topology_generation, bootId: boot_id(),
		profile: profile, healthGuard: guard, rill: rill_status(), nativePacketSteering: packet_steering_capability(), platform: platform_info(),
		automationDisposition: conservative_disposition(),
		assistedAuto: { enabled: cfg('main.automation','conservative') == 'assisted' && bool_cfg('main.assisted_auto', false), maintenanceWindow: [ cfg('main.maintenance_start','03:00'), cfg('main.maintenance_end','05:00') ] }
	};
}

function resource_usage() {
	let vmrss=null, vmsize=null, pid=null;
	for (let line in split(read('/proc/self/status') ?? '', '\n')) {
		let m=match(line,/^VmRSS:\s+([0-9]+)\s+kB/); if (m) vmrss=+m[1];
		m=match(line,/^VmSize:\s+([0-9]+)\s+kB/); if (m) vmsize=+m[1];
		m=match(line,/^Pid:\s+([0-9]+)/); if (m) pid=+m[1];
	}
	let rill_dir=cfg('shadow.state_dir',`${persist_dir()}/rill`);
	let hs=fs.stat(`${persist_dir()}/history.jsonl`), outcomes=fs.stat(`${rill_dir}/validated-outcomes.tsv`), ledger=fs.stat(`${rill_dir}/decision-ledger.jsonl`);
	let counters = {};
	for (let key in keys(rill_runtime_counters)) counters[key] = rill_runtime_counters[key];
	let prepared=0, pending=0, sent_unknown=0;
	for (let path in fs.glob(`${persist_dir()}/rill-executions/*.json`) ?? []) {
		let row=json_read(path,null);
		if (row?.executionState == 'outcome-prepared') prepared++;
		if (row?.executionState == 'outcome-pending') pending++;
		if (row?.executionState == 'sent-unknown') sent_unknown++;
	}
	counters.rillDecisionAvailable = length(keys(rill_bindings));
	counters.rillOutcomePrepared = prepared;
	counters.rillOutcomePending = pending;
	counters.rillOutcomeSentUnknown = sent_unknown;
	counters.pmPersistentWrites = persistent_write_count;
	counters.expectedAdapterPersistenceEvents = rill_runtime_counters.rillObserveAccepted + rill_runtime_counters.rillOutcomeAccepted + rill_runtime_counters.rillOutcomeReconciled;
	counters.persistenceAccounting = 'logical/inferred-from-pinned-rill-v1.2.0-contract';
	return {corePid:pid,coreVmRssKiB:vmrss,coreVmSizeKiB:vmsize,corePersistentWritesSinceStart:persistent_write_count,corePersistentWriteBytesSinceStart:persistent_write_bytes,persistentHistoryBytes:hs?.size ?? 0,rillOutcomeBytes:outcomes?.size ?? 0,rillLedgerBytes:ledger?.size ?? 0,historyLineLimit:MAX_HISTORY_LINES,rillCounters:counters,rillBounds:{adapterStateFileBytes:4194304,bindingCacheEntries:RILL_BINDINGS_MAX}};
}

function diagnostics() {
	return {
		status: status(), capabilities: capabilities(), topology: topology(), targets: target_refs(), paths: topology().paths,
		integrations: integration_state(), recommendations: recommendations(false), transactions: transaction_list(), locks: lock_list(),
		benchmarks: benchmark_list(), history: read_lines(`${persist_dir()}/history.jsonl`, 100), telemetry: telemetry_snapshot(), resources: resource_usage(), profile: profile_status(), analysis: analysis_report(false)
	};
}

function topology_signature(t) {
	let rows=[];
	for (let i in t.interfaces ?? []) push(rows,sprintf('if:%s|%s|%s|%s|%s',i.name ?? '',i.l3Device ?? '',i.up ?? '',i.proto ?? '',i.device ?? ''));
	for (let d in t.devices ?? []) push(rows,sprintf('dev:%s|%s|%s|%s',d.name ?? '',d.targetRef ?? '',d.driver ?? '',d.operstate ?? ''));
	for (let p in t.paths ?? []) push(rows,sprintf('path:%s|%s|%s|%s|%s',p.id ?? '',p.wanInterface ?? '',p.routeIdentity ?? '',join(',',p.targetRefs ?? []),join(',',p.workloadClass ?? [])));
	return stable_list_hash('topology-v2',rows);
}

function refresh(reason) {
	let observed=topology(), signature=topology_signature(observed), changed=false;
	if (last_topology_signature == null) last_topology_signature=signature;
	else if (signature != last_topology_signature) { topology_generation++; last_topology_signature=signature; changed=true; }
	let replay_reason=reason == 'boot' ? 'boot' : (match(reason ?? '', /device|interface|rtnl/) ? 'device_up' : 'topology_change');
	let replay=changed || reason == 'boot' ? replay_policies(replay_reason) : [];
	if (changed) rill_invalidate_runtime_decisions(reason ?? 'topology-change');
	runtime_history('topology.refresh',{reason:reason ?? 'manual',changed:changed,topologySignature:signature,topologyGeneration:topology_generation,replay:replay});
	return {ok:true,changed:changed,topologyGeneration:topology_generation,replay:replay,rillAdvisoryInvalidated:changed};
}

function rill_refresh_advisory() {
	rill_invalidate_runtime_decisions('explicit-refresh');
	rill_last_observe_ms = null;
	return rill_observe();
}

function schedule_event(reason) {
	if (event_timer) event_timer.cancel();
	event_timer = uloop.timer(750, function() {
		refresh(reason);
		event_timer = null;
	});
}

function schedule_telemetry() {
	if (!bool_cfg('main.telemetry', true)) return;
	let interval = max(30, int_cfg('main.telemetry_interval', 45)) * 1000;
	telemetry_timer = uloop.timer(interval, function() {
		let snap = telemetry_snapshot();
		json_write(`${state_dir()}/telemetry/latest.json`, snap);
		assisted_auto_tick(snap);
		conservative_auto_tick();
		this.set(interval);
	});
	let deep_interval = max(300, int_cfg('main.deep_interval', 600)) * 1000;
	deep_timer = uloop.timer(deep_interval, function() {
		json_write(`${state_dir()}/diagnostics/latest.json`, { capabilities: capabilities(), topology: topology(), integrations: integration_state(), guard: system_guard() });
		this.set(deep_interval);
	});
}

function rill_pending_outcome_count() {
	let count=0;
	for (let path in fs.glob(`${persist_dir()}/rill-executions/*.json`) ?? []) {
		let row=json_read(path,null);
		if (row?.executionState == 'outcome-prepared' || row?.executionState == 'outcome-pending' || row?.executionState == 'sent-unknown') count++;
	}
	return count;
}

function schedule_rill_outcome_retry() {
	if (rill_outcome_timer || rill_pending_outcome_count() == 0) return;
	rill_outcome_timer = uloop.timer(5000, function() {
		rill_outcome_timer = null;
		if (bool_cfg('shadow.enabled', true)) { if (rill_recover_execution_hook) rill_recover_execution_hook(); rill_retry_pending_outcomes(); }
		if (rill_pending_outcome_count() > 0) schedule_rill_outcome_retry();
	});
}

function recover_rill_executions() {
	let recovered=0, retired=0;
	for (let path in fs.glob(`${persist_dir()}/rill-executions/*.json`) ?? []) {
		let row=json_read(path,null);
		if (!row) { fs.unlink(path); continue; }
		if (row.executionState == 'outcome-prepared') {
			let armed=rill_arm_outcome(row.binding ?? row.frozenDecision);
			if (armed.ok) { recovered++; continue; }
			if (armed.state == 'outcome-owner-terminal-not-durable' && row.createdBootId != boot_id()) {
				row.executionState='retired-abandoned'; row.retiredReason='prepared-outcome-owner-not-terminal-after-recovery';
				json_write(path,row); retired++;
			}
			continue;
		}
		if (row.executionState == 'outcome-pending' || row.executionState == 'sent-unknown') {
			row.nextRetryMonotonicMs=monotonic_ms();
			row.recoveredBootId=boot_id(); row.recoveredMonotonicMs=monotonic_ms();
			if (row.outcomePreparedBootId == boot_id()) rill_runtime_counters.rillOutcomeRecoveredAfterCoreRestart++;
			else rill_runtime_counters.rillOutcomeRecoveredAfterBoot++;
			json_write(path,row); recovered++; continue;
		}
		if ((row.executionState == 'reserved' || row.executionState == 'executing') && row.createdBootId != boot_id()) {
			row.executionState='retired-abandoned'; row.retiredReason='boot-recovery-no-auto-actuation';
			json_write(path,row); retired++;
		}
	}
	if (recovered) schedule_rill_outcome_retry();
	return {recovered:recovered,retired:retired};
}

rill_outcome_schedule_hook = schedule_rill_outcome_retry;
rill_recover_execution_hook = recover_rill_executions;

function reply(req, data) { req.reply(data); }

ensure_dir(state_dir());
ensure_dir(persist_dir());
ensure_dir(`${state_dir()}/transactions`);
ensure_dir(`${state_dir()}/locks`);
ensure_dir(`${state_dir()}/benchmarks`);
ensure_dir(`${state_dir()}/telemetry`);
ensure_dir(`${state_dir()}/diagnostics`);
ensure_dir(`${persist_dir()}/rill-executions`);
uloop.init();
recover_pending();
recover_rill_executions();
let obj = conn.publish(UBUS_NAME, {
	status: { call: function(req, msg) { reply(req, status()); } },
	capabilities: { call: function(req, msg) { reply(req, capabilities()); } },
	topology: { call: function(req, msg) { reply(req, topology()); } },
	targets: { call: function(req, msg) { reply(req, { topologyGeneration: topology_generation, targets: target_refs() }); } },
	paths: { call: function(req, msg) { reply(req, { topologyGeneration: topology_generation, paths: topology().paths }); } },
	analyze: { call: function(req, msg) { reply(req, analysis_report()); } },
	recommendations: { call: function(req, msg) { reply(req, recommendations()); } },
	transactions: { call: function(req, msg) { reply(req, { transactions: transaction_list() }); } },
	locks: { call: function(req, msg) { reply(req, { locks: lock_list() }); } },
	/* Current ucode exposes validated method payloads as req.args (the handler
	 * receives one request resource), not as a second callback argument. */
	history: { args: { limit: 0 }, call: function(req) { let msg=req.args ?? {}, limit = min(MAX_HISTORY_LINES, max(1, +(msg?.limit ?? 100))); reply(req, { history: read_lines(`${persist_dir()}/history.jsonl`, limit), runtimeHistory: read_lines(`${state_dir()}/history.jsonl`, limit) }); } },
	apply: { args: { actionId: 'string', target: 'string', executionSource: 'string', decisionId: 'string' }, call: function(req) { reply(req, apply_action(req.args ?? {})); } },
	confirm: { args: { transactionId: 'string' }, call: function(req) { reply(req, confirm_transaction(req.args?.transactionId)); } },
	rollback: { args: { transactionId: 'string' }, call: function(req) { reply(req, rollback_transaction(req.args?.transactionId, 'manual')); } },
	benchmark_start: { args: { phase: 'string', actionId: 'string', pathId: 'string', measurementClass: 'string', executionSource: 'string', decisionId: 'string', sessionId: 'string', evidence: {}, target: 'string' }, call: function(req) { reply(req, benchmark_start(req.args ?? {})); } },
	benchmark_status: { call: function(req) {
		let msg=req.args ?? {};
		if (msg?.sessionId) {
			let s = json_read(benchmark_path(msg.sessionId), null);
			reply(req, s ? { found: true, session: s } : { found: false });
		} else reply(req, { found: length(benchmark_list()) > 0, sessions: benchmark_list() });
	}, args: { sessionId: 'string' } },
	benchmark_stop: { args: { sessionId: 'string' }, call: function(req) { reply(req, benchmark_stop(req.args?.sessionId)); } },
	rill_status: { call: function(req, msg) { reply(req, rill_status()); } },
	rill_refresh: { call: function(req, msg) { reply(req, rill_refresh_advisory()); } },
	diagnostics: { call: function(req, msg) { reply(req, diagnostics()); } },
	cleanup: { args: { reason: 'string' }, call: function(req) { reply(req, cleanup_owned(req.args?.reason ?? 'package-remove')); } },
	refresh: { args: { reason: 'string' }, call: function(req) { reply(req, refresh(req.args?.reason ?? 'manual')); } }
});

if (!obj) {
	warn(`performance-manager: failed to publish ubus object: ${ubusmod.error()}\n`);
	exit(1);
}

for (let pattern in [ 'interface.*', 'network.*', 'firewall.*' ]) {
	let l = conn.listener(pattern, function(ev, data) { schedule_event(ev ?? pattern); });
	if (l) push(listeners, l);
}

/* netifd broadcasts cover logical interfaces; rtnetlink closes the device and
 * route-change gap required by the frozen topology/event contract. Use numeric
 * RTM command IDs and RTNLGRP multicast groups: these are stable kernel ABI
 * values, and the module exposes its constants inconsistently (rtnl.const.*
 * vs. top-level exports) across ucode-mod-rtnl builds. */
let route_listener = rtnl.listener(function(msg) { schedule_event('rtnl-route-or-link'); }, [ 16, 17, 24, 25 ], [ 1, 7, 11 ]);
if (route_listener) push(listeners, route_listener);

schedule_telemetry();
uloop.timer(1500, function() { refresh('boot'); });
uloop.run();
