'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.capabilities(), pm.topology() ]); },
	render: function(data) {
		const c = data[0] || {}, t = data[1] || {};
		const nodes = [ E('h2', {}, [ _('Capabilities') ]), E('p', {}, [ _('Unsupported optional capabilities are hidden from action surfaces; expected profile gaps are reported as degraded.') ]) ];
		(c.capabilities || []).forEach(function(x) {
			nodes.push(pu.card(x.id + (x.targetRef ? ' · ' + x.targetRef : ''), pu.kv([
				[_('Provider'), x.provider], [_('Availability'), x.availability], [_('Scope'), x.scope], [_('Confidence'), x.confidence], [_('Adjustable'), x.adjustable ? _('Yes') : _('No')], [_('Policy'), x.policy || '—']
			])));
		});
		nodes.push(pu.jsonBox({ capabilities: c, topology: t }, _('Capability / Topology / TargetRef JSON')));
		return E([], nodes);
	}
});
