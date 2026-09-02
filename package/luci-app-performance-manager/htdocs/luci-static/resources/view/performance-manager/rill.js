'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.rill(), pm.recommendations(), pm.history(100) ]); },
	render: function(payload) {
		const r = (payload && payload[0]) || {}, rec = (payload && payload[1]) || {}, history = (payload && payload[2]) || {}, s = rec.smartSelection || {};
		const refresh = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Refresh Rill decision') ]);
		refresh.addEventListener('click', function() {
			refresh.disabled = true;
			pm.rillRefresh().then(function(result) {
				if (result && result.ok === false)
					throw new Error(result.reason || result.state || 'rill-refresh-failed');
				if (typeof window !== 'undefined') window.location.reload();
			}).catch(function(error) {
				ui.addNotification(null, E('p', {}, [ _('Rill refresh failed: %s').format(error.message) ]), 'error');
			}).finally(function() { refresh.disabled = false; });
		});
		const ranking = (s.ranking || []).slice(0, 5);
		const rows = ranking.length ? ranking.map(function(row, i) {
				const blocked = (s.blockedReasons || []).find(function(item) { return item.actionId === row.actionId; });
				return E('tr', {}, [ E('td', {}, [ String(i + 1) ]), E('td', {}, [ row.actionId || '—' ]), E('td', {}, [ row.score == null ? '—' : String(row.score) ]), E('td', {}, [ row.actionId === s.selectedCandidateId ? _('Selected') : (blocked ? (blocked.reason || _('Blocked')) : _('Eligible')) ]), E('td', {}, [ blocked && blocked.cooldownRemaining ? String(blocked.cooldownRemaining) : '—' ]) ]);
			}) : [ E('tr', {}, [ E('td', { 'colspan': '5' }, [ _('No ranking is available yet.') ]) ]) ];
		const table = E('table', { 'class': 'table pm-ranking-table' }, [ E('thead', {}, [ E('tr', {}, [ E('th', {}, [ _('Rank') ]), E('th', {}, [ _('Candidate') ]), E('th', {}, [ _('Score') ]), E('th', {}, [ _('Eligibility') ]), E('th', {}, [ _('Cooldown') ]) ]) ]), E('tbody', {}, rows) ]);
		const context = s.context || {};
		const feedback = (history.history || []).filter(function(row) { return /^rill\.outcome\.(accepted|reconciled)/.test(row.event || ''); }).slice(-5).reverse();
		const feedbackRows = feedback.length ? feedback.map(function(row) { const d = row.data || {}; return E('tr', {}, [ E('td', {}, [ d.actionId || '—' ]), E('td', {}, [ d.goal || s.goal || '—' ]), E('td', {}, [ d.reward == null ? '—' : String(d.reward) ]), E('td', {}, [ d.measurementQuality || 'controlled_ab' ]), E('td', {}, [ d.accepted === true ? _('Accepted') : _('Reconciled') ]) ]); }) : [ E('tr', {}, [ E('td', { 'colspan': '5' }, [ _('No validated feedback yet.') ]) ]) ];
		const feedbackTable = E('table', { 'class': 'table pm-ranking-table' }, [ E('thead', {}, [ E('tr', {}, [ E('th', {}, [ _('Candidate') ]), E('th', {}, [ _('Goal') ]), E('th', {}, [ _('Reward') ]), E('th', {}, [ _('Quality') ]), E('th', {}, [ _('Result') ]) ]) ]), E('tbody', {}, feedbackRows) ]);
		return pu.page(_('RillML (Rill) Intelligence'), _('Rill ranks legal actions while Core keeps the final execution authority.'), [
			pu.card(_('Runtime status'), pu.kv([
				[_('State'), r.status || _('Runtime · Collecting')], [_('Version'), r.rillVersion || r.resolvedRillVersion || '—'], [_('Transport'), r.transport || '—'], [_('Runtime contract'), r.protocolVersion == null ? '—' : 'Runtime v' + r.protocolVersion], [_('Last decision'), s.decisionId || '—'], [_('Selected action'), s.selectedActionId || '—'], [_('Selected candidate'), s.selectedCandidateId || '—'], [_('Last outcome'), s.lastOutcome ? JSON.stringify(s.lastOutcome) : '—']
			]), 'hero'),
			pu.card(_('Decision context'), pu.kv([
				[_('Profile'), context.profile || '—'], [_('Goal'), s.goal || context.goal || '—'], [_('Path'), context.pathId || '—'], [_('Workload'), (context.workloadClass || []).join(', ') || '—'], [_('Topology generation'), context.topologyGeneration == null ? '—' : String(context.topologyGeneration)], [_('Route identity'), context.routeIdentity || '—'], [_('Integration'), context.integrationState ? JSON.stringify(context.integrationState) : '—']
			]), 'muted'),
			pu.card(_('Selected candidate details'), pu.kv([
				[_('Business action'), s.selectedActionId || '—'], [_('Candidate ID'), s.selectedCandidateId || '—'], [_('Candidate reward mean'), s.candidateHistory?.recentRewardMean == null ? '—' : String(s.candidateHistory.recentRewardMean)], [_('Candidate successes'), s.candidateHistory?.successCount == null ? '—' : String(s.candidateHistory.successCount)], [_('Candidate failures'), s.candidateHistory?.failureCount == null ? '—' : String(s.candidateHistory.failureCount)], [_('Candidate rollbacks'), s.candidateHistory?.rollbackCount == null ? '—' : String(s.candidateHistory.rollbackCount)], [_('Cooldown reason'), s.candidateHistory?.cooldownReason || '—']
			]), 'muted'),
			pu.card(_('Learning status'), pu.kv([
				[_('Learning stage'), s.learningStage || _('cold')], [_('Validated samples'), s.validatedSamples == null ? '0' : String(s.validatedSamples)], [_('Minimum samples'), s.minimumSamples == null ? '—' : String(s.minimumSamples)], [_('Confidence'), s.confidence == null ? '—' : String(s.confidence)], [_('Last reward'), s.lastReward == null ? '—' : String(s.lastReward)], [_('Reward components'), s.lastRewardComponents ? JSON.stringify(s.lastRewardComponents) : '—'], [_('Measurement quality'), s.lastOutcome?.measurementQuality || '—'], [_('Drift'), s.drifted ? _('Detected') : _('Stable')], [_('Auto eligibility'), s.autoEligible === false ? _('Paused') : (s.reason || _('Eligible'))]
			]), 'muted'),
			pu.card(_('Top ranking'), E('div', {}, [ table, pu.toolbar([ refresh ]) ])),
			pu.card(_('Recent feedback'), feedbackTable),
			(s.drifted ? pu.note(_('Performance drift detected. Rill Auto temporarily paused.'), 'warning') : null),
			pu.note(_('Rill cannot write UCI, sysctl or firewall state, cannot execute arbitrary shell, and cannot apply Actions.'), 'info'),
			pu.card(_('Rill details'), pu.jsonBox({ runtime: r, selection: s, advisory: rec.learnedAdvisory || [] }, _('Raw Rill contract')), 'muted')
		]);
	}
});
