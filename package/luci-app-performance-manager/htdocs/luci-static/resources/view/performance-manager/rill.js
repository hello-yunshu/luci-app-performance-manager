'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return pm.rill(); },
	render: function(r) {
		r = r || {};
		return E([], [
			E('h2', {}, [ _('RillML (Rill) Intelligence') ]),
			pu.card(_('Shadow boundary'), pu.kv([
				[_('State'), r.status || _('Shadow · Collecting')], [_('Transport'), r.transport || '—'], [_('Mode'), _('Observe / learn / recommend only')], [_('Apply authority'), _('None')]
			])),
			E('p', {}, [ _('Rill cannot write UCI, sysctl or firewall state, cannot execute arbitrary shell, and cannot apply Actions.') ]),
			pu.jsonBox(r.detail || r, _('Rill details'))
		]);
	}
});
