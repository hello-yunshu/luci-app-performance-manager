'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	load: function() { return Promise.all([ pm.status(), pm.topology(), pm.transactions() ]); },
	render: function(data) {
		const s = data[0] || {}, t = data[1] || {};
		const txs = (data[2] && data[2].transactions) || [];
		const profile = s.profile || {}, rill = s.rill || {}, guard = s.healthGuard || {};
		/* degraded means "healthy but a recommended package is missing"; an
		 * unhealthy profile is a different state and must not be labelled
		 * degraded. */
		const profileBadge = profile.healthy
			? (profile.degraded
				? pu.badge(_('Profile degraded'), 'warning')
				: pu.badge(_('Profile healthy'), 'success'))
			: pu.badge(_('Profile unmet'), 'danger');
		const status = E('div', { 'class': 'pm-status-row' }, [
			E('span', { 'class': 'pm-status-label' }, [ _('System status') ]),
			pu.badge(s.running ? _('Running') : _('Stopped'), s.running ? 'success' : 'danger'),
			pu.badge(_('Automation: %s').format(labels.automation(s.automation))),
			pu.badge(_('Goal: %s').format(labels.goal(s.goal))),
			pu.badge(labels.runtimeStatus(rill.status || 'Runtime · Collecting')),
			pu.badge(s.telemetry ? _('Telemetry enabled') : _('Telemetry disabled'), s.telemetry ? 'success' : 'warning'),
			pu.badge(s.failsafe ? _('Failsafe enabled') : _('Failsafe disabled'), s.failsafe ? 'success' : 'warning'),
			profileBadge
		]);
		const recentTx = txs[0] || {};
		const recentBody = [
			pu.kv([
				[_('Action'), labels.actionName(recentTx.actionId)],
				[_('State'), labels.state(recentTx.state)],
				[_('Target'), labels.target(recentTx.applyTarget)],
				[_('Boot identity'), labels.shortId(recentTx.bootId)]
			])
		];
		if (txs.length)
			recentBody.push(pu.jsonBox({
				actionId: recentTx.actionId,
				state: recentTx.state,
				applyTarget: recentTx.applyTarget,
				bootId: recentTx.bootId
			}, _('Technical details')));
		return pu.page(_('Performance Manager'), _('See system health, active safeguards, and the latest verified action. Confidence and scores are shown as percentages (0–1 maps to 0–100%).'), [
			status,
			pu.grid([
				pu.card(_('System health guard'), E('div', {}, [
					pu.badge(guard.pass ? _('Health guard passed') : _('Blocked by health guard'), guard.pass ? 'success' : 'warning'),
					pu.kv([
						[_('Reasons'), (guard.reasons || []).map(labels.guardReason).join('、') || _('None')],
						[_('Topology generation'), s.topologyGeneration],
						[_('Platform'), s.platform && (s.platform.hyperv ? 'Hyper-V' : (s.platform.kvm ? 'KVM' : _('Generic x86')))]
					])
				]), 'hero'),
				pu.card(_('Recent transaction'), E('div', {}, recentBody), txs.length ? null : 'muted')
			], 'pm-card-grid--primary'),
			pu.grid([
			pu.card(_('Native Packet Steering'), E('div', {}, [
				pu.kv([
					[_('Provider'), labels.provider(s.nativePacketSteering && s.nativePacketSteering.provider)],
					[_('Availability'), labels.availability(s.nativePacketSteering && s.nativePacketSteering.availability)],
					[_('Policy'), labels.policy('observe-respect')],
					[_('Ownership'), labels.ownership(s.nativePacketSteering && s.nativePacketSteering.ownership)]
				]),
				s.nativePacketSteering ? pu.jsonBox(s.nativePacketSteering, _('Technical details')) : null
			])),
			pu.card(_('Path'), E('div', {}, [
				pu.kv([
					[_('LAN → WAN'), labels.routeIdentity(t.paths && t.paths[0] && t.paths[0].routeIdentity)],
					[_('Workload'), ((t.paths && t.paths[0] && t.paths[0].workloadClass) || []).map(labels.workloadClass).join('、') || _('None')],
					[_('Stable targets'), ((t.paths && t.paths[0] && t.paths[0].targetRefs) || []).map(labels.target).join('、') || _('None')]
				]),
				t.paths && t.paths[0] ? pu.jsonBox({
					routeIdentity: t.paths[0].routeIdentity,
					routeProvider: t.paths[0].routeProvider,
					workloadClass: t.paths[0].workloadClass,
					targetRefs: t.paths[0].targetRefs
				}, _('Technical details')) : null
			]))
			], 'pm-card-grid--supporting'),
			pu.card(_('Advanced details'), pu.jsonBox({ status: s, topology: t }, _('Status and topology JSON')), 'muted')
		]);
	}
});
