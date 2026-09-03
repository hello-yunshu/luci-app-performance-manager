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
		// Every goal uses controlled A/B; latency and CPU efficiency require the
		// corresponding real evidence rather than a throughput proxy.
		o = s.option(form.ListValue, 'goal', _('Goal')); [
			['balanced', _('Balanced (requires latency and CPU evidence)')],
			['throughput', _('Throughput')],
			['latency', _('Latency (requires latency evidence)')],
			['cpu_efficiency', _('CPU efficiency (requires Core CPU evidence)')]
		].forEach(function(v){ o.value(v[0], v[1]); }); o.default='balanced';
		o = s.option(form.ListValue, 'profile', _('Profile')); ['minimal','recommended','performance-x86','wireless','diagnostics'].forEach(function(v){ o.value(v, v); }); o.default='recommended';
		o = s.option(form.Flag, 'telemetry', _('Telemetry')); o.default=o.enabled;
		o = s.option(form.Flag, 'history', _('History')); o.default=o.enabled;
		o = s.option(form.Flag, 'failsafe', _('Failsafe')); o.default=o.enabled;
	o = s.option(form.Value, 'telemetry_interval', _('Fast telemetry interval (seconds)')); o.datatype='uinteger'; o.default='45';
	o = s.option(form.Value, 'deep_interval', _('Deep telemetry interval (seconds)')); o.datatype='uinteger'; o.default='600';
	// Advanced Smart Settings remain on the Core section so older LuCI form
	// implementations render them correctly without a tab API dependency.
	let r = m.section(form.NamedSection, 'runtime', 'rill', _('Rill Runtime'));
	o = r.option(form.Flag, 'enabled', _('Enable Runtime')); o.default=o.enabled;
	o = r.option(form.Value, 'binary', _('Generic Runtime binary')); o.default=''; o.placeholder='/usr/bin/rill-runtime';
	o = s.option(form.Flag, 'smart_rill_auto', _('Allow Rill ranking in Auto')); o.default=o.enabled;
	o = s.option(form.Value, 'min_validated_samples', _('Minimum validated samples')); o.datatype='uinteger'; o.default='8';
	o = s.option(form.Value, 'min_confidence_conservative', _('Conservative minimum confidence')); o.datatype='ufloat'; o.default='0.65';
	o = s.option(form.Value, 'min_confidence_assisted', _('Assisted minimum confidence')); o.datatype='ufloat'; o.default='0.75';
	o = s.option(form.Value, 'performance_drift_threshold', _('Performance drift threshold')); o.datatype='ufloat'; o.default='0.20';
	o = s.option(form.Value, 'action_cooldown_base_seconds', _('Action cooldown (seconds)')); o.datatype='uinteger'; o.default='600';
		const rendered = m.render();
		if (rendered && typeof rendered.then === 'function') return rendered.then(function(form) {
			return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ form ]);
		});
		return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ rendered ]);
	}
});
