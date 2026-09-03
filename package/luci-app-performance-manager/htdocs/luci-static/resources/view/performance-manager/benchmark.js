'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

function parseEvidence(text) {
	try { return JSON.parse(text); }
	catch (e) { throw new Error(_('Evidence must be valid JSON.')); }
}

function stageRow(stage, active) {
	return E('li', { 'class': 'pm-stage' + (active ? ' pm-stage--active' : '') }, [
		E('span', { 'class': 'pm-stage-status' }, [ active ? _('Complete') : _('Pending') ]),
		E('span', {}, [ stage ])
	]);
}

return view.extend({
	load: function() { return pm.recommendations(); },
	render: function(rec) {
		const actions = ((rec && rec.benchmarkActions) || []).filter(function(a) { return a.status !== 'blocked'; });
		const advisories = (rec && rec.learnedAdvisory) || [];
		const root = E('div');
		const action = E('select', { 'class': 'cbi-input-select', 'aria-label': _('Benchmark action') });
		actions.forEach(function(a) { action.appendChild(E('option', { value: a.id }, [ a.id + ' · ' + a.evaluationSemantics ])); });
		const pathSelect = E('select', { 'class': 'cbi-input-select', 'aria-label': _('Evaluation path') });
		function refreshPaths() {
			pathSelect.replaceChildren();
			const selected = actions.find(function(a){ return a.id === action.value; });
			((selected && selected.evaluationPaths) || []).forEach(function(p){ pathSelect.appendChild(E('option', { value: p }, [ p ])); });
		}
		action.addEventListener('change', refreshPaths);
		refreshPaths();
		const measurement = E('select', { 'class': 'cbi-input-select', 'aria-label': _('Measurement class') }, [
			E('option', { value: 'controlled_ab' }, [ _('Controlled A/B') ]),
			E('option', { value: 'passive_before_after' }, [ _('Passive before/after') ]),
			E('option', { value: 'health_only' }, [ _('Health only') ])
		]);
		const start = E('button', { 'class': 'btn cbi-button cbi-button-action', type: 'button' }, [ _('Start explicit test') ]);
		const output = E('div');

		function renderSession(res) {
			output.replaceChildren();
			if (!res || !res.ok) { output.appendChild(pu.inset(_('Blocked result'), pu.jsonBox(res || {}, _('Details')), 'warning')); return; }
			const s = res.session || {};
			const stages = E('ol', { 'class': 'pm-stage-list' }, [
				stageRow(_('Environment'), true), stageRow(_('Path'), true), stageRow(_('Compatibility'), true), stageRow(_('Locks / Failsafe'), s.state !== 'awaiting_control'),
				stageRow(_('Baseline'), !!s.controlEvidence), stageRow(_('Candidate'), s.state === 'candidate_applied' || s.state === 'completed'),
				stageRow(_('Commit-confirm'), s.state === 'candidate_applied'), stageRow(_('Result'), s.state === 'completed')
			]);
			output.appendChild(stages);
			if (s.state === 'awaiting_control' || s.state === 'candidate_applied') {
				const phase = s.state === 'awaiting_control' ? 'control' : 'candidate';
				const meta = (s.companion && s.companion.metadata) || {};
				const command = 'python3 pm_companion_agent.py client --host <WAN_SERVER> --role ' + ((s.companion && s.companion.requiredRole) || 'lan-client') +
					' --session-id ' + s.sessionId + ' --phase ' + phase + ' --action-id ' + s.actionId + ' --path-id ' + s.evaluationPath +
					' --topology-generation ' + meta.topologyGeneration + ' --route-identity ' + meta.routeIdentity + ' --capability-hash ' + meta.capabilityHash;
				const evidenceBox = E('textarea', { class: 'cbi-input-textarea', rows: 9, placeholder: _('Paste Companion JSON evidence') });
				const submitEvidence = E('button', { class: 'btn cbi-button cbi-button-positive', type: 'button' }, [ phase === 'control' ? _('Apply candidate after validating baseline') : _('Validate candidate and restore original state') ]);
				submitEvidence.addEventListener('click', function() {
					let evidence;
					try { evidence = parseEvidence(evidenceBox.value); } catch (e) { ui.addNotification(null, E('p', {}, [ e.message ])); return; }
					const restore = pu.setBusy(submitEvidence, _('Working…'));
					pm.benchmarkStart(s.actionId, s.evaluationPath, 'controlled_ab', phase, s.sessionId, evidence)
						.then(renderSession)
						.catch(function(error) { ui.addNotification(null, E('p', {}, [ error.message || error ])); })
						.finally(restore);
				});
				output.appendChild(pu.inset(phase === 'control' ? _('Baseline evidence') : _('Candidate evidence'), E('div', {}, [
					E('p', {}, [ phase === 'control' ? _('Run the Companion before any candidate is applied, then paste its JSON result.') : _('The candidate is temporarily active and protected by commit-confirm. Run the same endpoint test now; Core will restore the original value before validating the result.') ]),
					E('pre', {}, [ command ]), evidenceBox, E('div', { 'class': 'pm-toolbar' }, [ submitEvidence ])
				])));
			}
			output.appendChild(pu.jsonBox(s, _('Benchmark session JSON')));
		}

		start.addEventListener('click', function() {
			const restore = pu.setBusy(start, _('Starting…'));
			const selected = actions.find(function(a){ return a.id === action.value; });
			const path = pathSelect.value || (selected && selected.evaluationPaths && selected.evaluationPaths[0]) || 'path:lan-to-wan';
			const selectedAdvisory = advisories.find(function(a) { return a.kind === 'benchmark' && a.actionId === action.value; });
			pm.benchmarkStart(measurement.value === 'controlled_ab' ? action.value : 'observe', path, measurement.value, 'begin', null, null,
				selectedAdvisory && measurement.value === 'controlled_ab' ? 'benchmark-rill' : 'manual',
				selectedAdvisory && measurement.value === 'controlled_ab' ? selectedAdvisory.decisionId : null)
				.then(renderSession)
				.catch(function(error) { output.replaceChildren(pu.inset(_('Test could not start'), pu.note(error.message || error, 'warning'))); })
				.finally(restore);
		});

		start.disabled = !actions.length;
		root.appendChild(pu.toolbar([
			pu.field(_('Benchmark action'), action),
			pu.field(_('Evaluation path'), pathSelect),
			pu.field(_('Measurement class'), measurement),
			start
		]));
		if (!actions.length) root.appendChild(pu.note(_('No benchmark action is currently available for this device.'), 'warning'));
		root.appendChild(output);
		return pu.page(_('Performance Test'), _('Active tests are explicit, one-variable-at-a-time transactions. A controlled A/B result is validated only after context stability, health checks and verified rollback.'), [
			pu.card(_('Environment → Path → Compatibility → Locks/Failsafe → Baseline → Candidate → Commit-confirm → Result'), root),
			pu.card(_('Blocked providers'), pu.jsonBox(((rec && rec.benchmarkActions) || []).filter(function(a){ return a.status === 'blocked'; }), _('Why some benchmark actions are unavailable')), 'muted')
		]);
	}
});
