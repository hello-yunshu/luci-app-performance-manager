'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	handleSave: null,
	handleSaveApply: null,
	handleReset: null,

	load: function() {
		return pm.capabilities().catch(function(err) {
				console.error('performance-manager: capabilities load failed', err);
				return { _loadError: err };
			});
	},
	render: function(data) {
		if (data && data._loadError)
			return pu.page(_('Capabilities'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const c = data || {};
		const nodes = [];
		const nicCapabilities = [];
		(c.capabilities || []).forEach(function(x) {
			if (String(x.id || '').indexOf('nic.') === 0) {
				nicCapabilities.push(x);
				return;
			}
			nodes.push(pu.card(labels.capabilityName(x.id), E('div', {}, [
				pu.badge(labels.availability(x.availability), x.availability === 'available' ? 'success' : 'warning'),
				E('p', { 'class': 'cbi-value-description' }, [ labels.capabilityDesc(x.id) ]),
				pu.kv([
					[_('Adjustable'), x.adjustable ? _('Yes') : _('No')]
				]),
				pu.jsonBox({ id: x.id, provider: x.provider, availability: x.availability, scope: x.scope, confidence: x.confidence, policy: x.policy, targetRef: x.targetRef }, _('Provider and policy details'))
			])));
		});
		if (nicCapabilities.length)
			nodes.push(pu.card(_('Network adapter tuning'), E('div', {}, [
				E('p', { 'class': 'cbi-value-description' }, [ _('Network adapter features are grouped here to keep repeated hardware details out of the main list.') ]),
				pu.jsonBox(nicCapabilities, _('Adapter capabilities and details'))
			])));
		if (!nodes.length) nodes.push(pu.note(_('No capabilities are available from the current provider.'), 'warning'));
		return pu.page(_('Capabilities'), _('Review the capabilities available on this device. Unsupported capabilities are hidden from action controls; expected profile gaps appear as degraded.'), [
			pu.grid(nodes)
		]);
	}
});
