'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.rill(), pm.recommendations() ]); },
	render: function(payload) {
		const r = (payload && payload[0]) || {}, rec = (payload && payload[1]) || {}, s = rec.smartSelection || {};
		const refresh = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Refresh Rill decision') ]);
		refresh.addEventListener('click', function() { refresh.disabled = true; pm.rillRefresh().then(function() { if (typeof window !== 'undefined') window.location.reload(); }).finally(function() { refresh.disabled = false; }); });
		const ranking = (s.ranking || []).slice(0, 3);
		const rows = ranking.length ? ranking.map(function(row, i) { return E('tr', {}, [ E('td', {}, [ String(i + 1) ]), E('td', {}, [ row.actionId || '—' ]), E('td', {}, [ row.score == null ? '—' : String(row.score) ]), E('td', {}, [ row.actionId === s.selectedActionId ? _('Selected') : _('Candidate') ]) ]); }) : [ E('tr', {}, [ E('td', { 'colspan': '4' }, [ _('No ranking is available yet.') ]) ]) ];
		const table = E('table', { 'class': 'table pm-ranking-table' }, [ E('thead', {}, [ E('tr', {}, [ E('th', {}, [ _('Rank') ]), E('th', {}, [ _('Action') ]), E('th', {}, [ _('Score') ]), E('th', {}, [ _('Status') ]) ]) ]), E('tbody', {}, rows) ]);
		return pu.page(_('RillML (Rill) Intelligence'), _('Rill ranks legal actions while Core keeps the final execution authority.'), [
			pu.card(_('Runtime status'), pu.kv([
				[_('State'), r.status || _('Runtime · Collecting')], [_('Transport'), r.transport || '—'], [_('Runtime contract'), r.protocolVersion == null ? '—' : 'Runtime v' + r.protocolVersion], [_('Last decision'), s.decisionId || '—']
			]), 'hero'),
			pu.card(_('Learning status'), pu.kv([
				[_('Learning stage'), s.learningStage || _('cold')], [_('Validated samples'), s.validatedSamples == null ? '0' : String(s.validatedSamples)], [_('Minimum samples'), s.minimumSamples == null ? '—' : String(s.minimumSamples)], [_('Confidence'), s.confidence == null ? '—' : String(s.confidence)], [_('Last reward'), s.lastReward == null ? '—' : String(s.lastReward)], [_('Auto eligibility'), s.autoEligible === false ? _('Paused') : (s.reason || _('Eligible'))]
			]), 'muted'),
			pu.card(_('Top ranking'), E('div', {}, [ table, pu.toolbar([ refresh ]) ])),
			(s.drifted ? pu.note(_('Performance drift detected. Rill Auto temporarily paused.'), 'warning') : null),
			pu.note(_('Rill cannot write UCI, sysctl or firewall state, cannot execute arbitrary shell, and cannot apply Actions.'), 'info'),
			pu.card(_('Rill details'), pu.jsonBox({ runtime: r, selection: s, advisory: rec.learnedAdvisory || [] }, _('Raw Rill contract')), 'muted')
		]);
	}
});
