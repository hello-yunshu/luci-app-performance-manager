'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return pm.rill(); },
	render: function(r) {
		r = r || {};
		return pu.page(_('RillML (Rill) Intelligence'), _('Rill provides observation and recommendations while Core keeps the final execution authority.'), [
			pu.card(_('Shadow boundary'), pu.kv([
				[_('State'), r.status || _('Shadow · Collecting')], [_('Transport'), r.transport || '—'], [_('Mode'), _('Observe / learn / recommend only')], [_('Apply authority'), _('None')]
			]), 'hero'),
			pu.note(_('Rill cannot write UCI, sysctl or firewall state, cannot execute arbitrary shell, and cannot apply Actions.'), 'info'),
			pu.card(_('Rill details'), pu.jsonBox(r.detail || r, _('Raw Rill contract')), 'muted')
		]);
	}
});
