'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	handleSave: null,
	handleSaveApply: null,
	handleReset: null,

	load: function() {
		return Promise.resolve({ _lazy: true });
	},
	render: function(r) {
		if (r && r._lazy) {
			const placeholderTitle = E('h3', {}, [ _('Optimization recommendations') ]);
			const placeholder = E('div', { 'class': 'cbi-section' }, [ placeholderTitle, E('p', {
				'class': 'cbi-value-description', 'role': 'status', 'aria-live': 'polite'
			}, _('Loading recommendations when this section is reached…')) ]);
			const page = pu.page(_('Smart optimization'), _('Review supported actions and apply them only after Core safety checks. Existing user and external settings are preserved.'), [ placeholder ]);
			let started = false;
			const load = function() {
				if (started) return;
				started = true;
				placeholder.replaceChildren(placeholderTitle, E('p', {
					'class': 'cbi-value-description', 'role': 'status', 'aria-live': 'polite'
				}, _('Loading...')));
				pm.recommendations().then(function(result) {
					page.replaceWith(this.render(result));
				}.bind(this)).catch(function(error) {
					started = false;
					placeholder.replaceChildren(
						placeholderTitle,
						E('p', { 'role': 'alert', 'aria-live': 'assertive' }, _('Unable to load recommendations: %s').format(labels.errorSummary(error))),
						E('button', {
							'class': 'btn cbi-button', 'type': 'button',
							'click': load
						}, _('Retry'))
					);
				}.bind(this));
			}.bind(this);
			if (typeof window.IntersectionObserver === 'function') {
				const observer = new window.IntersectionObserver(function(entries) {
					if (entries.some(function(entry) { return entry.isIntersecting; })) {
						observer.disconnect();
						load();
					}
				}, { threshold: 0.01 });
				observer.observe(placeholder);
			} else window.setTimeout(load, 0);
			return page;
		}
		if (r && r._loadError)
			return pu.page(_('Smart optimization'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const actions = (r && r.actions) || [];
		const nodes = [];
		const observationItems = [];
		const smart = (r && r.smartSelection) || {};
		const noChangeNeeded = smart.selectedActionId === 'pm.noop';
		const rillUnavailable = !!smart.rillState && smart.rillState !== 'available' && smart.rillState !== 'learning';
		const autoState = rillUnavailable ? _('Rill unavailable') :
			noChangeNeeded ? _('No change needed') :
			smart.autoEligible === true ? _('Ready') :
			smart.autoEligible === false ? _('Paused') : _('Not evaluated');
		const statusText = rillUnavailable ? _('Rill unavailable') :
			noChangeNeeded ? _('No change needed') :
			smart.autoEligible === true ? _('Ready for automatic action') :
			smart.autoEligible === false ? _('Automatic action paused') : _('Automatic action not evaluated');
		const statusTone = rillUnavailable ? 'warning' :
			noChangeNeeded ? 'neutral' :
			smart.autoEligible === true ? 'success' :
			smart.autoEligible === false ? 'warning' : 'neutral';
		const smartBody = E('div', {}, [
			pu.badge(statusText, statusTone),
			pu.kv([
				[_('Selected action'), labels.actionName(smart.selectedActionId)],
				[_('Automatic action'), autoState]
			]),
			pu.jsonBox({
				learningStage: smart.learningStage,
				selectedActionId: smart.selectedActionId,
				confidence: smart.confidence,
				lastReward: smart.lastReward,
				autoEligible: smart.autoEligible,
				coreRecommendation: smart.coreRecommendation,
				reason: smart.reason
			}, _('Learning and policy details'))
		]);
		const smartCard = pu.card(_('Smart policy'), smartBody);
		if (smart.drifted) nodes.push(pu.note(_('Performance drift detected. Automatic Rill decisions are temporarily paused.'), 'warning'));
		if (!actions.length && smart.selectedActionId !== 'pm.noop') nodes.push(pu.note(_('No conservative changes are needed right now.'), 'success'));
		actions.forEach(function(a) {
			const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply safely') ]);
			apply.addEventListener('click', function() {
				const restore = pu.setBusy(apply, _('Applying...'));
				pm.apply(a.id, a.applyTarget).then(function(res) {
					if (res && res.ok)
						ui.addNotification(null, E('p', {}, [ _('Action committed after verification.') ]));
					else {
						const details = [ E('p', {}, [ _('Action was not committed: %s. Check the transaction details and try again.').format(labels.errorSummary(res)) ]) ];
						if (res) details.push(pu.jsonBox(res, _('Technical details')));
						ui.addNotification(null, E('div', {}, details), 'error');
					}
				}).catch(function(error) {
					ui.addNotification(null, E('p', {}, [ _('Unable to apply action: %s. Check the transaction details and try again.').format(labels.errorSummary(error)) ]), 'error');
				}).finally(restore);
			});
			nodes.push(pu.card(labels.actionName(a.id), E('div', {}, [
				E('p', { 'class': 'cbi-value-description' }, [ labels.actionDesc(a.id) ]),
				pu.kv([
					[_('Applies to'), labels.target(a.applyTarget)],
					[_('Risk'), labels.risk(a.risk)],
					[_('Why'), labels.actionReason(a.reason)]
				]),
				pu.jsonBox({ id: a.id, applyTarget: a.applyTarget, affectedTargets: a.affectedTargets, evaluationPaths: a.evaluationPaths, reason: a.reason }, _('Affected targets and evaluation details')),
				E('div', {}, [ apply ])
			])));
		});
		((r && r.observations) || []).forEach(function(o) {
			observationItems.push(E('div', {}, [
				E('h4', {}, [ labels.capabilityName(o.id) ]),
				E('p', { 'class': 'cbi-value-description' }, [ labels.observationDetail(o.detail) ]),
				pu.jsonBox(o, _('Technical details'))
			]));
		});
		if (observationItems.length)
			nodes.push(pu.card(_('Observations'), E('div', {}, observationItems)));
		((r && r.learnedAdvisory) || []).forEach(function(a) {
			const body = E('div', {}, [ pu.kv([ [_('Authority'), labels.authority(a.authority)], [_('Execution path'), a.kind === 'benchmark' ? _('Controlled benchmark') : (a.kind === 'noop' ? _('No mutation') : _('Safe direct apply'))], [_('Confidence'), labels.percent(a.confidence)] ]) ]);
			if (a.kind === 'safe-direct') {
				const apply = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Apply this Rill recommendation') ]);
				apply.addEventListener('click', function() {
					const restore = pu.setBusy(apply, _('Applying...'));
					pm.apply(a.actionId, a.applyTarget, 'rill-advisory', a.decisionId).then(function(res) {
						if (res && res.ok)
							ui.addNotification(null, E('p', {}, [ _('Rill recommendation applied and verified.') ]));
						else {
							const details = [ E('p', {}, [ _('Rill recommendation was not applied: %s. Review the safety state and try again.').format(labels.errorSummary(res)) ]) ];
							if (res) details.push(pu.jsonBox(res, _('Technical details')));
							ui.addNotification(null, E('div', {}, details), 'error');
						}
					}).catch(function(error) {
						ui.addNotification(null, E('p', {}, [ _('Unable to apply Rill recommendation: %s. Review the safety state and try again.').format(labels.errorSummary(error)) ]), 'error');
					}).finally(restore);
				});
				body.appendChild(E('div', {}, [ apply ]));
			} else if (a.kind === 'noop') {
				/* The selected-action summary already communicates the no-change
				 * outcome; avoid repeating the same sentence in a second card. */
			} else {
				body.appendChild(E('p', { 'class': 'cbi-value-description' }, [ _('This recommendation is for a performance test only. Open Performance test and complete both detection phases with the companion test tool; it cannot be applied directly.') ]));
			}
			body.appendChild(pu.jsonBox({ actionId: a.actionId, kind: a.kind, authority: a.authority, decisionId: a.decisionId }, _('Technical details')));
			const advisoryTitle = a.kind === 'noop' ? _('Rill recommendation') : _('Rill recommendation: %s').format(labels.actionName(a.actionId));
			smartBody.appendChild(E('h4', {}, [ advisoryTitle ]));
			smartBody.appendChild(body);
		});
		/* Keep the policy and grouped observations in the native-theme grid.
		 * Rill's advisory stays inside policy so it does not repeat a no-op action
		 * or leave a lone card in themes whose content column fits two cards. */
		return pu.page(_('Smart optimization'), _('Review supported actions and apply them only after Core safety checks. Existing user and external settings are preserved.'), [ pu.grid([ smartCard, ...nodes ]) ]);
	}
});
