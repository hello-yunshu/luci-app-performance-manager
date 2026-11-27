'use strict';
'require view';
'require form';
'require performance-manager.ui as pu';

return view.extend({
	render: function() {
		let m = new form.Map('performance-manager', null, null);
		let s = m.section(form.NamedSection, 'main', 'core', _('Core'));
		s.tab('basic', _('Basic settings'));
		s.tab('advanced', _('Advanced settings'), _('Adjust measurement, learning and automation thresholds.'));
		let o = s.taboption('basic', form.Flag, 'enabled', _('Enable Core')); o.default = o.enabled; o.description = _('Enable the Performance Manager service.');
		o = s.taboption('basic', form.ListValue, 'automation', _('Automation mode')); o.value('manual', _('Manual')); o.value('conservative', _('Conservative')); o.value('assisted', _('Assisted automation (opt-in; safe actions only)')); o.default = 'conservative'; o.description = _('Manual mode leaves each action to you. Conservative mode applies safe actions automatically. Assisted mode also needs a separate switch, a time window and low traffic.');

		o = s.taboption('advanced', form.Flag, 'assisted_auto', _('Enable assisted automation')); o.default=o.disabled; o.depends('automation', 'assisted'); o.description = _('Allow only preset safe actions.');
		o = s.taboption('advanced', form.Value, 'maintenance_start', _('Maintenance window start')); o.default='03:00'; o.depends('automation', 'assisted'); o.description = _('Local time when assisted automation may start.');
		o = s.taboption('advanced', form.Value, 'maintenance_end', _('Maintenance window end')); o.default='05:00'; o.depends('automation', 'assisted'); o.description = _('Local time when assisted automation must stop.');
		o = s.taboption('advanced', form.Value, 'assisted_max_bytes_per_second', _('Low-traffic threshold (bytes/s)')); o.datatype='uinteger'; o.default='1048576'; o.depends('automation', 'assisted'); o.description = _('Run assisted automation only while traffic is below this limit. The default is about 1 MiB/s.');
		// Every goal uses controlled A/B; latency and CPU efficiency require the
		// corresponding real evidence rather than a throughput proxy.
		o = s.taboption('basic', form.ListValue, 'goal', _('Goal')); [
			['balanced', _('Balanced (requires latency and CPU evidence)')],
			['throughput', _('Throughput')],
			['latency', _('Latency (requires latency evidence)')],
			['cpu_efficiency', _('CPU efficiency (requires Core CPU evidence)')]
		].forEach(function(v){ o.value(v[0], v[1]); }); o.default='balanced'; o.description = _('Rank supported actions and evaluate results against this goal.');
		o = s.taboption('basic', form.ListValue, 'profile', _('Profile')); [['minimal', _('Minimal')], ['recommended', _('Recommended')], ['performance-x86', _('Performance x86')], ['wireless', _('Wireless')], ['diagnostics', _('Diagnostics')]].forEach(function(v){ o.value(v[0], v[1]); }); o.default='recommended'; o.description = _('Load this profile and its expected capabilities.');
		o = s.taboption('basic', form.Flag, 'telemetry', _('Telemetry')); o.default=o.enabled; o.description = _('Collect data for health checks and decisions.');
		o = s.taboption('basic', form.Flag, 'history', _('History')); o.default=o.enabled; o.description = _('Save events for review and rollback.');
		o = s.taboption('basic', form.Flag, 'failsafe', _('Failsafe')); o.default=o.enabled; o.description = _('Protect changes with locks, health checks and verified rollback.');
		o = s.taboption('advanced', form.Value, 'telemetry_interval', _('Fast telemetry interval (seconds)')); o.datatype='uinteger'; o.default='45'; o.description = _('How often to collect fast measurements.');
		o = s.taboption('advanced', form.Value, 'deep_interval', _('Deep telemetry interval (seconds)')); o.datatype='uinteger'; o.default='600'; o.description = _('How often to collect deeper measurements.');
	let r = m.section(form.NamedSection, 'runtime', 'rill', _('Rill Runtime'));
		o = r.option(form.Flag, 'enabled', _('Enable Runtime')); o.default=o.enabled; o.description = _('Enable Rill. Performance Manager still checks safety and applies changes.');
		o = r.option(form.Value, 'binary', _('Generic Runtime binary')); o.default=''; o.placeholder='/usr/bin/rill-runtime'; o.description = _('Path to the external Rill program.');
		o = s.taboption('advanced', form.Flag, 'smart_rill_auto', _('Use Rill ranking in automatic modes')); o.default=o.enabled; o.description = _('Let Rill rank eligible actions. Performance Manager still chooses and applies them.');
		o = s.taboption('advanced', form.Value, 'min_validated_samples', _('Minimum validated samples')); o.datatype='uinteger'; o.default='8'; o.description = _('Validated samples needed before an action can be considered automatically.');
		o = s.taboption('advanced', form.Value, 'min_confidence_conservative', _('Conservative minimum confidence (0–1 ratio)')); o.datatype='ufloat'; o.default='0.65'; o.description = _('Minimum confidence for conservative mode. 0.65 = 65%.');
		o = s.taboption('advanced', form.Value, 'min_confidence_assisted', _('Assisted minimum confidence (0–1 ratio)')); o.datatype='ufloat'; o.default='0.75'; o.description = _('Minimum confidence for assisted mode. 0.75 = 75%.');
		o = s.taboption('advanced', form.Value, 'performance_drift_threshold', _('Performance drift threshold (0–1 ratio)')); o.datatype='ufloat'; o.default='0.20'; o.description = _('Pause automatic Rill decisions when performance changes by more than this value. 0.20 = 20%.');
	o = s.taboption('advanced', form.Value, 'action_cooldown_base_seconds', _('Action cooldown (seconds)')); o.datatype='uinteger'; o.default='600'; o.description = _('Minimum time between repeated applications of the same action.');
		const rendered = m.render();
		if (rendered && typeof rendered.then === 'function') return rendered.then(function(form) {
			return pu.page(_('Settings'), _('Conservative mode is the default. Enable assisted automation separately.'), [ form ]);
		});
		return pu.page(_('Settings'), _('Conservative mode is the default. Enable assisted automation separately.'), [ rendered ]);
	}
});
