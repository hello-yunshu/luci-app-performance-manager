'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.status(), pm.topology() ]); },
	render: function(data) {
		const s = data[0] || {}, t = data[1] || {};
		const profile = s.profile || {}, rill = s.rill || {}, guard = s.healthGuard || {};
		const status = E('div', { 'class': 'pm-status-row' }, [
			pu.badge(s.running ? _('Running') : _('Stopped'), s.running ? 'success' : 'danger'),
			pu.badge(_('Automation: %s').format(s.automation || '—')),
			pu.badge(_('Goal: %s').format(s.goal || '—')),
			pu.badge(rill.status || _('Rill Shadow · Collecting')),
			pu.badge(s.telemetry ? _('Telemetry Active') : _('Telemetry Off'), s.telemetry ? 'success' : 'warning'),
			pu.badge(s.failsafe ? _('Failsafe Ready') : _('Failsafe Off'), s.failsafe ? 'success' : 'warning'),
			pu.badge(profile.healthy ? _('Profile Healthy') : _('Profile Degraded'), profile.healthy ? 'success' : 'warning')
		]);
		return pu.page(_('Performance Manager'), _('Capability-first, topology-aware and transactional performance control plane.'), [
			pu.card(_('System health guard'), pu.kv([
				[_('Guard'), guard.pass ? _('Pass') : _('Blocked')],
				[_('Reasons'), (guard.reasons || []).join(', ') || _('None')],
				[_('Topology generation'), s.topologyGeneration],
				[_('Platform'), s.platform && (s.platform.hyperv ? 'Hyper-V' : (s.platform.kvm ? 'KVM' : _('Generic x86')))]
			]), 'hero'),
			status,
			pu.grid([
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
			]))
			]),
			pu.card(_('Advanced details'), pu.jsonBox({ status: s, topology: t }, _('Status and topology JSON')), 'muted')
		]);
	}
});
