'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

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
					const restore = pu.setBusy(c, _('Confirming…'));
					pm.confirm(tx.transactionId).then(function(r){ ui.addNotification(null, E('p', {}, [ r && r.ok ? _('Transaction confirmed.') : _('Confirmation failed or expired. Refresh the page to check the transaction state.') ])); })
						.catch(function(error) { ui.addNotification(null, E('p', {}, [ _('Unable to confirm transaction: %s. Refresh the page and try again if it is still pending.').format(error.message || error) ]), 'error'); })
						.finally(restore);
				});
				controls.push(c);
			}
			if (!['rolled_back','failed'].includes(tx.state)) {
				const b = E('button', { 'class': 'btn cbi-button cbi-button-negative', 'type': 'button' }, [ _('Rollback') ]);
				b.addEventListener('click', function() {
					const restore = pu.setBusy(b, _('Rolling back…'));
					pm.rollback(tx.transactionId).then(function(r){ ui.addNotification(null, E('p', {}, [ r && r.ok ? _('Rollback completed and read-back verified.') : _('Rollback could not be completed. Check the transaction details before trying again.') ])); })
						.catch(function(error) { ui.addNotification(null, E('p', {}, [ _('Unable to roll back transaction: %s. Check the transaction details and try again.').format(error.message || error) ]), 'error'); })
						.finally(restore);
				});
				controls.push(b);
			}
			nodes.push(pu.card(tx.transactionId, E('div', {}, [ pu.kv([ [_('Action'), tx.actionId], [_('State'), tx.state], [_('Target'), tx.applyTarget], [_('Boot identity'), tx.bootId] ]), controls.length ? E('div', { 'class': 'pm-toolbar' }, controls) : null, pu.jsonBox(tx, _('Transaction JSON')) ]), 'transaction'));
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
