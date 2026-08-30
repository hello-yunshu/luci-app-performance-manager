'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return pm.recommendations(); },
	render: function(r) {
		const actions = (r && r.actions) || [];
		const nodes = [];
		if (!actions.length) nodes.push(pu.note(_('No conservative changes are currently needed.'), 'success'));
		actions.forEach(function(a) {
			const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply safely') ]);
			apply.addEventListener('click', function() {
				apply.disabled = true;
				pm.apply(a.id, a.applyTarget).then(function(res) {
					ui.addNotification(null, E('p', {}, [ res && res.ok ? _('Action committed after verification.') : _('Action was not committed; inspect transaction details.') ]));
				}).finally(function() { apply.disabled = false; });
			});
			nodes.push(pu.card(a.id, E('div', {}, [
				pu.kv([ [_('Applies To'), a.applyTarget], [_('Affected'), (a.affectedTargets || []).join(', ')], [_('Evaluated On'), (a.evaluationPaths || []).join(', ')], [_('Risk'), a.risk], [_('Reason'), a.reason] ]),
				E('div', { 'class': 'pm-toolbar' }, [ apply ])
			])));
		});
		(r.observations || []).forEach(function(o) { nodes.push(pu.card(o.id, E('p', {}, [ o.detail ]))); });
		(r.learnedAdvisory || []).forEach(function(a) {
			const body = E('div', {}, [ pu.kv([ [_('Authority'), a.authority || _('none')], [_('Execution path'), a.kind === 'benchmark' ? _('Controlled benchmark') : _('Safe direct apply')], [_('Confidence'), a.confidence == null ? '—' : String(a.confidence)] ]) ]);
			if (a.kind === 'safe-direct') {
				const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply this exact Rill advisory') ]);
				apply.addEventListener('click', function() {
					apply.disabled = true;
					pm.apply(a.actionId, a.applyTarget, 'rill-advisory', a.decisionId).then(function(res) {
						ui.addNotification(null, E('p', {}, [ res && res.ok ? _('Exact Rill decision applied and verified.') : _('The advisory was not applied; its exact decision binding was rejected or the safety gate failed.') ]));
					}).finally(function() { apply.disabled = false; });
				});
				body.appendChild(E('div', { 'class': 'pm-toolbar' }, [ apply ]));
			} else {
				body.appendChild(E('p', { 'class': 'pm-control-help' }, [ _('This advisory is benchmark-only. Open Performance Test and complete both Companion evidence legs; it can never enter direct Apply.') ]));
			}
			nodes.push(pu.card(_('Rill advisory: %s').format(a.actionId || '—'), body));
		});
		return pu.page(_('Smart Optimization'), _('Only legal, supported actions are shown. Existing user/external/preexisting settings are respected.'), [ pu.grid(nodes) ]);
	}
});
