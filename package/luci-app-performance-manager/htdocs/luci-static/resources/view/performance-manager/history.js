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
		return Promise.all([ pm.transactions(), pm.locks() ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: history load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(data) {
		if ((data || []).some(function(d) { return d && d._loadError; }))
			return pu.page(_('History and rollback'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const txs = (data[0] && data[0].transactions) || [], locks = (data[1] && data[1].locks) || [];
		const historyOutput = E('div', {}, [ _('Expand to view recent history summaries.') ]);
		const historyDetails = E('details', { 'class': 'pm-disclosure' }, [
			E('summary', {}, [ _('Locks and event records') ]),
			historyOutput
		]);
		let historyLoaded = false;
		historyDetails.addEventListener('toggle', function() {
			if (!historyDetails.open || historyLoaded) return;
			historyLoaded = true;
			historyOutput.replaceChildren(_('Loading history…'));
			pm.historySummary(50).then(function(result) {
				historyOutput.replaceChildren(E('pre', {}, [ JSON.stringify({
					resourceLocks: (result && result.resourceLocks) || locks,
					actionHistory: (result && result.actionHistory) || [],
					runtimeHistory: (result && result.runtimeHistory) || []
				}, null, 2) ]));
			}).catch(function(error) {
				historyOutput.replaceChildren(E('p', { 'class': 'alert-message warning', 'role': 'status' }, [
					_('Unable to load history records: %s').format(error.message || error)
				]));
				historyLoaded = false;
			});
		});
		const nodes = [];
		txs.forEach(function(tx) {
			const controls = [];
			if (tx.state === 'awaiting_confirm') {
				const c = E('button', { 'class': 'btn cbi-button cbi-button-positive', 'type': 'button' }, [ _('Confirm') ]);
				c.addEventListener('click', function() {
					const restore = pu.setBusy(c, _('Confirming...'));
					pm.confirm(tx.transactionId).then(function(r){
						if (r && r.ok)
							ui.addNotification(null, E('p', {}, [ _('Transaction confirmed.') ]));
						else
							ui.addNotification(null, E('div', {}, [
								E('p', {}, [ _('Confirmation failed: %s. Refresh the page to check the transaction state.').format(labels.errorSummary(r)) ]),
								r ? pu.jsonBox(r, _('Technical details')) : null
							]), 'error');
					})
						.catch(function(error) { ui.addNotification(null, E('p', {}, [ _('Unable to confirm transaction: %s. Refresh the page and try again if it is still pending.').format(labels.errorSummary(error)) ]), 'error'); })
						.finally(restore);
				});
				controls.push(c);
			}
			if (!['rolled_back','failed'].includes(tx.state)) {
				const b = E('button', { 'class': 'btn cbi-button cbi-button-negative', 'type': 'button' }, [ _('Rollback') ]);
				b.addEventListener('click', function() {
					const restore = pu.setBusy(b, _('Rolling back...'));
					pm.rollback(tx.transactionId).then(function(r){
						if (r && r.ok)
							ui.addNotification(null, E('p', {}, [ _('Rollback completed and read-back verified.') ]));
						else
							ui.addNotification(null, E('div', {}, [
								E('p', {}, [ _('Rollback could not be completed: %s. Check the transaction details before trying again.').format(labels.errorSummary(r)) ]),
								r ? pu.jsonBox(r, _('Technical details')) : null
							]), 'error');
					})
						.catch(function(error) { ui.addNotification(null, E('p', {}, [ _('Unable to roll back transaction: %s. Check the transaction details and try again.').format(labels.errorSummary(error)) ]), 'error'); })
						.finally(restore);
				});
				controls.push(b);
			}
			const body = [ pu.kv([ [_('Action'), labels.actionName(tx.actionId)], [_('State'), labels.state(tx.state)], [_('Target'), labels.target(tx.applyTarget)] ]) ];
			if (controls.length)
				body.push(E('div', { 'class': 'ys-actions' }, controls));
			body.push(pu.jsonBox(tx, _('Transaction details')));
			nodes.push(pu.card(labels.transaction(tx.transactionId), E('div', {}, body)));
		});
		if (!txs.length) nodes.push(pu.note(_('No transactions are currently recorded.'), 'success'));
		return pu.page(_('History and rollback'), _('Review pending confirmations, verified rollbacks, and runtime events with their safety context.'), [
			pu.grid(nodes),
			pu.card(_('Advanced history details'), historyDetails)
		]);
	}
});
