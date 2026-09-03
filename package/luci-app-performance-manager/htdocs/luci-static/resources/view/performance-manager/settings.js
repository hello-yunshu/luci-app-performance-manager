'use strict';
'require view';
'require form';
'require performance-manager.ui as pu';

return view.extend({
	render: function() {
		let m = new form.Map('performance-manager', _('Performance Manager settings'), _('Conservative automation is the supported default. Active benchmark saturation remains disabled by default.'));
		let s = m.section(form.NamedSection, 'main', 'core', _('Core'));
		let o = s.option(form.Flag, 'enabled', _('Enable Core')); o.default = o.enabled; o.description = _('Run the Performance Manager core service. Disable this to stop performance management.');
		o = s.option(form.ListValue, 'automation', _('Automation mode')); o.value('manual', _('Manual')); o.value('conservative', _('Conservative')); o.value('assisted', _('Assisted automation (opt-in; safe actions only)')); o.default = 'conservative'; o.description = _('Choose how Core responds: manual, conservative, or assisted automation.');

		o = s.option(form.Flag, 'assisted_auto', _('Enable assisted automation')); o.default=o.disabled; o.depends('automation', 'assisted'); o.description = _('Allow assisted automation to apply only actions on the safe allowlist.');
		o = s.option(form.Value, 'maintenance_start', _('Maintenance window start')); o.default='03:00'; o.depends('automation', 'assisted'); o.description = _('Assisted automation may run only within this local time window.');
		o = s.option(form.Value, 'maintenance_end', _('Maintenance window end')); o.default='05:00'; o.depends('automation', 'assisted'); o.description = _('Assisted automation may run only within this local time window.');
		o = s.option(form.Value, 'assisted_max_bytes_per_second', _('Low-traffic threshold (bytes/s)')); o.datatype='uinteger'; o.default='1048576'; o.depends('automation', 'assisted'); o.description = _('Assisted automation runs only while traffic stays below this threshold.');
		// Every goal uses controlled A/B; latency and CPU efficiency require the
		// corresponding real evidence rather than a throughput proxy.
		o = s.option(form.ListValue, 'goal', _('Goal')); [
			['balanced', _('Balanced (requires latency and CPU evidence)')],
			['throughput', _('Throughput')],
			['latency', _('Latency (requires latency evidence)')],
			['cpu_efficiency', _('CPU efficiency (requires Core CPU evidence)')]
		].forEach(function(v){ o.value(v[0], v[1]); }); o.default='balanced'; o.description = _('Select the outcome used to rank supported actions and evaluate evidence.');
		o = s.option(form.ListValue, 'profile', _('Profile')); [['minimal', _('Minimal')], ['recommended', _('Recommended')], ['performance-x86', _('Performance x86')], ['wireless', _('Wireless')], ['diagnostics', _('Diagnostics')]].forEach(function(v){ o.value(v[0], v[1]); }); o.default='recommended'; o.description = _('Load the selected configuration profile and its capability expectations.');
		o = s.option(form.Flag, 'telemetry', _('Telemetry')); o.default=o.enabled; o.description = _('Collect measurements used by health checks and decision-making.');
		o = s.option(form.Flag, 'history', _('History')); o.default=o.enabled; o.description = _('Store action and runtime events for review and rollback.');
		o = s.option(form.Flag, 'failsafe', _('Failsafe')); o.default=o.enabled; o.description = _('Protect changes with locks, health checks, and verified rollback.');
	o = s.option(form.Value, 'telemetry_interval', _('Fast telemetry interval (seconds)')); o.datatype='uinteger'; o.default='45'; o.description = _('How often to collect fast measurements.');
	o = s.option(form.Value, 'deep_interval', _('Deep telemetry interval (seconds)')); o.datatype='uinteger'; o.default='600'; o.description = _('How often to collect deeper measurements.');
	// Advanced Smart Settings remain on the Core section so older LuCI form
	// implementations render them correctly without a tab API dependency.
	let r = m.section(form.NamedSection, 'runtime', 'rill', _('Rill Runtime'));
	o = r.option(form.Flag, 'enabled', _('Enable Runtime')); o.default=o.enabled; o.description = _('Enable the optional Rill Runtime integration. Core remains the execution authority.');
	o = r.option(form.Value, 'binary', _('Generic Runtime binary')); o.default=''; o.placeholder='/usr/bin/rill-runtime'; o.description = _('Path to the external generic Rill Runtime binary.');
	o = s.option(form.Flag, 'smart_rill_auto', _('Use Rill ranking in automatic modes')); o.default=o.enabled; o.description = _('Let Rill rank Core-approved actions in automatic modes. Core still decides and executes.');
	o = s.option(form.Value, 'min_validated_samples', _('Minimum validated samples')); o.datatype='uinteger'; o.default='8'; o.description = _('Minimum validated samples before an action can be considered for automatic selection.');
	o = s.option(form.Value, 'min_confidence_conservative', _('Conservative minimum confidence')); o.datatype='ufloat'; o.default='0.65'; o.description = _('Minimum confidence required by conservative automation.');
	o = s.option(form.Value, 'min_confidence_assisted', _('Assisted minimum confidence')); o.datatype='ufloat'; o.default='0.75'; o.description = _('Minimum confidence required by assisted automation.');
	o = s.option(form.Value, 'performance_drift_threshold', _('Performance drift threshold')); o.datatype='ufloat'; o.default='0.20'; o.description = _('Pause automatic Rill decisions when measured performance drifts beyond this threshold.');
	o = s.option(form.Value, 'action_cooldown_base_seconds', _('Action cooldown (seconds)')); o.datatype='uinteger'; o.default='600'; o.description = _('Minimum time between repeated applications of the same action.');
		const rendered = m.render();
		if (rendered && typeof rendered.then === 'function') return rendered.then(function(form) {
			return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ pu.card(_('Configuration'), form, 'form') ]);
		});
		return pu.page(_('Settings'), _('Keep conservative automation as the safe default; assisted actions remain explicitly opt-in.'), [ pu.card(_('Configuration'), rendered, 'form') ]);
	}
});
