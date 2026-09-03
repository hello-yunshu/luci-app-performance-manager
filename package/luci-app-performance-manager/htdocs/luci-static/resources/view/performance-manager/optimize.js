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
		const smart = (r && r.smartSelection) || {};
		const smartCard = pu.card(_('Smart policy'), E('div', {}, [
			pu.badge(smart.autoEligible === false ? _('Automatic action paused') : _('Eligible for automatic action'), smart.autoEligible === false ? 'warning' : 'success'),
			pu.kv([
				[_('Learning stage'), smart.learningStage || _('cold')], [_('Selected action'), smart.selectedActionId || '—'], [_('Confidence'), smart.confidence == null ? '—' : String(smart.confidence)], [_('Last reward'), smart.lastReward == null ? '—' : String(smart.lastReward)], [_('Auto eligibility'), smart.autoEligible === false ? _('Paused') : (smart.reason || _('Eligible'))], [_('Core recommendation'), smart.coreRecommendation || _('Deterministic fallback')], [_('Policy reason'), smart.reason || '—']
			])
		]), smart.drifted ? 'warning' : 'hero');
		if (smart.selectedActionId === 'pm.noop') nodes.push(pu.note(_('Rill recommends keeping the current configuration.'), 'success'));
		if (smart.drifted) nodes.push(pu.note(_('Performance drift detected. Automatic Rill decisions are temporarily paused.'), 'warning'));
		if (!actions.length) nodes.push(pu.note(_('No conservative changes are needed right now.'), 'success'));
		actions.forEach(function(a) {
			const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply safely') ]);
			apply.addEventListener('click', function() {
				const restore = pu.setBusy(apply, _('Applying…'));
				pm.apply(a.id, a.applyTarget).then(function(res) {
					ui.addNotification(null, E('p', {}, [ res && res.ok ? _('Action committed after verification.') : _('Action was not committed. Check the transaction details and try again.') ]));
				}).catch(function(error) {
					ui.addNotification(null, E('p', {}, [ _('Unable to apply action: %s. Check the transaction details and try again.').format(error.message || error) ]), 'error');
				}).finally(restore);
			});
			nodes.push(pu.card(a.id, E('div', {}, [
				pu.kv([ [_('Applies to'), a.applyTarget], [_('Affected targets'), (a.affectedTargets || []).join(', ')], [_('Evaluation paths'), (a.evaluationPaths || []).join(', ')], [_('Risk'), a.risk], [_('Reason'), a.reason] ]),
				E('div', { 'class': 'pm-toolbar' }, [ apply ])
			]), 'action'));
		});
		((r && r.observations) || []).forEach(function(o) { nodes.push(pu.card(o.id, E('p', {}, [ o.detail ]))); });
		((r && r.learnedAdvisory) || []).forEach(function(a) {
			const body = E('div', {}, [ pu.kv([ [_('Authority'), a.authority || _('none')], [_('Execution path'), a.kind === 'benchmark' ? _('Controlled benchmark') : (a.kind === 'noop' ? _('No mutation') : _('Safe direct apply'))], [_('Confidence'), a.confidence == null ? '—' : String(a.confidence)] ]) ]);
			if (a.kind === 'safe-direct') {
				const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply this Rill recommendation') ]);
				apply.addEventListener('click', function() {
					const restore = pu.setBusy(apply, _('Applying…'));
					pm.apply(a.actionId, a.applyTarget, 'rill-advisory', a.decisionId).then(function(res) {
						ui.addNotification(null, E('p', {}, [ res && res.ok ? _('Rill recommendation applied and verified.') : _('Rill recommendation was not applied. The decision binding was rejected or the safety check failed; review the safety state and try again.') ]));
					}).catch(function(error) {
						ui.addNotification(null, E('p', {}, [ _('Unable to apply Rill recommendation: %s. Review the safety state and try again.').format(error.message || error) ]), 'error');
					}).finally(restore);
				});
				body.appendChild(E('div', { 'class': 'pm-toolbar' }, [ apply ]));
			} else if (a.kind === 'noop') {
				body.appendChild(E('p', { 'class': 'pm-control-help' }, [ _('Rill recommends keeping the current configuration.') ]));
			} else {
				body.appendChild(E('p', { 'class': 'pm-control-help' }, [ _('This recommendation is for benchmark tests only. Open Performance test and complete both Companion evidence phases; it cannot be applied directly.') ]));
			}
			nodes.push(pu.card(_('Rill recommendation: %s').format(a.actionId || '—'), body));
		});
		return pu.page(_('Smart optimization'), _('Review supported actions and apply them only after Core safety checks. Existing user and external settings are preserved.'), [ smartCard, pu.grid(nodes, 'pm-card-grid--dense') ]);
	}
});
