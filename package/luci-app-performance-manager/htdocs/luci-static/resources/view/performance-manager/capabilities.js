'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	load: function() { return Promise.all([ pm.capabilities(), pm.topology() ]); },
	render: function(data) {
		const c = data[0] || {}, t = data[1] || {};
		const nodes = [];
		(c.capabilities || []).forEach(function(x) {
			nodes.push(pu.card(labels.capabilityName(x.id) + (x.targetRef ? ' · ' + labels.target(x.targetRef) : ''), E('div', {}, [
				pu.badge(labels.availability(x.availability), x.availability === 'available' ? 'success' : 'warning'),
				E('p', { 'class': 'pm-control-help' }, [ labels.capabilityDesc(x.id) ]),
				pu.kv([
					[_('Provider'), labels.provider(x.provider)],
					[_('Availability'), labels.availability(x.availability)],
					[_('Scope'), labels.scope(x.scope)],
					[_('Confidence'), labels.confidence(x.confidence)],
					[_('Adjustable'), x.adjustable ? _('Yes') : _('No')],
					[_('Policy'), labels.policy(x.policy)]
				]),
				pu.jsonBox({ id: x.id, provider: x.provider, availability: x.availability, scope: x.scope, confidence: x.confidence, policy: x.policy, targetRef: x.targetRef }, _('Technical details'))
			]), 'capability'));
		});
		if (!nodes.length) nodes.push(pu.note(_('No capabilities are available from the current provider.'), 'warning'));
		return pu.page(_('Capabilities'), _('Review the capabilities available on this device. Unsupported capabilities are hidden from action controls; expected profile gaps appear as degraded.'), [
			pu.grid(nodes, 'pm-card-grid--dense'),
			pu.card(_('Capability / Topology / TargetRef JSON'), pu.jsonBox({ capabilities: c, topology: t }, _('Raw capability contract')), 'muted')
		]);
	}
});
