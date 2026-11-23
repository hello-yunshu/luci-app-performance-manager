'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

return view.extend({
	handleSave: null,
	handleSaveApply: null,
	handleReset: null,

	load: function() {
		return Promise.all([ pm.rill(), pm.recommendations(), pm.runtimeManagerStatus() ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: Rill status load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(payload) {
		if ((payload || []).slice(0, 2).some(function(d) { return d && d._loadError; }))
			return pu.page(_('Rill smart decisions'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const r = (payload && payload[0]) || {}, rec = (payload && payload[1]) || {}, manager = (payload && payload[2]) || {}, s = rec.smartSelection || {};
		const refresh = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button' }, [ _('Refresh Rill decision') ]);
		refresh.addEventListener('click', function() {
			const restore = pu.setBusy(refresh, _('Refreshing...'));
			pm.rillRefresh().then(function(result) {
				if (result && result.ok === false)
					throw new Error(result.reason || result.state || _('Unable to refresh Rill.'));
				if (typeof window !== 'undefined') window.location.reload();
			}).catch(function(error) {
				ui.addNotification(null, E('p', {}, [ _('Unable to refresh Rill: %s. Try again.').format(labels.errorSummary(error)) ]), 'error');
			}).finally(restore);
		});
		function managerAction(action, packageName, button) {
			const restore = pu.setBusy(button, _('Working...'));
			const call = action === 'install'
				? pm.runtimeManagerInstall(packageName)
				: (action === 'repair' ? pm.runtimeManagerRepair(packageName) : (action === 'refresh' ? pm.runtimeManagerRefresh() : pm.runtimeManagerUpdate(packageName)));
			call.then(function(result) {
				if (!result || result.ok !== true)
					throw new Error((result && (result.message || result.errorCode)) || _('Unable to manage packages.'));
				if (typeof window !== 'undefined') window.location.reload();
			}).catch(function(error) {
				ui.addNotification(null, E('p', {}, [ _('Package operation failed: %s').format(labels.errorSummary(error)) ]), 'error');
			}).finally(restore);
		}
		const managerAvailable = manager && manager.ok === true && !manager._loadError;
		const managerSupportsDevice = managerAvailable && manager.supported !== false;
		const managerBusy = manager && manager.busy === true;
		const legacyPreviewConflict = managerAvailable && (manager.channel === 'legacy-preview' || manager.channel === 'preview' || manager.package === 'rill-runtime-preview' || manager.legacyPreviewInstalled === true);
		/* The shared rill-runtime-manager parses the installed package metadata
		 * itself, so a failed parse (for example `apk info -v` printing the
		 * package description instead of `name-version` on apk 3.x) makes it
		 * report the Runtime as incompatible even though the Runtime answered
		 * PM's own version handshake. The handshake is the authoritative
		 * signal: a disagreement must neither raise the conflict banner nor
		 * block Runtime package management. Legacy Preview ownership and
		 * unknown ownership remain real conflicts. */
		const managerIncompatible = manager.installed === true && manager.compatible === false;
		const handshakeCompatible = r.compatibility === 'compatible';
		const managerVerdictOverridden = managerAvailable && managerIncompatible && handshakeCompatible;
		if (managerVerdictOverridden && typeof console !== 'undefined' && console.warn)
			console.warn('performance-manager: rill-runtime-manager reports the Runtime as incompatible while the Runtime handshake succeeded; the handshake verdict is used');
		/* A parsed version is short and starts with a digit. The manager can
		 * hand back a whole package description when its parse failed; never
		 * print that into the details table. */
		const managerVersion = (typeof manager.version === 'string' && /^[0-9][0-9A-Za-z.+~_-]*$/.test(manager.version) && manager.version.length <= 40) ? manager.version : null;
		const runtimeConflict = managerAvailable && (legacyPreviewConflict || manager.channel === 'unknown' || (managerIncompatible && !managerVerdictOverridden));
		const packageActions = [];
		const checkPackages = E('button', { 'class': 'btn cbi-button', 'type': 'button', 'disabled': managerSupportsDevice && !managerBusy ? null : '' }, [ _('Check for updates') ]);
		checkPackages.addEventListener('click', function() { managerAction('refresh', null, checkPackages); });
		packageActions.push(checkPackages);
		if (managerAvailable && manager.supported === true && manager.installed !== true && !runtimeConflict) {
			const installRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Install Rill Runtime') ]);
			installRuntime.addEventListener('click', function() { managerAction('install', 'rill-runtime', installRuntime); });
			packageActions.push(installRuntime);
		}
		if (managerAvailable && manager.supported === true && manager.runtimeUpdateAvailable === true && !runtimeConflict) {
			const updateRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Update Rill Runtime') ]);
			updateRuntime.addEventListener('click', function() { managerAction('update', 'rill-runtime', updateRuntime); });
			packageActions.push(updateRuntime);
		}
		if (managerAvailable && manager.repairAvailable === true && !runtimeConflict) {
			const repairRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Repair Rill Runtime') ]);
			repairRuntime.addEventListener('click', function() { managerAction('repair', 'rill-runtime', repairRuntime); });
			packageActions.push(repairRuntime);
		}
		if (managerAvailable && manager.pmUpdateAvailable === true) {
			const updatePm = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Update Performance Manager') ]);
			updatePm.addEventListener('click', function() { managerAction('update', 'luci-app-performance-manager-all', updatePm); });
			packageActions.push(updatePm);
		}
		const packageToolbar = pu.toolbar(packageActions);
		packageToolbar.classList.add('pm-rill-ranking-actions');
		let packageStatus = null;
		if (!managerAvailable)
			packageStatus = pu.note(_('Package manager controls are unavailable. Update Performance Manager from the unified feed to enable them.'), 'warning');
		else if (manager.supported === false)
			packageStatus = pu.note(_('Rill Runtime is not available for this OpenWrt release and architecture.'), 'warning');
		else if (runtimeConflict) {
			if (legacyPreviewConflict) {
				const migration = E('div', {}, [
					E('p', {}, [ _('The installed owner is rill-runtime-preview, version %s. PM will not remove or replace it automatically.').format(managerVersion || _('Unknown')) ]),
					E('p', {}, [ _('Back up /etc/config/performance-manager and /etc/performance-manager/. Check for other packages that use rill-runtime-preview before continuing.') ]),
					E('pre', {}, [ 'cp -a /etc/config/performance-manager /root/performance-manager.config.backup\ntar -czf /root/performance-manager-data.backup.tgz /etc/performance-manager\n\n# OpenWrt 24.10 (opkg)\nopkg remove luci-app-performance-manager-all rill-runtime-preview\nopkg update\nopkg install luci-app-performance-manager-all\n\n# OpenWrt 25.12 (apk)\napk del luci-app-performance-manager-all rill-runtime-preview\napk update\napk add luci-app-performance-manager-all' ])
				]);
				packageStatus = pu.note(migration, 'warning');
			}
			else
				packageStatus = pu.note(_('An incompatible Rill Runtime is installed. Resolve that package conflict before changing Runtime packages.'), 'warning');
		}
		else if (manager.installed !== true)
			packageStatus = pu.note(_('Rill Runtime is not installed. Install it to enable Rill decisions.'), 'warning');
		const packageDetails = managerAvailable ? pu.kv([
			[_('OpenWrt release'), manager.release || _('Unknown')],
			[_('Package architecture'), manager.architecture || _('Unknown')],
			[_('Runtime package'), manager.installed === true ? (legacyPreviewConflict ? 'rill-runtime-preview' : (manager.package || 'rill-runtime')) : 'rill-runtime'],
			[_('Runtime version'), managerVersion || (manager.installed === true ? _('Unknown') : _('Not installed'))],
			[_('Runtime channel'), manager.channel || _('Unknown')],
			[_('Runtime compatibility'), (managerVerdictOverridden || manager.compatible === true) ? _('Compatible') : (manager.compatible === false ? _('Needs attention') : _('Unknown'))]
		]) : null;
		const ranking = (s.ranking || []).slice(0, 5);
		const rows = ranking.length ? ranking.map(function(row, i) {
				const blocked = (s.blockedReasons || []).find(function(item) { return item.actionId === row.actionId; });
				return E('tr', { 'class': 'tr', 'aria-current': row.actionId === s.selectedCandidateId ? 'true' : 'false' }, [ E('td', { 'class': 'td', 'data-title': _('Rank') }, [ String(i + 1) ]), E('td', { 'class': 'td', 'data-title': _('Candidate') }, [ labels.actionName(row.actionId) ]), E('td', { 'class': 'td', 'data-title': _('Score') }, [ labels.percent(row.score) ]), E('td', { 'class': 'td', 'data-title': _('Eligibility') }, [ row.actionId === s.selectedCandidateId ? _('Selected') : (blocked ? labels.smartReason(blocked.reason) : _('Eligible')) ]), E('td', { 'class': 'td', 'data-title': _('Cooldown') }, [ blocked && blocked.cooldownRemaining ? labels.duration(blocked.cooldownRemaining) : '—' ]) ]);
			}) : [ E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'colspan': '5', 'data-title': _('Rank') }, [ _('No ranking is available yet. Refresh the decision or wait for the next evaluation.') ]) ]) ];
		const table = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [ E('caption', { 'class': 'pm-visually-hidden' }, [ _('Ranking table') ]), E('thead', {}, [ E('tr', { 'class': 'tr cbi-section-table-titles' }, [ E('th', { 'class': 'th' }, [ _('Rank') ]), E('th', { 'class': 'th' }, [ _('Candidate') ]), E('th', { 'class': 'th' }, [ _('Score') ]), E('th', { 'class': 'th' }, [ _('Eligibility') ]), E('th', { 'class': 'th' }, [ _('Cooldown') ]) ]) ]), E('tbody', {}, rows) ]) ]);
		const rankingActions = pu.toolbar([ refresh ]);
		rankingActions.classList.add('pm-rill-ranking-actions');
		const context = s.context || {};
		const feedbackOutput = E('div', {}, [ _('Expand to load recent validated feedback.') ]);
		const feedbackDetails = E('details', { 'class': 'pm-disclosure' }, [
			E('summary', {}, [ _('Show recent validated feedback') ]),
			feedbackOutput
		]);
		let feedbackLoaded = false;
		feedbackDetails.addEventListener('toggle', function() {
			if (!feedbackDetails.open || feedbackLoaded) return;
			feedbackLoaded = true;
			feedbackOutput.replaceChildren(_('Loading feedback…'));
			pm.rillFeedback(5).then(function(result) {
				const feedback = ((result && result.feedback) || []).slice().reverse();
				const feedbackRows = feedback.length ? feedback.map(function(row) {
					const d = row.data || {};
					return E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td', 'data-title': _('Candidate') }, [ labels.actionName(d.actionId) ]),
						E('td', { 'class': 'td', 'data-title': _('Goal') }, [ labels.goal(d.goal || s.goal) ]),
						E('td', { 'class': 'td', 'data-title': _('Reward') }, [ labels.percent(d.reward) ]),
						E('td', { 'class': 'td', 'data-title': _('Quality') }, [ labels.measurementQuality(d.measurementQuality) ]),
						E('td', { 'class': 'td', 'data-title': _('Result') }, [ d.accepted === true ? _('Accepted') : _('Reconciled') ])
					]);
				}) : [ E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td', 'colspan': '5', 'data-title': _('Candidate') }, [ _('No validated feedback yet.') ]) ]) ];
				const feedbackTable = E('div', { 'class': 'pu-table-scroll' }, [ E('table', { 'class': 'table' }, [
					E('caption', { 'class': 'pm-visually-hidden' }, [ _('Feedback table') ]),
					E('thead', {}, [ E('tr', { 'class': 'tr cbi-section-table-titles' }, [
						E('th', { 'class': 'th' }, [ _('Candidate') ]), E('th', { 'class': 'th' }, [ _('Goal') ]),
						E('th', { 'class': 'th' }, [ _('Reward') ]), E('th', { 'class': 'th' }, [ _('Quality') ]),
						E('th', { 'class': 'th' }, [ _('Result') ])
					]) ]),
					E('tbody', {}, feedbackRows)
				]) ]);
				feedbackOutput.replaceChildren(feedbackTable);
			}).catch(function(error) {
				feedbackOutput.replaceChildren(E('p', { 'class': 'alert-message warning', 'role': 'status' }, [
					_('Unable to load feedback records: %s').format(error.message || error)
				]));
				feedbackLoaded = false;
			});
		});
		const outcomeText = s.lastOutcome
			? _('Reward %s · %s').format(labels.percent(s.lastOutcome.reward), labels.measurementQuality(s.lastOutcome.measurementQuality))
			: '—';
		const candidateHistory = s.candidateHistory || {};
		const rillUnavailable = !!r.state && r.state !== 'available' && r.state !== 'learning';
		const eligible = rillUnavailable ? _('Rill unavailable') : (s.autoEligible === true ? _('Ready') : (s.autoEligible === false ? _('Paused') : _('Not evaluated')));
		const decisionReason = s.reason ? labels.smartReason(s.reason) : (s.selectedActionId === 'pm.noop' ? _('The current configuration meets the policy.') : _('No decision reason is available yet.'));
		const pageNodes = [
			pu.card(_('Package management'), E('div', {}, [ packageToolbar, packageStatus, packageDetails ])),
			pu.card(_('Current decision'), E('div', {}, [
				pu.badge(labels.runtimeStatus(r.status)),
				pu.kv([
					[_('Selected action'), labels.actionName(s.selectedActionId)],
					[_('Automatic action'), eligible],
					[_('Confidence'), labels.percent(s.confidence)],
					[_('Learning stage'), labels.learningStage(s.learningStage)],
					[_('Last outcome'), outcomeText],
					[_('Why'), decisionReason]
				])
			])),
			pu.note(_('Rill provides observations and recommendations. Core checks safety and keeps final control over every change.'), 'info'),
			pu.grid([
				pu.card(_('Top ranking'), E('div', {}, [ rankingActions, pu.tableWrap(table) ])),
				pu.card(_('Recent feedback'), feedbackDetails)
			]),
			pu.card(_('Advanced details'), pu.jsonBox({
				runtime: r,
				context: context,
				selection: s,
				candidateHistory: candidateHistory,
				advisory: rec.learnedAdvisory || []
			}, _('Runtime, decision and candidate details')))
		];
		if (s.drifted)
			pageNodes.splice(1, 0, pu.note(_('Performance drift detected. Rill Auto temporarily paused.'), 'warning'));
		return pu.page(_('Rill smart decisions'), _('Rill ranks actions that passed the Core engine review; the Core engine keeps the final authority to execute them.'), pageNodes);
	}
});
