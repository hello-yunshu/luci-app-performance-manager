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
		return Promise.all([ pm.status(), pm.resources() ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: advanced load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(data) {
		if ((data || []).some(function(d) { return d && d._loadError; }))
			return pu.page(_('Advanced'), null, pu.note(_('Unable to load this page. Retry; if it keeps failing, check the service log.'), 'danger'));
		const s = data[0] || {}, resources = (data[1] && data[1].resources) || {};
		const profile = s.profile || {};
		const diagnosticOutput = E('div', {}, [ _('Expand to load detailed capability, topology, transaction and lock records.') ]);
		const diagnostics = E('details', { 'class': 'pm-disclosure' }, [
			E('summary', {}, [ _('Detailed diagnostics') ]),
			diagnosticOutput
		]);
		let diagnosticsLoaded = false;
		diagnostics.addEventListener('toggle', function() {
			if (!diagnostics.open || diagnosticsLoaded) return;
			diagnosticsLoaded = true;
			diagnosticOutput.replaceChildren(_('Loading diagnostics…'));
			Promise.all([ pm.capabilities(), pm.topology(), pm.recommendations(), pm.transactions(), pm.locks() ])
				.then(function(records) {
					diagnosticOutput.replaceChildren(E('pre', {}, [ JSON.stringify({
						capabilities: records[0], topology: records[1], recommendations: records[2],
						transactions: records[3], locks: records[4]
					}, null, 2) ]));
				})
				.catch(function(error) {
					diagnosticOutput.replaceChildren(E('p', { 'class': 'alert-message warning', 'role': 'status' }, [
						_('Unable to load diagnostic records: %s').format(error.message || error)
					]));
					diagnosticsLoaded = false;
				});
		});
		return pu.page(_('Advanced'), _('View diagnostic data and resource use.'), [
			pu.grid([
				pu.card(_('Runtime and profile'), E('div', {}, [
					pu.kv([
						[_('Service'), s.running ? _('Running') : _('Stopped')],
						[_('System profile'), profile.healthy ? (profile.degraded ? _('Degraded') : _('Healthy')) : _('Needs attention')],
						[_('Health guard'), (s.healthGuard || {}).pass ? _('Passed') : _('Blocked')],
						[_('Automation mode'), s.automation ? labels.automation(s.automation) : _('Not reported')]
					]),
					pu.jsonBox({ profile: profile, healthGuard: s.healthGuard || {} }, _('Technical details'))
				])),
				pu.card(_('Resource usage'), E('div', {}, [
					pu.kv([
						[_('Core memory'), resources.coreVmRssKiB == null ? '—' : resources.coreVmRssKiB + ' KiB'],
						[_('Stored history'), resources.persistentHistoryBytes == null ? '—' : resources.persistentHistoryBytes + ' B'],
						[_('Active Rill operations'), resources.rillExecutionHealth && resources.rillExecutionHealth.active != null ? resources.rillExecutionHealth.active : 0]
					]),
					pu.jsonBox(resources, _('Technical details'))
				]))
			]),
			pu.card(_('Diagnostic records'), diagnostics)
		]);
	}
});
