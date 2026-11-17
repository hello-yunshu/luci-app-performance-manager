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
		return Promise.all([ pm.rill(), pm.recommendations() ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: rill load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(payload) {
		if ((payload || []).some(function(d) { return d && d._loadError; }))
			return pu.page(_('Rill smart decisions'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const r = (payload && payload[0]) || {}, rec = (payload && payload[1]) || {}, s = rec.smartSelection || {};
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
		const table = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [ E('caption', { 'class': 'pm-visually-hidden' }, [ _('Ranking table') ]), E('thead', {}, [ E('tr', { 'class': 'tr cbi-section-table-titles' }, [ E('th', { 'class': 'th' }, [ _('Rank') ]), E('th', { 'class': 'th' }, [ _('Candidate') ]), E('th', { 'class': 'th' }, [ _('Score') ]), E('th', { 'class': 'th' }, [ _('Eligibility') ]), E('th', { 'class': 'th' }, [ _('Cooldown') ]) ]) ]), E('tbody', {}, rows) ]) ]);
		const rankingActions = pu.toolbar([ refresh ]);
		const context = s.context || {};
		const feedbackOutput = E('div', {}, [ _('Expand to load recent validated feedback.') ]);
		const feedbackDetails = E('details', { 'class': 'pm-disclosure' }, [
			E('summary', {}, [ _('Show recent validated feedback') ]),
			feedbackOutput
		]);
		let feedbackLoaded = false;
		feedbackDetails.addEventListener('toggle', function() {
			if (!feedbackDetails.open || feedbackLoaded) return;
			feedbackLoaded = true;
			feedbackOutput.replaceChildren(_('Loading feedback…'));
			pm.rillFeedback(5).then(function(result) {
				const feedback = ((result && result.feedback) || []).slice().reverse();
				const feedbackRows = feedback.length ? feedback.map(function(row) {
					const d = row.data || {};
					return E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td', 'data-title': _('Candidate') }, [ labels.actionName(d.actionId) ]),
						E('td', { 'class': 'td', 'data-title': _('Goal') }, [ labels.goal(d.goal || s.goal) ]),
						E('td', { 'class': 'td', 'data-title': _('Reward') }, [ labels.percent(d.reward) ]),
						E('td', { 'class': 'td', 'data-title': _('Quality') }, [ labels.measurementQuality(d.measurementQuality) ]),
						E('td', { 'class': 'td', 'data-title': _('Result') }, [ d.accepted === true ? _('Accepted') : _('Reconciled') ])
					]);
				}) : [ E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'colspan': '5', 'data-title': _('Candidate') }, [ _('No validated feedback yet.') ]) ]) ];
				const feedbackTable = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [
					E('caption', { 'class': 'pm-visually-hidden' }, [ _('Feedback table') ]),
					E('thead', {}, [ E('tr', { 'class': 'tr cbi-section-table-titles' }, [
						E('th', { 'class': 'th' }, [ _('Candidate') ]), E('th', { 'class': 'th' }, [ _('Goal') ]),
						E('th', { 'class': 'th' }, [ _('Reward') ]), E('th', { 'class': 'th' }, [ _('Quality') ]),
						E('th', { 'class': 'th' }, [ _('Result') ])
					]) ]),
					E('tbody', {}, feedbackRows)
				]) ]);
				feedbackOutput.replaceChildren(feedbackTable);
			}).catch(function(error) {
				feedbackOutput.replaceChildren(E('p', { 'class': 'alert-message warning', 'role': 'status' }, [
					_('Unable to load feedback records: %s').format(error.message || error)
				]));
				feedbackLoaded = false;
			});
		});
		const outcomeText = s.lastOutcome
			? _('Reward %s · %s').format(labels.percent(s.lastOutcome.reward), labels.measurementQuality(s.lastOutcome.measurementQuality))
			: '—';
		const candidateHistory = s.candidateHistory || {};
		const rillUnavailable = !!r.state && r.state !== 'available' && r.state !== 'learning';
		const eligible = rillUnavailable ? _('Rill unavailable') : (s.autoEligible === true ? _('Ready') : (s.autoEligible === false ? _('Paused') : _('Not evaluated')));
		const decisionReason = s.reason ? labels.smartReason(s.reason) : (s.selectedActionId === 'pm.noop' ? _('The current configuration meets the policy.') : _('No decision reason is available yet.'));
		return pu.page(_('Rill smart decisions'), _('Rill ranks actions that passed the Core engine review; the Core engine keeps the final authority to execute them.'), [
			pu.card(_('Current decision'), E('div', {}, [
				pu.badge(labels.runtimeStatus(r.status)),
				pu.kv([
					[_('Selected action'), labels.actionName(s.selectedActionId)],
					[_('Automatic action'), eligible],
					[_('Confidence'), labels.percent(s.confidence)],
					[_('Learning stage'), labels.learningStage(s.learningStage)],
					[_('Last outcome'), outcomeText],
					[_('Why'), decisionReason]
				])
			])),
			(s.drifted ? pu.note(_('Performance drift detected. Rill Auto temporarily paused.'), 'warning') : null),
			pu.note(_('Rill provides observations and recommendations. Core checks safety and keeps final control over every change.'), 'info'),
			pu.grid([
				pu.card(_('Top ranking'), E('div', {}, [ rankingActions, pu.tableWrap(table) ])),
				pu.card(_('Recent feedback'), feedbackDetails)
			]),
			pu.card(_('Advanced details'), pu.jsonBox({
				runtime: r,
				context: context,
				selection: s,
				candidateHistory: candidateHistory,
				advisory: rec.learnedAdvisory || []
			}, _('Runtime, decision and candidate details')))
		]);
	}
});
