'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.status(), pm.topology() ]); },
	render: function(data) {
		const s = data[0] || {}, t = data[1] || {};
		const profile = s.profile || {}, rill = s.rill || {}, guard = s.healthGuard || {};
		return E([], [
			E('h2', {}, [ _('Performance Manager') ]),
			E('p', {}, [ _('Capability-first, topology-aware and transactional performance control plane.') ]),
			E('div', {}, [
				pu.badge(s.running ? _('Running') : _('Stopped')),
				pu.badge(_('Automation: %s').format(s.automation || '—')),
				pu.badge(_('Goal: %s').format(s.goal || '—')),
				pu.badge(rill.status || _('Rill Shadow · Collecting')),
				pu.badge(s.telemetry ? _('Telemetry Active') : _('Telemetry Off')),
				pu.badge(s.failsafe ? _('Failsafe Ready') : _('Failsafe Off')),
				pu.badge(profile.healthy ? _('Profile Healthy') : _('Profile Degraded'))
			]),
			pu.card(_('System health guard'), pu.kv([
				[_('Guard'), guard.pass ? _('Pass') : _('Blocked')],
				[_('Reasons'), (guard.reasons || []).join(', ') || _('None')],
				[_('Topology generation'), s.topologyGeneration],
				[_('Platform'), s.platform && (s.platform.hyperv ? 'Hyper-V' : (s.platform.kvm ? 'KVM' : _('Generic x86')))]
			])),
			pu.card(_('Native Packet Steering'), pu.kv([
				[_('Provider'), s.nativePacketSteering && s.nativePacketSteering.provider],
				[_('Availability'), s.nativePacketSteering && s.nativePacketSteering.availability],
				[_('Policy'), _('Observe / Respect')],
				[_('Ownership'), s.nativePacketSteering && s.nativePacketSteering.ownership]
			])),
			pu.card(_('Path'), pu.kv([
				[_('LAN → WAN'), t.paths && t.paths[0] && t.paths[0].routeIdentity],
				[_('Workload'), t.paths && t.paths[0] && (t.paths[0].workloadClass || []).join(', ')],
				[_('Stable targets'), t.paths && t.paths[0] && (t.paths[0].targetRefs || []).join(', ')]
			])),
			pu.jsonBox({ status: s, topology: t }, _('Advanced details'))
		]);
	}
});
