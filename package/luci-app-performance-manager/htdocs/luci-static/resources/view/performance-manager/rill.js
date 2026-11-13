'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	load: function() {
		return Promise.all([ pm.rill(), pm.recommendations(), pm.history(100) ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: rill load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(payload) {
		if ((payload || []).some(function(d) { return d && d._loadError; }))
			return pu.page(_('Rill smart decisions'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const r = (payload && payload[0]) || {}, rec = (payload && payload[1]) || {}, history = (payload && payload[2]) || {}, s = rec.smartSelection || {};
		const refresh = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Refresh Rill decision') ]);
		refresh.addEventListener('click', function() {
			const restore = pu.setBusy(refresh, _('Refreshing...'));
			pm.rillRefresh().then(function(result) {
				if (result && result.ok === false)
					throw new Error(result.reason || result.state || _('Unable to refresh Rill.'));
				if (typeof window !== 'undefined') window.location.reload();
			}).catch(function(error) {
				ui.addNotification(null, E('p', {}, [ _('Unable to refresh Rill: %s. Try again.').format(labels.errorSummary(error)) ]), 'error');
			}).finally(restore);
		});
		const ranking = (s.ranking || []).slice(0, 5);
		const rows = ranking.length ? ranking.map(function(row, i) {
				const blocked = (s.blockedReasons || []).find(function(item) { return item.actionId === row.actionId; });
				return E('tr', { 'class': 'tr', 'aria-current': row.actionId === s.selectedCandidateId ? 'true' : 'false' }, [ E('td', { 'class': 'td', 'data-title': _('Rank') }, [ String(i + 1) ]), E('td', { 'class': 'td', 'data-title': _('Candidate') }, [ labels.actionName(row.actionId) ]), E('td', { 'class': 'td', 'data-title': _('Score') }, [ labels.percent(row.score) ]), E('td', { 'class': 'td', 'data-title': _('Eligibility') }, [ row.actionId === s.selectedCandidateId ? _('Selected') : (blocked ? labels.smartReason(blocked.reason) : _('Eligible')) ]), E('td', { 'class': 'td', 'data-title': _('Cooldown') }, [ blocked && blocked.cooldownRemaining ? labels.duration(blocked.cooldownRemaining) : '—' ]) ]);
			}) : [ E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'colspan': '5', 'data-title': _('Rank') }, [ _('No ranking is available yet. Refresh the decision or wait for the next evaluation.') ]) ]) ];
		const table = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [ E('caption', { 'class': 'pm-visually-hidden' }, [ _('Ranking table') ]), E('thead', {}, [ E('tr', {}, [ E('th', {}, [ _('Rank') ]), E('th', {}, [ _('Candidate') ]), E('th', {}, [ _('Score') ]), E('th', {}, [ _('Eligibility') ]), E('th', {}, [ _('Cooldown') ]) ]) ]), E('tbody', {}, rows) ]) ]);
		const context = s.context || {};
		const feedback = (history.history || []).filter(function(row) { return /^rill\.outcome\.(accepted|reconciled)/.test(row.event || ''); }).slice(-5).reverse();
		const feedbackRows = feedback.length ? feedback.map(function(row) { const d = row.data || {}; return E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'data-title': _('Candidate') }, [ labels.actionName(d.actionId) ]), E('td', { 'class': 'td', 'data-title': _('Goal') }, [ labels.goal(d.goal || s.goal) ]), E('td', { 'class': 'td', 'data-title': _('Reward') }, [ labels.percent(d.reward) ]), E('td', { 'class': 'td', 'data-title': _('Quality') }, [ labels.measurementQuality(d.measurementQuality) ]), E('td', { 'class': 'td', 'data-title': _('Result') }, [ d.accepted === true ? _('Accepted') : _('Reconciled') ]) ]); }) : [ E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'colspan': '5', 'data-title': _('Candidate') }, [ _('No validated feedback yet.') ]) ]) ];
		const feedbackTable = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [ E('caption', { 'class': 'pm-visually-hidden' }, [ _('Feedback table') ]), E('thead', {}, [ E('tr', {}, [ E('th', {}, [ _('Candidate') ]), E('th', {}, [ _('Goal') ]), E('th', {}, [ _('Reward') ]), E('th', {}, [ _('Quality') ]), E('th', {}, [ _('Result') ]) ]) ]), E('tbody', {}, feedbackRows) ]) ]);
		const outcomeText = s.lastOutcome
			? _('Reward %s · %s').format(labels.percent(s.lastOutcome.reward), labels.measurementQuality(s.lastOutcome.measurementQuality))
			: '—';
		const candidateHistory = s.candidateHistory || {};
		return pu.page(_('Rill smart decisions'), _('Rill ranks actions that passed the Core engine review; the Core engine keeps the final authority to execute them. Confidence and scores are shown as percentages (0–1 maps to 0–100%).'), [
			pu.card(_('Runtime status'), E('div', {}, [
				pu.kv([
					[_('State'), labels.runtimeStatus(r.status)],
					[_('Version'), labels.fmt(r.rillVersion || r.resolvedRillVersion)],
					[_('Transport'), labels.transport(r.transport)],
					[_('Protocol'), r.protocolVersion == null ? '—' : _('Runtime protocol v%s').format(r.protocolVersion)],
					[_('Last decision'), labels.reference(s.decisionId)],
					[_('Selected action'), labels.actionName(s.selectedActionId)],
					[_('Last outcome'), outcomeText]
				]),
				pu.jsonBox({ runtime: r, decisionId: s.decisionId, selectedCandidateId: s.selectedCandidateId, lastOutcome: s.lastOutcome }, _('Technical details'))
			]), 'hero'),
			pu.grid([
				pu.card(_('Decision context'), E('div', {}, [
					pu.kv([
						[_('Profile'), labels.profile(context.profile)],
						[_('Goal'), labels.goal(s.goal || context.goal)],
						[_('Path'), labels.path(context.pathId)],
						[_('Workload'), (context.workloadClass || []).map(labels.workloadClass).join('、') || '—'],
						[_('Topology generation'), context.topologyGeneration == null ? '—' : String(context.topologyGeneration)],
						[_('Route identity'), labels.routeIdentity(context.routeIdentity)],
						[_('Integration'), labels.integrationSummary(context.integrationState)]
					]),
					pu.jsonBox({ context: context }, _('Technical details'))
				]), 'muted'),
				pu.card(_('Selected candidate details'), E('div', {}, [
					pu.kv([
						[_('Business action'), labels.actionName(s.selectedActionId)],
						[_('Candidate identifier'), labels.reference(s.selectedCandidateId)],
						[_('Candidate reward mean'), labels.percent(candidateHistory.recentRewardMean)],
						[_('Candidate successes'), labels.fmt(candidateHistory.successCount)],
						[_('Candidate failures'), labels.fmt(candidateHistory.failureCount)],
						[_('Candidate rollbacks'), labels.fmt(candidateHistory.rollbackCount)],
						[_('Cooldown reason'), labels.smartReason(candidateHistory.cooldownReason)]
					]),
					E('p', { 'class': 'cbi-value-description' }, [ _('Candidate identifiers are kept in technical details so long identifiers do not crowd the page.') ]),
					pu.jsonBox({ candidateHistory: candidateHistory }, _('Technical details'))
				]), 'muted'),
				pu.card(_('Learning status'), E('div', {}, [
					pu.kv([
						[_('Learning stage'), labels.learningStage(s.learningStage)],
						[_('Validated samples'), s.validatedSamples == null ? '0' : String(s.validatedSamples)],
						[_('Minimum samples'), labels.fmt(s.minimumSamples)],
						[_('Confidence'), labels.percent(s.confidence)],
						[_('Last reward'), labels.percent(s.lastReward)],
						[_('Measurement quality'), labels.measurementQuality((s.lastOutcome && s.lastOutcome.measurementQuality) || s.measurementQuality)],
						[_('Drift'), s.drifted ? _('Detected') : _('Stable')],
						[_('Auto eligibility'), s.autoEligible === false ? _('Paused') : _('Eligible')],
						[_('Policy reason'), labels.smartReason(s.reason)]
					]),
					pu.jsonBox({ learningStage: s.learningStage, confidence: s.confidence, lastReward: s.lastReward, lastRewardComponents: s.lastRewardComponents, reason: s.reason }, _('Technical details'))
				]), 'muted')
			]),
			pu.grid([
				pu.card(_('Top ranking'), E('div', {}, [ pu.tableWrap(table), pu.toolbar([ refresh ]) ])),
				pu.card(_('Recent feedback'), pu.tableWrap(feedbackTable))
			]),
			(s.drifted ? pu.note(_('Performance drift detected. Rill Auto temporarily paused.'), 'warning') : null),
			pu.note(_('Rill provides observation and recommendations only. It cannot write UCI, sysctl, or firewall state, execute arbitrary shell commands, or apply actions.'), 'info'),
			pu.card(_('Rill details'), pu.jsonBox({ runtime: r, selection: s, advisory: rec.learnedAdvisory || [] }, _('Raw Rill contract')), 'muted')
		]);
	}
});
