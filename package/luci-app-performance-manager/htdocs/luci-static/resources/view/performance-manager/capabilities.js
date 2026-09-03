'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.capabilities(), pm.topology() ]); },
	render: function(data) {
		const c = data[0] || {}, t = data[1] || {};
		const nodes = [];
		(c.capabilities || []).forEach(function(x) {
			nodes.push(pu.card(x.id + (x.targetRef ? ' · ' + x.targetRef : ''), E('div', {}, [
				pu.badge(x.availability || _('Unknown'), x.availability === 'available' ? 'success' : 'warning'),
				pu.kv([
				[_('Provider'), x.provider], [_('Availability'), x.availability], [_('Scope'), x.scope], [_('Confidence'), x.confidence], [_('Adjustable'), x.adjustable ? _('Yes') : _('No')], [_('Policy'), x.policy || '—']
				])
			]), 'capability'));
		});
		if (!nodes.length) nodes.push(pu.note(_('No capabilities were reported by the current provider.'), 'warning'));
		return pu.page(_('Capabilities'), _('Unsupported optional capabilities are hidden from action surfaces; expected profile gaps are reported as degraded.'), [
			pu.grid(nodes, 'pm-card-grid--dense'),
			pu.card(_('Capability / Topology / TargetRef JSON'), pu.jsonBox({ capabilities: c, topology: t }, _('Raw capability contract')), 'muted')
		]);
	}
});
