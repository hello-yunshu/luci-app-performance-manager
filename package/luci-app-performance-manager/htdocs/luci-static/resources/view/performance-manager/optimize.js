'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	load: function() {
		return pm.recommendations().catch(function(err) {
			console.error('performance-manager: optimize load failed', err);
			return { _loadError: err };
		});
	},
	render: function(r) {
		if (r && r._loadError)
			return pu.page(_('Smart optimization'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const actions = (r && r.actions) || [];
		const nodes = [];
		const smart = (r && r.smartSelection) || {};
		const smartCard = pu.card(_('Smart policy'), E('div', {}, [
			pu.badge(smart.autoEligible === false ? _('Automatic action paused') : _('Eligible for automatic action'), smart.autoEligible === false ? 'warning' : 'success'),
			pu.kv([
				[_('Learning stage'), labels.learningStage(smart.learningStage)],
				[_('Selected action'), labels.actionName(smart.selectedActionId)],
				[_('Confidence'), labels.percent(smart.confidence)],
				[_('Last reward'), labels.percent(smart.lastReward)],
				[_('Auto eligibility'), smart.autoEligible === false ? _('Paused') : _('Eligible')],
				[_('Core recommendation'), labels.actionName(smart.coreRecommendation)],
				[_('Policy reason'), labels.smartReason(smart.reason)]
			]),
			pu.jsonBox({
				learningStage: smart.learningStage,
				selectedActionId: smart.selectedActionId,
				confidence: smart.confidence,
				lastReward: smart.lastReward,
				autoEligible: smart.autoEligible,
				coreRecommendation: smart.coreRecommendation,
				reason: smart.reason
			}, _('Technical details'))
		]), smart.drifted ? 'warning' : 'hero');
		if (smart.selectedActionId === 'pm.noop') nodes.push(pu.note(_('Rill recommends keeping the current configuration.'), 'success'));
		if (smart.drifted) nodes.push(pu.note(_('Performance drift detected. Automatic Rill decisions are temporarily paused.'), 'warning'));
		if (!actions.length) nodes.push(pu.note(_('No conservative changes are needed right now.'), 'success'));
		actions.forEach(function(a) {
			const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply safely') ]);
			apply.addEventListener('click', function() {
				const restore = pu.setBusy(apply, _('Applying...'));
				pm.apply(a.id, a.applyTarget).then(function(res) {
					if (res && res.ok)
						ui.addNotification(null, E('p', {}, [ _('Action committed after verification.') ]));
					else
						ui.addNotification(null, E('div', {}, [
							E('p', {}, [ _('Action was not committed: %s. Check the transaction details and try again.').format(labels.errorSummary(res)) ]),
							res ? pu.jsonBox(res, _('Technical details')) : null
						]), 'error');
				}).catch(function(error) {
					ui.addNotification(null, E('p', {}, [ _('Unable to apply action: %s. Check the transaction details and try again.').format(labels.errorSummary(error)) ]), 'error');
				}).finally(restore);
			});
			nodes.push(pu.card(labels.actionName(a.id), E('div', {}, [
				E('p', { 'class': 'cbi-value-description' }, [ labels.actionDesc(a.id) ]),
				pu.kv([
					[_('Applies to'), labels.target(a.applyTarget)],
					[_('Affected targets'), (a.affectedTargets || []).map(labels.target).join('、') || _('None')],
					[_('Evaluation paths'), (a.evaluationPaths || []).map(labels.path).join('、') || _('None')],
					[_('Risk'), labels.risk(a.risk)],
					[_('Reason'), labels.actionReason(a.reason)]
				]),
				pu.jsonBox({ id: a.id, applyTarget: a.applyTarget, risk: a.risk, reason: a.reason }, _('Technical details')),
				E('div', {}, [ apply ])
			]), 'action'));
		});
		((r && r.observations) || []).forEach(function(o) {
			nodes.push(pu.card(labels.capabilityName(o.id), E('div', {}, [
				E('p', {}, [ labels.observationDetail(o.detail) ]),
				pu.jsonBox(o, _('Technical details'))
			])));
		});
		((r && r.learnedAdvisory) || []).forEach(function(a) {
			const body = E('div', {}, [ pu.kv([ [_('Authority'), labels.authority(a.authority)], [_('Execution path'), a.kind === 'benchmark' ? _('Controlled benchmark') : (a.kind === 'noop' ? _('No mutation') : _('Safe direct apply'))], [_('Confidence'), labels.percent(a.confidence)] ]) ]);
			if (a.kind === 'safe-direct') {
				const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply this Rill recommendation') ]);
				apply.addEventListener('click', function() {
					const restore = pu.setBusy(apply, _('Applying...'));
					pm.apply(a.actionId, a.applyTarget, 'rill-advisory', a.decisionId).then(function(res) {
						if (res && res.ok)
							ui.addNotification(null, E('p', {}, [ _('Rill recommendation applied and verified.') ]));
						else
							ui.addNotification(null, E('div', {}, [
								E('p', {}, [ _('Rill recommendation was not applied: %s. Review the safety state and try again.').format(labels.errorSummary(res)) ]),
								res ? pu.jsonBox(res, _('Technical details')) : null
							]), 'error');
					}).catch(function(error) {
						ui.addNotification(null, E('p', {}, [ _('Unable to apply Rill recommendation: %s. Review the safety state and try again.').format(labels.errorSummary(error)) ]), 'error');
					}).finally(restore);
				});
				body.appendChild(E('div', {}, [ apply ]));
			} else if (a.kind === 'noop') {
				body.appendChild(E('p', { 'class': 'cbi-value-description' }, [ _('Rill recommends keeping the current configuration.') ]));
			} else {
				body.appendChild(E('p', { 'class': 'cbi-value-description' }, [ _('This recommendation is for a performance test only. Open Performance test and complete both detection phases with the companion test tool; it cannot be applied directly.') ]));
			}
			body.appendChild(pu.jsonBox({ actionId: a.actionId, kind: a.kind, authority: a.authority, decisionId: a.decisionId }, _('Technical details')));
			nodes.push(pu.card(_('Rill recommendation: %s').format(labels.actionName(a.actionId)), body));
		});
		return pu.page(_('Smart optimization'), _('Review supported actions and apply them only after Core safety checks. Existing user and external settings are preserved.'), [ smartCard, pu.grid(nodes) ]);
	}
});
