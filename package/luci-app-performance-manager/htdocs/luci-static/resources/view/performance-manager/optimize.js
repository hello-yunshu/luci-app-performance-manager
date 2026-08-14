'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return pm.recommendations(); },
	render: function(r) {
		const actions = (r && r.actions) || [];
		const nodes = [ E('h2', {}, [ _('Smart Optimization') ]), E('p', {}, [ _('Only legal, supported actions are shown. Existing user/external/preexisting settings are respected.') ]) ];
		if (!actions.length) nodes.push(E('div', { 'class': 'alert-message success' }, [ _('No conservative changes are currently needed.') ]));
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
				E('div', { 'style': 'margin-top:.8rem' }, [ apply ])
			])));
		});
		(r.observations || []).forEach(function(o) { nodes.push(pu.card(o.id, E('p', {}, [ o.detail ]))); });
		(r.learnedAdvisory || []).forEach(function(a) { nodes.push(pu.card(_('Rill advisory: %s').format(a.actionId || '—'), pu.kv([ [_('Authority'), a.authority || _('none')], [_('Confidence'), a.confidence || '—'], [_('Validated samples'), a.validatedSamples == null ? '—' : String(a.validatedSamples)], [_('Mean reward'), a.meanReward == null ? '—' : String(a.meanReward)] ]))); });
		return E([], nodes);
	}
});
