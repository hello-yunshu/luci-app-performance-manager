'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.status(), pm.topology(), pm.transactions() ]); },
	render: function(data) {
		const s = data[0] || {}, t = data[1] || {};
		const txs = (data[2] && data[2].transactions) || [];
		const profile = s.profile || {}, rill = s.rill || {}, guard = s.healthGuard || {};
		const status = E('div', { 'class': 'pm-status-row' }, [
			E('span', { 'class': 'pm-status-label' }, [ _('System status') ]),
			pu.badge(s.running ? _('Running') : _('Stopped'), s.running ? 'success' : 'danger'),
			pu.badge(_('Automation: %s').format(s.automation || '—')),
			pu.badge(_('Goal: %s').format(s.goal || '—')),
			pu.badge(rill.status || _('Rill Runtime · Collecting')),
			pu.badge(s.telemetry ? _('Telemetry enabled') : _('Telemetry disabled'), s.telemetry ? 'success' : 'warning'),
			pu.badge(s.failsafe ? _('Failsafe enabled') : _('Failsafe disabled'), s.failsafe ? 'success' : 'warning'),
			pu.badge(profile.healthy ? _('Profile healthy') : _('Profile degraded'), profile.healthy ? 'success' : 'warning')
		]);
		const recentTx = txs[0] || {};
		return pu.page(_('Performance Manager'), _('See system health, active safeguards, and the latest verified action.'), [
			status,
			pu.grid([
				pu.card(_('System health guard'), E('div', {}, [
					pu.badge(guard.pass ? _('Health guard passed') : _('Blocked by health guard'), guard.pass ? 'success' : 'warning'),
					pu.kv([
						[_('Reasons'), (guard.reasons || []).join(', ') || _('None')],
						[_('Topology generation'), s.topologyGeneration],
						[_('Platform'), s.platform && (s.platform.hyperv ? 'Hyper-V' : (s.platform.kvm ? 'KVM' : _('Generic x86')))]
					])
				]), 'hero'),
				pu.card(_('Recent transaction'), pu.kv([
					[_('Action'), recentTx.actionId],
					[_('State'), recentTx.state],
					[_('Target'), recentTx.applyTarget],
					[_('Boot identity'), recentTx.bootId]
				]), txs.length ? null : 'muted')
			], 'pm-card-grid--primary'),
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
			], 'pm-card-grid--supporting'),
			pu.card(_('Advanced details'), pu.jsonBox({ status: s, topology: t }, _('Status and topology JSON')), 'muted')
		]);
	}
});
