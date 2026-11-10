'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	load: function() { return Promise.all([ pm.transactions(), pm.locks(), pm.history(100) ]); },
	render: function(data) {
		const txs = (data[0] && data[0].transactions) || [], locks = (data[1] && data[1].locks) || [], history = (data[2] && data[2].history) || [], runtimeHistory = (data[2] && data[2].runtimeHistory) || [];
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
			nodes.push(pu.card(labels.transaction(tx.transactionId), E('div', {}, [ pu.kv([ [_('Action'), labels.actionName(tx.actionId)], [_('State'), labels.state(tx.state)], [_('Target'), labels.target(tx.applyTarget)], [_('Boot identity'), labels.reference(tx.bootId)] ]), E('p', { 'class': 'pm-control-help' }, [ _('Identifiers are kept in technical details so long UUIDs do not crowd the page.') ]), controls.length ? E('div', { 'class': 'pm-toolbar' }, controls) : null, pu.jsonBox(tx, _('Transaction JSON')) ]), 'transaction'));
		});
		if (!txs.length) nodes.push(pu.note(_('No transactions are currently recorded.'), 'success'));
		return pu.page(_('History and rollback'), _('Review pending confirmations, verified rollbacks, and runtime events with their safety context.'), [
			pu.grid(nodes, 'pm-card-grid--dense'),
			pu.grid([
				pu.card(_('Resource locks'), pu.jsonBox(locks, _('Locks JSON'))),
				pu.card(_('Persistent action history'), pu.jsonBox(history, _('History JSON'))),
				pu.card(_('Runtime event history'), pu.jsonBox(runtimeHistory, _('Runtime History JSON')))
			], 'pm-card-grid--supporting')
		]);
	}
});
