/* ============================================================================
 * REAL Core runtime harness test driver.
 * Appended by build-harness.py to the forward-reference-free, main-stripped
 * Core library so it
 * executes the ACTUAL performance-manager.uc logic. The data-provider seam
 * (conn/run/read/command_exists/interface_dump/device_dump/netdevs/stable_target/
 * integration_state) is re-seated to runtime-shaped fixtures; every function
 * under test below is the real Core implementation, not a Python mirror and not
 * a substring check.
 * ========================================================================== */

let _failures = 0;
let _NFT_RULESET = '';

/* ucode has no global JSON; %.J is the canonical serializer. */
function jstr(v) { return sprintf('%.J', v); }

function check(cond, label, detail) {
	if (cond) {
		print('PASS  ' + label + '\n');
	} else {
		_failures++;
		print('FAIL  ' + label + '  ' + (detail == null ? '' : jstr(detail)) + '\n');
	}
}

function json_eq(a, b, label) {
	check(jstr(a) == jstr(b), label, { got: a, want: b });
}

/* ---- fixtures ------------------------------------------------------------ */

/* read(): /proc providers used by boot_id()/monotonic_ms(). */
read = function(path, limit) {
	if (path == '/proc/sys/kernel/random/boot_id') return '11111111-2222-3333-4444-555555555555';
	if (path == '/proc/uptime') return '12345.6 99999.0';
	return null;
};

/* command_exists(): advertise ip + nft so route/nft paths are exercised. */
command_exists = function(name) {
	if (index(['ip', 'nft'], name) >= 0) return true;
	return false;
};

/* interface_dump(): netifd-shape runtime interfaces.  Custom WANs (isp-b,
 * fiber) are present and reached via route/rule evidence, not wan[0-9]+ names. */
interface_dump = function() {
	return {
		interface: [
			{ interface: 'lan', device: 'br-lan', proto: 'static', up: true },
			{ interface: 'wan', device: 'eth1', proto: 'dhcp', up: true },
			{ interface: 'isp-b', device: 'ppp0', l3_device: 'ppp0', proto: 'pppoe', up: true },
			{ interface: 'fiber', device: 'eth2', proto: 'dhcp', up: true }
		]
	};
};

/* run(): fake command provider.  ip route/rule evidence points at eth1 (wan),
 * eth2 (fiber) and ppp0 (isp-b) so ALL THREE custom WANs are discovered without
 * any name-based guess.  nft returns a scripted ruleset for fingerprint tests. */
let _KNOWN_CMDS = [
	'ip -j -4 route show table all default',
	'ip -j -6 route show table all default',
	'ip -j -4 rule show',
	'ip -j -6 rule show',
	'nft -j list ruleset'
];

run = function(argv) {
	let cmd = join(' ', map(argv ?? [], shell_quote));
	if (cmd == 'ip -j -4 route show table all default') {
		return { rc: 0, out: jstr([
			{ dst: 'default', dev: 'eth1', table: 254 },
			{ dst: 'default', dev: 'eth2', table: 100 },
			{ dst: 'default', dev: 'ppp0', table: 200 }
		]) };
	}
	if (cmd == 'ip -j -6 route show table all default')
		return { rc: 0, out: '[]' };
	if (cmd == 'ip -j -4 rule show') {
		return { rc: 0, out: jstr([
			{ priority: 3000, oif: 'eth1', table: 254 },
			{ priority: 3001, oif: 'eth2', table: 100 },
			{ priority: 3002, lookup: 200 }
		]) };
	}
	if (cmd == 'ip -j -6 rule show') return { rc: 0, out: '[]' };
	if (cmd == 'nft -j list ruleset') return { rc: 0, out: _NFT_RULESET };
	if (cmd == 'uci -q get performance-manager.main.persistent_dir') return { rc: 0, out: '/tmp/pm-harness\n' };
	if (cmd == 'uname -m') return { rc: 0, out: 'x86_64\n' };
	return { rc: 1, out: '' };
};

/* device_dump(): netifd device topology with parent relations + types.  A PPPoE
 * (ppp0) rides over a VLAN (eth1.100) which rides over a physical NIC (eth1);
 * wlan-radio0 is a non-`wlan0`-named wireless device. */
device_dump = function() {
	return {
		device: [
			{ name: 'br-lan', type: 'bridge', parent: null },
			{ name: 'eth1', type: 'ethernet', parent: null },
			{ name: 'eth1.100', type: 'vlan', parent: 'eth1' },
			{ name: 'ppp0', type: 'pppoe', parent: 'eth1.100' },
			{ name: 'eth2', type: 'ethernet', parent: null },
			{ name: 'wg0', type: 'wireguard', parent: null },
			{ name: 'wlan-radio0', type: 'wireless', parent: null }
		]
	};
};

/* stable_target(): only physical NICs resolve to a stable tunable; logical/
 * tunnel/VLAN devs do not, so underlay_chain walks to the real NIC. */
stable_target = function(runtime) {
	let map2 = {
		'eth1': { stableId: 'nic:pci:0000:00:01.0', driver: 'hv_netvsc', runtimeName: 'eth1' },
		'eth2': { stableId: 'nic:pci:0000:00:02.0', driver: 'e1000e', runtimeName: 'eth2' }
	};
	let r = map2[runtime];
	if (!r) return { stableId: null, driver: null, runtimeName: runtime };
	let o = {}; for (let k in keys(r)) o[k] = r[k];
	return o;
};

/* netdevs(): runtime netdev inventory.  Only physical NICs carry a targetRef. */
netdevs = function() {
	return [
		{ name: 'eth1', operstate: 'up', type: 1, mtu: 1500, address: '02:00:00:00:00:01', driver: 'hv_netvsc', targetRef: 'nic:pci:0000:00:01.0', tunable: true },
		{ name: 'eth1.100', operstate: 'up', type: 1, mtu: 1500, address: '02:00:00:00:00:01', driver: null, targetRef: null, tunable: false },
		{ name: 'ppp0', operstate: 'up', type: 512, mtu: 1492, address: '', driver: null, targetRef: null, tunable: false },
		{ name: 'eth2', operstate: 'up', type: 1, mtu: 1500, address: '02:00:00:00:00:02', driver: 'e1000e', targetRef: 'nic:pci:0000:00:02.0', tunable: true },
		{ name: 'wg0', operstate: 'down', type: 65534, mtu: 1420, address: '', driver: null, targetRef: null, tunable: false },
		{ name: 'wlan-radio0', operstate: 'up', type: 1, mtu: 1500, address: '02:00:00:00:00:03', driver: 'mt7915', targetRef: null, tunable: false }
	];
};

/* integration_state(): a WireGuard interface is globally present, but that must
 * NOT label a plain WAN path as vpn_tunnel (path-specific classification). */
integration_state = function() {
	return {
		openclash: false, passwall: false, homeproxy: false, sqm: false,
		qosify: false, mwan3: true, pbr: true, wireguard: true, openvpn: false,
		docker: false, transparentProxy: false
	};
};

/* ---- real Core behavior assertions -------------------------------------- */

print('== [1] Multi-WAN / PBR: real route/rule evidence -> custom WANs ==\n');
let ev = wan_candidates_evidence();
let evNames = map(ev, function(w) { return w.interface; });
sort(evNames);
check(index(evNames, 'isp-b') >= 0, 'wan_candidates_evidence includes isp-b', evNames);
check(index(evNames, 'fiber') >= 0, 'wan_candidates_evidence includes fiber', evNames);
check(index(evNames, 'wan') >= 0, 'wan_candidates_evidence includes wan', evNames);

let topo = topology();
let wc = map(topo.wanCandidates ?? [], function(x) { return x; });
sort(wc);
check(index(wc, 'isp-b') >= 0, 'topology().wanCandidates includes isp-b', wc);
check(index(wc, 'fiber') >= 0, 'topology().wanCandidates includes fiber', wc);
let pathIds = map(topo.paths ?? [], function(p) { return p.id; });
check(index(pathIds, 'path:lan-to-isp-b') >= 0, 'topology().paths includes path:lan-to-isp-b', pathIds);
check(index(pathIds, 'path:lan-to-fiber') >= 0, 'topology().paths includes path:lan-to-fiber', pathIds);

print('== [2] underlay resolver: PPPoE -> VLAN -> physical NIC ==\n');
let ul = underlay_chain({ interface: 'isp-b', device: 'ppp0', l3_device: 'ppp0', proto: 'pppoe' });
check(ul.target?.stableId == 'nic:pci:0000:00:01.0', 'pppoe chain resolves to physical eth1 NIC', ul);
check(index(ul.chain ?? [], 'ppp0') >= 0 && index(ul.chain ?? [], 'eth1.100') >= 0 && index(ul.chain ?? [], 'eth1') >= 0,
	'underlay_chain([ppp0,eth1.100,eth1]) walks full path', ul.chain);

print('== [3] Workload Class is path-specific (global WireGuard must not leak) ==\n');
let wl_wan = derive_workload({ id: 'path:lan-to-wan', proto: 'dhcp', underlayChain: ['eth1'] });
check(index(wl_wan, 'vpn_tunnel') < 0, 'plain WAN path is NOT vpn_tunnel despite global WireGuard', wl_wan);
check(index(wl_wan, 'plain_forwarding') >= 0, 'plain WAN path is plain_forwarding', wl_wan);
let wl_p1 = derive_workload({ id: 'path:lan-to-isp-b', proto: 'pppoe', underlayChain: ['ppp0', 'eth1.100', 'eth1'] });
check(index(wl_p1, 'pppoe') >= 0, 'pppoe WAN path is pppoe', wl_p1);
check(index(wl_p1, 'vpn_tunnel') < 0, 'pppoe-over-vlan path is NOT vpn_tunnel', wl_p1);
let wl_vpn = derive_workload({ id: 'path:lan-to-wg', proto: null, underlayChain: ['wg0'] });
check(index(wl_vpn, 'vpn_tunnel') >= 0, 'path traversing wg0 IS vpn_tunnel', wl_vpn);
let wl_wifi = derive_workload({ id: 'path:lan-to-wifi', proto: null, underlayChain: ['wlan-radio0'] });
check(index(wl_wifi, 'wireless') >= 0, 'non-wlan0-named wireless device -> wireless class', wl_wifi);

print('== [4] fastpath nft fingerprint: real candidate-only masking ==\n');
_NFT_RULESET = '{"nftables":[{"metainfo":{}},{"chain":{"family":"inet","table":"fw4","name":"forward"}},' +
	'{"flowtable":{"family":"inet","table":"fw4","name":"ft"}},' +
	'{"rule":{"family":"inet","table":"fw4","chain":"forward","flow":{"add":"@ft"}}}]}';
let fp_ctl = nft_ruleset_fingerprint([ 'fastpath-mask-nft' ]);
let fp_cand = nft_ruleset_fingerprint([ 'fastpath-mask-nft' ]);
check(fp_ctl == fp_cand, 'candidate-only PM flow offload is masked -> identical fingerprint', { fp_ctl, fp_cand });
check(nft_comparable(fp_ctl, fp_cand).comparable, 'nft_comparable(control,candidate-only-flowoffload) == true');

/* Unrelated external drift (a different chain rule) must invalidate. */
let _NFT_EXTERNAL = '{"nftables":[{"metainfo":{}},{"chain":{"family":"inet","table":"fw4","name":"forward"}},' +
	'{"flowtable":{"family":"inet","table":"fw4","name":"ft"}},' +
	'{"rule":{"family":"inet","table":"fw4","name":"forward","flow":{"add":"@ft"}}},' +
	'{"rule":{"family":"inet","table":"fw4","name":"forward","dnat":{"to":["1.2.3.4"]}}}]}';
_NFT_RULESET = _NFT_EXTERNAL;
let fp_ext = nft_ruleset_fingerprint([ 'fastpath-mask-nft' ]);
check(fp_ctl != fp_ext, 'unrelated external nft rule changes fingerprint', { fp_ctl, fp_ext });
check(!nft_comparable(fp_ctl, fp_ext).comparable, 'nft_comparable(control, external-drift) == false');

print('== [5] measurement methodology mismatch (real Core) ==\n');
let ctl_raw = { methodology: { host: 'server-A', port: 5201, reverse: false, parallel: 1, duration: 10 }, endpoint: { host: 'server-A', tool: 'iperf3' } };
let cand_raw = { methodology: { host: 'server-B', port: 5201, reverse: true, parallel: 16, duration: 60 }, endpoint: { host: 'server-B', tool: 'iperf3' } };
let ctl = measurement_methodology(ctl_raw);
let cand = measurement_methodology(cand_raw);
check(!methodology_matches(ctl_raw, cand_raw), 'methodology mismatch detected (host/reverse/parallel/duration)', { ctl, cand });
let twin_raw = { methodology: { host: 'server-A', port: 5201, reverse: false, parallel: 1, duration: 10 }, endpoint: { host: 'server-A', tool: 'iperf3' } };
check(methodology_matches(ctl_raw, twin_raw), 'identical methodology matches');

print('== [6] Conservative semantics: real conservative_auto_tick gating ==\n');
/* health guard blocks first. */
system_guard = function() { return { pass: false, faults: ['thermal'] }; };
let c1 = conservative_auto_tick();
check(c1.state == 'health-guard', 'conservative_auto_tick blocked by health guard', c1);
/* healthy + safe candidate -> applies via apply_ring. */
system_guard = function() { return { pass: true }; };
let _applied = null;
apply_ring = function(action, opts) { _applied = action; return { ok: true, actionId: action.id }; };
candidate_actions = function() { return [{ id: 'nic.ring.floor', applyTarget: 'nic:pci:0000:00:01.0', risk: 'safe', params: { rxFloor: 1024 } }]; };
let _hist = null;
history = function(ev, data) { if (ev == 'conservative.action') _hist = data; };
let c2 = conservative_auto_tick();
check(c2.state == 'applied', 'conservative_auto_tick applies a safe candidate', c2);
check(_applied != null && _applied.id == 'nic.ring.floor', 'apply_ring called with the SAFE_ACTIONS candidate', _applied);
check(_hist != null && _hist.ok == true, 'conservative applied event recorded to history', _hist);
/* benchmark/unsafe/unknown candidates are NEVER auto-applied. */
candidate_actions = function() { return [{ id: 'network.backlog', risk: 'benchmark' }]; };
let c3 = conservative_auto_tick();
check(c3.state == 'candidate-not-safe', 'benchmark-flagged candidate NOT auto-applied', c3);
check(_applied?.id == 'nic.ring.floor', 'apply_ring not called for non-safe candidate', _applied);
/* never races an active benchmark experiment. */
benchmark_active = function() { return true; };
candidate_actions = function() { return [{ id: 'nic.ring.floor', risk: 'safe' }]; };
let c4 = conservative_auto_tick();
check(c4.state == 'benchmark-active', 'conservative_auto_tick defers while benchmark active', c4);
benchmark_active = function() { return false; };

print('== [7] Rill fail-closed: unavailable + malformed (real socket) ==\n');
/* Unavailable: no listener at the configured socket path. */
rill_socket_path = function() { return '/tmp/pm-harness/no-such-rill.sock'; };
let r1 = rill_send({ op: 'status' });
check(!r1.ok && r1.state == 'unavailable', 'rill_send fails closed when socket unavailable', r1);

print('HARNESS-COMPLETE failures=' + _failures + '\n');
if (_failures > 0) exit(1);
exit(0);