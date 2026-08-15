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
	return pu.badge(stage, active ? 'success' : '');
}

return view.extend({
	load: function() { return pm.recommendations(); },
	render: function(rec) {
		const actions = ((rec && rec.benchmarkActions) || []).filter(function(a) { return a.status !== 'blocked'; });
		const root = E('div');
		const action = E('select', { 'class': 'cbi-input-select', 'aria-label': _('Benchmark action') });
		actions.forEach(function(a) { action.appendChild(E('option', { value: a.id }, [ a.id + ' · ' + a.evaluationSemantics ])); });
		const pathSelect = E('select', { 'class': 'cbi-input-select', 'style': 'margin-left:.5rem', 'aria-label': _('Evaluation path') });
		function refreshPaths() {
			pathSelect.replaceChildren();
			const selected = actions.find(function(a){ return a.id === action.value; });
			((selected && selected.evaluationPaths) || []).forEach(function(p){ pathSelect.appendChild(E('option', { value: p }, [ p ])); });
		}
		action.addEventListener('change', refreshPaths);
		refreshPaths();
		const measurement = E('select', { 'class': 'cbi-input-select', 'style': 'margin-left:.5rem', 'aria-label': _('Measurement class') }, [
			E('option', { value: 'controlled_ab' }, [ _('Controlled A/B') ]),
			E('option', { value: 'passive_before_after' }, [ _('Passive before/after') ]),
			E('option', { value: 'health_only' }, [ _('Health only') ])
		]);
		const start = E('button', { 'class': 'btn cbi-button cbi-button-action', type: 'button', style: 'margin-left:.5rem' }, [ _('Start explicit test') ]);
		const output = E('div');

		function renderSession(res) {
			output.replaceChildren();
			if (!res || !res.ok) { output.appendChild(pu.jsonBox(res || {}, _('Blocked result'))); return; }
			const s = res.session || {};
			const stages = E('div', { style: 'margin:.7rem 0' }, [
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
				const evidenceBox = E('textarea', { class: 'cbi-input-textarea', rows: 9, style: 'width:100%', placeholder: _('Paste Companion JSON evidence') });
				const submitEvidence = E('button', { class: 'btn cbi-button cbi-button-positive', type: 'button', style: 'margin-top:.5rem' }, [ phase === 'control' ? _('Apply candidate after validating baseline') : _('Validate candidate and restore original state') ]);
				submitEvidence.addEventListener('click', function() {
					let evidence;
					try { evidence = parseEvidence(evidenceBox.value); } catch (e) { ui.addNotification(null, E('p', {}, [ e.message ])); return; }
					submitEvidence.disabled = true;
					pm.benchmarkStart(s.actionId, s.evaluationPath, 'controlled_ab', phase, s.sessionId, evidence).then(renderSession).finally(function(){ submitEvidence.disabled=false; });
				});
				output.appendChild(pu.card(phase === 'control' ? _('Baseline evidence') : _('Candidate evidence'), E('div', {}, [
					E('p', {}, [ phase === 'control' ? _('Run the Companion before any candidate is applied, then paste its JSON result.') : _('The candidate is temporarily active and protected by commit-confirm. Run the same endpoint test now; Core will restore the original value before validating the result.') ]),
					E('pre', { style: 'white-space:pre-wrap;overflow:auto' }, [ command ]), evidenceBox, submitEvidence
				])));
			}
			output.appendChild(pu.jsonBox(s, _('Benchmark session JSON')));
		}

		start.addEventListener('click', function() {
			start.disabled = true;
			const selected = actions.find(function(a){ return a.id === action.value; });
			const path = pathSelect.value || (selected && selected.evaluationPaths && selected.evaluationPaths[0]) || 'path:lan-to-wan';
			pm.benchmarkStart(measurement.value === 'controlled_ab' ? action.value : 'observe', path, measurement.value, 'begin', null, null)
				.then(renderSession).finally(function(){ start.disabled=false; });
		});

		root.appendChild(E('div', {}, [ action, pathSelect, measurement, start ]));
		root.appendChild(output);
		return E([], [
			E('h2', {}, [ _('Performance Test') ]),
			E('p', {}, [ _('Active tests are explicit, one-variable-at-a-time transactions. A controlled A/B result is validated only after context stability, health checks and verified rollback.') ]),
			pu.card(_('Environment → Path → Compatibility → Locks/Failsafe → Baseline → Candidate → Commit-confirm → Result'), root),
			pu.card(_('Blocked providers'), pu.jsonBox(((rec && rec.benchmarkActions) || []).filter(function(a){ return a.status === 'blocked'; }), _('Why some benchmark actions are unavailable')))
		]);
	}
});
