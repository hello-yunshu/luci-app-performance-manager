'use strict';
'require view';
'require ui';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';
'require performance-manager.labels as labels';

/* Where the verdict of the last "check for updates" survives the reload it
 * triggers. Same-tab storage: closing the tab drops a claim that is about the
 * feed as it looked minutes ago. */
const REFRESH_RECORD_KEY = 'pm.rill.package-refresh';

function readRefreshRecord() {
	try {
		if (typeof window === 'undefined' || !window.sessionStorage)
			return null;
		const raw = window.sessionStorage.getItem(REFRESH_RECORD_KEY);
		if (!raw)
			return null;
		const record = JSON.parse(raw);
		return (record && typeof record.at === 'number' && !isNaN(record.at)) ? record : null;
	}
	catch (e) {
		return null;
	}
}

function rememberRefresh(result, at) {
	try {
		if (typeof window === 'undefined' || !window.sessionStorage)
			return;
		window.sessionStorage.setItem(REFRESH_RECORD_KEY, JSON.stringify({
			/* Page load retiring a stale verdict is not a new check; keep the
			 * timestamp of the observation the verdict came from. */
			at: (typeof at === 'number' && !isNaN(at)) ? at : Date.now(),
			hasUpdate: labels.managerUpdatePending(result)
		}));
	}
	catch (e) {
		/* Private mode or a full quota: the page still reloads, it just cannot
		 * carry the verdict over. */
	}
}

function forgetRefresh() {
	try {
		if (typeof window !== 'undefined' && window.sessionStorage)
			window.sessionStorage.removeItem(REFRESH_RECORD_KEY);
	}
	catch (e) {
		/* Storage may be unavailable; the page renders its empty state. */
	}
}

/* A verdict written before an install/update can survive the reload that
 * follows it. The manager status read on page load is a fresh observation:
 * retire a stale "update available" claim when it says nothing is pending. */
function reconcileRefreshRecord(manager) {
	if (!manager || manager.ok !== true || labels.managerUpdatePending(manager) !== false)
		return;
	const flags = [ 'updateAvailable', 'runtimeUpdateAvailable', 'pmUpdateAvailable', 'cfiUpdateAvailable', 'clientUpdateAvailable' ];
	if (!flags.some(function(flag) { return manager[flag] === false; }))
		return;
	const record = readRefreshRecord();
	if (record && record.hasUpdate === true)
		rememberRefresh({ updateAvailable: false }, record.at);
}

/* LuCI bounds every ubus RPC by L.env.rpctimeout (seconds, default 20). The
 * shared package manager can legitimately take longer; a client timeout does
 * not cancel the router-side work, so verify before declaring failure. */
const MANAGER_RPC_TIMEOUT_SECONDS = 120;
const MANAGER_STATUS_INTERVAL_MS = 2000;
const MANAGER_STATUS_ATTEMPTS = 15;
const managerTimer = (typeof window !== 'undefined' && window.setTimeout) ? window.setTimeout : setTimeout;
/* A reload wipes the outcome notice before it can be read; give it a moment on
 * screen, the same way the Cloudflare IP Runtime actions do. */
const MANAGER_RELOAD_DELAY_MS = 1500;
/* Package actions share one opkg lock on the router. Track every rendered
 * action button so one running action locks the others too; disabling only the
 * clicked button still lets a second click queue a duplicate transaction. */
const managerActionButtons = [];

function setManagerActionButtonsBusy(except, busy) {
	managerActionButtons.forEach(function(btn) {
		if (!btn || btn === except)
			return;
		if (busy) {
			if (!Object.prototype.hasOwnProperty.call(btn, '__pmBusyBefore'))
				btn.__pmBusyBefore = btn.disabled === true;
			btn.disabled = true;
		} else {
			const wasDisabled = btn.__pmBusyBefore === true;
			delete btn.__pmBusyBefore;
			if (!wasDisabled)
				btn.disabled = false;
		}
	});
}

function managerRequestTimedOut(error) {
	return /timed out|timeout/i.test(String((error && error.message) || error || ''));
}

function withManagerTimeout(call) {
	const env = (typeof L !== 'undefined' && L && L.env) ? L.env : null;
	const previous = env ? env.rpctimeout : undefined;
	if (!env || previous === MANAGER_RPC_TIMEOUT_SECONDS)
		return Promise.resolve().then(call);
	env.rpctimeout = MANAGER_RPC_TIMEOUT_SECONDS;
	return Promise.resolve().then(call).finally(function() { env.rpctimeout = previous; });
}

function waitForManagerIdle() {
	let attempts = 0;
	function poll() {
		attempts += 1;
		return pm.runtimeManagerStatus().then(function(state) {
			if (state && state.busy === true)
				throw new Error(_('The package manager is still busy. Do not retry until it is idle.'));
			return state || null;
		}).catch(function(error) {
			if (attempts < MANAGER_STATUS_ATTEMPTS)
				return new Promise(function(resolve) { managerTimer(resolve, MANAGER_STATUS_INTERVAL_MS); }).then(poll);
			throw error;
		});
	}
	return poll();
}

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
			/* Name the work: refreshing the indexes downloads them, and "Working..."
			 * for a minute reads as a hang. */
			const restore = pu.setBusy(button, action === 'refresh' ? _('Refreshing package indexes...') : _('Working...'));
			setManagerActionButtonsBusy(button, true);
			const invoke = function() {
				if (action === 'install')
					return pm.runtimeManagerInstall(packageName);
				if (action === 'repair')
					return pm.runtimeManagerRepair(packageName);
				if (action === 'refresh')
					return pm.runtimeManagerRefresh();
				return pm.runtimeManagerUpdate(packageName);
			};
			function reloadAndRestore() {
				const finish = function() {
					restore();
					setManagerActionButtonsBusy(button, false);
				};
				if (typeof window === 'undefined') {
					finish();
					return;
				}
				managerTimer(function() {
					window.location.reload();
					finish();
				}, MANAGER_RELOAD_DELAY_MS);
			}
			function finishWithStatus(state) {
				/* The verdict of the earlier check can be stale after an
				 * install/update. Use this fresh status, or drop the claim if
				 * the manager cannot be read. */
				if (state && state.ok === true)
					rememberRefresh(state);
				else
					forgetRefresh();
				ui.addNotification(null, E('p', {}, [ labels.managerActionOutcome(action) ]));
				reloadAndRestore();
			}
			withManagerTimeout(invoke).then(function(result) {
				if (!result || result.ok !== true) {
					/* Carry the manager's error code into the summary so the page
					 * can translate it; the manager's own sentence is kept as the
					 * detail line instead of being shown as "unknown error". */
					const failure = new Error((result && (result.errorCode || result.message)) || _('Unable to manage packages.'));
					if (result && result.errorCode && result.message)
						failure.detail = result.message;
					throw failure;
				}
				if (action === 'refresh') {
					/* "Check for updates" owns its own verdict; no second status
					 * call is needed before the reload. */
					rememberRefresh(result);
					ui.addNotification(null, E('p', {}, [ labels.managerActionOutcome(action) ]));
					reloadAndRestore();
					return;
				}
				return pm.runtimeManagerStatus().then(finishWithStatus).catch(function() {
					finishWithStatus(null);
				});
			}).catch(function(error) {
				if (!managerRequestTimedOut(error)) {
					const body = [ _('Package operation failed: %s').format(labels.errorSummary(error)) ];
					if (error && error.detail)
						body.push(E('p', {}, [ error.detail ]));
					ui.addNotification(null, E('div', {}, body), 'error');
					restore();
					setManagerActionButtonsBusy(button, false);
					return;
				}
				/* A client timeout does not cancel the ubus call. Keep the
				 * buttons busy until the manager says it is idle. */
				return waitForManagerIdle().then(function(state) {
					/* An unreadable status is not confirmation that the manager
					 * is idle. Keep the buttons locked instead of claiming the
					 * action finished. */
					if (!state || state.ok !== true) {
						forgetRefresh();
						ui.addNotification(null, E('p', {}, [ _('The package manager status could not be read. Do not retry until it is idle.') ]), 'warning');
						return;
					}
					rememberRefresh(state);
					ui.addNotification(null, E('p', {}, [ _('The package manager request timed out, but the manager is now idle. The page will reload; check the package status above before retrying.') ]), 'warning');
					reloadAndRestore();
				}).catch(function(verifyError) {
					forgetRefresh();
					const busyTitle = _('The package manager is still busy. Do not retry until it is idle.');
					const body = [ busyTitle ];
					if (verifyError && verifyError.message && verifyError.message !== busyTitle)
						body.push(E('p', {}, [ verifyError.message ]));
					ui.addNotification(null, E('div', {}, body), 'error');
					/* No restore(): an unverified action must not be queued twice. */
				});
			});
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
		/* The verdict of the last check is a fact about the feed, not an action:
		 * it lives in the details table, so the rows below stay pure
		 * affordances. */
		if (managerAvailable)
			reconcileRefreshRecord(manager);
		const refreshRecord = managerAvailable ? readRefreshRecord() : null;
		const refreshNote = labels.managerRefreshNote(refreshRecord);
		/* One native row per action, titled with the object it acts on and never
		 * with the button label itself. A bar of bare buttons left "Check for
		 * updates" ambiguous: nothing on the page said it refreshes the feed
		 * index instead of upgrading something. The row title used to repeat the
		 * button verbatim ("Install Rill Runtime" over an "Install Rill Runtime"
		 * button), which said the same thing twice and named no object; the
		 * Cloudflare IP Runtime block titles its rows the same way. */
		const packageActions = [];
		managerActionButtons.length = 0;
		const checkPackages = E('button', { 'class': 'btn cbi-button', 'type': 'button', 'disabled': managerSupportsDevice && !managerBusy ? null : '' }, [ _('Check for updates') ]);
		managerActionButtons.push(checkPackages);
		checkPackages.addEventListener('click', function() { managerAction('refresh', null, checkPackages); });
		packageActions.push(pu.field(_('Package index'), checkPackages, _('Refreshes the trusted feed index, then reports whether an update is available.')));
		if (managerAvailable && manager.supported === true && manager.installed !== true && !runtimeConflict) {
			const installRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Install Rill Runtime') ]);
			managerActionButtons.push(installRuntime);
			installRuntime.addEventListener('click', function() { managerAction('install', 'rill-runtime', installRuntime); });
			packageActions.push(pu.field(_('Rill Runtime'), installRuntime, _('Installs the shared Runtime package for this release and architecture.')));
		}
		if (managerAvailable && manager.supported === true && manager.runtimeUpdateAvailable === true && !runtimeConflict) {
			const updateRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Update Rill Runtime') ]);
			managerActionButtons.push(updateRuntime);
			updateRuntime.addEventListener('click', function() { managerAction('update', 'rill-runtime', updateRuntime); });
			packageActions.push(pu.field(_('Rill Runtime'), updateRuntime, _('Updates only a compatible Stable Runtime; Preview installs are never replaced.')));
		}
		if (managerAvailable && manager.repairAvailable === true && !runtimeConflict) {
			const repairRuntime = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Repair Rill Runtime') ]);
			managerActionButtons.push(repairRuntime);
			repairRuntime.addEventListener('click', function() { managerAction('repair', 'rill-runtime', repairRuntime); });
			packageActions.push(pu.field(_('Rill Runtime'), repairRuntime, _('Reinstalls the same Stable package when its executable is missing; the version does not change.')));
		}
		if (managerAvailable && manager.pmUpdateAvailable === true) {
			const updatePm = E('button', { 'class': 'btn cbi-button cbi-button-action', 'type': 'button', 'disabled': managerBusy ? '' : null }, [ _('Update Performance Manager') ]);
			managerActionButtons.push(updatePm);
			updatePm.addEventListener('click', function() { managerAction('update', 'luci-app-performance-manager-all', updatePm); });
			packageActions.push(pu.field(_('Performance Manager'), updatePm, _('Installs the newer Performance Manager package from the unified feed.')));
		}
		const packageActionRows = E('div', { 'class': 'pm-package-actions' }, packageActions);
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
		/* One information block, one interaction block. The facts about the
		 * installed Runtime - including when the feed was last checked and what
		 * it answered - are rows of the same native table; the buttons that
		 * change those facts are a separate row underneath and carry no status
		 * of their own. Same split as the Cloudflare IP Runtime block, which
		 * also states before it offers. */
		const compatText = (managerVerdictOverridden || manager.compatible === true)
			? _('Compatible')
			: (manager.compatible === false ? _('Needs attention') : _('Unknown'));
		const lastCheck = refreshNote
			? E('span', {}, [
				pu.badge(refreshNote.hasUpdate ? _('Update available') : _('Up to date'), refreshNote.hasUpdate ? 'warning' : 'success'),
				' · ' + refreshNote.clock
			])
			: _('Not checked in this session.');
		const packageDetails = managerAvailable ? pu.kv([
			[_('OpenWrt release'), manager.release || _('Unknown')],
			[_('Package architecture'), manager.architecture || _('Unknown')],
			[_('Runtime package'), manager.installed === true ? (legacyPreviewConflict ? 'rill-runtime-preview' : (manager.package || 'rill-runtime')) : 'rill-runtime'],
			[_('Runtime version'), managerVersion || (manager.installed === true ? _('Unknown') : _('Not installed'))],
			[_('Runtime channel'), manager.channel || _('Unknown')],
			[_('Runtime compatibility'), compatText],
			[_('Last update check'), lastCheck]
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
			pu.card(_('Package management'), E('div', {}, [ packageStatus, packageDetails, packageActionRows ].filter(function(node) { return node != null; }))),
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
