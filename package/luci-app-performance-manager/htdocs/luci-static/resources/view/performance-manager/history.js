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
				c.addEventListener('click', function() { pm.confirm(tx.transactionId).then(function(r){ ui.addNotification(null, E('p', {}, [ r && r.ok ? _('Transaction confirmed.') : _('Confirmation failed or expired.') ])); }); });
				controls.push(c);
			}
			if (!['rolled_back','failed'].includes(tx.state)) {
				const b = E('button', { 'class': 'btn cbi-button cbi-button-negative', 'type': 'button' }, [ _('Rollback') ]);
				b.addEventListener('click', function() { pm.rollback(tx.transactionId).then(function(r){ ui.addNotification(null, E('p', {}, [ r && r.ok ? _('Rollback completed and read-back verified.') : _('Rollback could not be completed; inspect the transaction.') ])); }); });
				controls.push(b);
			}
			nodes.push(pu.card(tx.transactionId, E('div', {}, [ pu.kv([ [_('Action'), tx.actionId], [_('State'), tx.state], [_('Target'), tx.applyTarget], [_('Boot identity'), tx.bootId] ]), controls.length ? E('div', { 'class': 'pm-toolbar' }, controls) : null, pu.jsonBox(tx, _('Transaction JSON')) ])));
		});
		if (!txs.length) nodes.push(pu.note(_('No transactions are currently recorded.'), 'success'));
		return pu.page(_('History & Rollback'), _('Review pending confirmations, verified rollbacks, and the runtime record without losing the safety context.'), [
			pu.grid(nodes),
			pu.grid([
				pu.card(_('Resource locks'), pu.jsonBox(locks, _('Locks JSON'))),
				pu.card(_('Persistent action history'), pu.jsonBox(history, _('History JSON'))),
				pu.card(_('Runtime event history'), pu.jsonBox(runtimeHistory, _('Runtime History JSON')))
			])
		]);
	}
});
