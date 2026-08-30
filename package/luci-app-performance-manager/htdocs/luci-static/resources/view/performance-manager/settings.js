'use strict';
'require view';
'require form';
'require performance-manager.ui as pu';

return view.extend({
	render: function() {
		let m = new form.Map('performance-manager', _('Performance Manager Settings'), _('Conservative automation is the supported default. Active benchmark saturation remains disabled by default.'));
		let s = m.section(form.NamedSection, 'main', 'core', _('Core'));
		let o = s.option(form.Flag, 'enabled', _('Enable Core')); o.default = o.enabled;
		o = s.option(form.ListValue, 'automation', _('Automation')); o.value('manual', _('Manual')); o.value('conservative', _('Conservative')); o.value('assisted', _('Assisted Auto (opt-in, safe actions only)')); o.default = 'conservative';

		o = s.option(form.Flag, 'assisted_auto', _('Enable Assisted Auto')); o.default=o.disabled; o.depends('automation', 'assisted');
		o = s.option(form.Value, 'maintenance_start', _('Maintenance window start')); o.default='03:00'; o.depends('automation', 'assisted');
		o = s.option(form.Value, 'maintenance_end', _('Maintenance window end')); o.default='05:00'; o.depends('automation', 'assisted');
		o = s.option(form.Value, 'assisted_max_bytes_per_second', _('Low-traffic threshold (bytes/s)')); o.datatype='uinteger'; o.default='1048576'; o.depends('automation', 'assisted');
		// Goal semantics are honest: balanced/throughput are measurable for
		// controlled A/B; latency/cpu_efficiency are valid end-state goals but
		// the Core fails closed (goal-unsupported-for-controlled-ab) for
		// controlled A/B under them, so the UI marks them as such up front.
		o = s.option(form.ListValue, 'goal', _('Goal')); [
			['balanced', _('Balanced (measurable for A/B)')],
			['throughput', _('Throughput (measurable for A/B)')],
			['latency', _('Latency (not measurable for A/B)')],
			['cpu_efficiency', _('CPU efficiency (not measurable for A/B)')]
		].forEach(function(v){ o.value(v[0], v[1]); }); o.default='balanced';
		o = s.option(form.ListValue, 'profile', _('Profile')); ['minimal','recommended','performance-x86','wireless','diagnostics'].forEach(function(v){ o.value(v, v); }); o.default='recommended';
		o = s.option(form.Flag, 'telemetry', _('Telemetry')); o.default=o.enabled;
		o = s.option(form.Flag, 'history', _('History')); o.default=o.enabled;
		o = s.option(form.Flag, 'failsafe', _('Failsafe')); o.default=o.enabled;
		o = s.option(form.Value, 'telemetry_interval', _('Fast telemetry interval (seconds)')); o.datatype='uinteger'; o.default='45';
		o = s.option(form.Value, 'deep_interval', _('Deep telemetry interval (seconds)')); o.datatype='uinteger'; o.default='600';
		let r = m.section(form.NamedSection, 'shadow', 'rill', _('Rill Shadow'));
		o = r.option(form.Flag, 'enabled', _('Enable Shadow')); o.default=o.enabled;
		o = r.option(form.Value, 'socket', _('Unix socket')); o.default='/run/performance-manager/rill.sock'; o.readonly=true;
		const rendered = m.render();
		if (rendered && typeof rendered.then === 'function') return rendered.then(function(form) {
			return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ form ]);
		});
		return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ rendered ]);
	}
});
