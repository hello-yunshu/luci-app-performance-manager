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
		return Promise.all([ pm.status(), pm.topology(), pm.transactions() ].map(function(p) {
			return p.catch(function(err) {
				console.error('performance-manager: overview load failed', err);
				return { _loadError: err };
			});
		}));
	},
	render: function(data) {
		if ((data || []).some(function(d) { return d && d._loadError; }))
			return pu.page(_('Performance Manager'), null, pu.note(_('Unable to load this page. Retry the page; if it keeps failing, check the service log.'), 'danger'));
		const s = data[0] || {}, t = data[1] || {};
		const txs = (data[2] && data[2].transactions) || [];
		const profile = s.profile || {}, rill = s.rill || {}, guard = s.healthGuard || {};
		/* degraded means "healthy but a recommended package is missing"; an
		 * unhealthy profile is a different state and must not be labelled
		 * degraded. */
		const recentTx = txs[0] || {};
		const overview = [];
		const statusBanner = E('div', {
			'class': 'cbi-section alert-message ' + (s.running ? 'success' : 'warning'),
			'role': 'status'
		}, [
			E('h3', {}, s.running ? _('Performance Manager is running') : _('Performance Manager is stopped')),
			E('p', {}, _('Review safeguards and system information below.'))
		]);
		overview.push(statusBanner);

		function statCard(label, value, note) {
			const children = [
				E('div', { 'class': 'pm-overview-stat-value' }, [ value ]),
				E('div', { 'class': 'pm-overview-stat-label' }, [ label ])
			];
			if (note)
				children.push(E('small', { 'class': 'pm-overview-stat-note' }, [ note ]));
			return E('div', { 'class': 'cbi-section pm-overview-stat-card' }, children);
		}

		let profileValue = profile.healthy
			? (profile.degraded ? _('Degraded') : _('Healthy'))
			: _('Incomplete');
		let profileNote = '';
		const missingRequiredPackages = profile.missingRequiredPackages || [];
		const missingRecommendedPackages = profile.missingRecommendedPackages || [];
		const missingConditionalPackages = profile.missingConditionalPackages || [];
		const missingCapabilities = profile.missingCapabilities || [];
		const missingCommands = profile.missingCommands || [];
		const recommendedPackages = profile.recommendedPackages || [];
		const expectedCommands = profile.expectedCommands || [];
		/* Missing recommended tools should explain a partial profile without
		 * making it look like required components or capabilities are broken. */
		const recommendedToolsMissing = !profile.healthy &&
			!missingRequiredPackages.length && !missingConditionalPackages.length &&
			!missingCapabilities.length && profile.targetMatched !== false &&
			(missingRecommendedPackages.length > 0 || missingCommands.length > 0);
		if (recommendedToolsMissing)
			profileValue = _('Recommended tools missing');
		if (!profile.healthy) {
			if (recommendedToolsMissing)
				profileNote = _('Some recommended testing and diagnostic tools are missing.');
			else if (missingRequiredPackages.length)
				profileNote = _('Required components are unavailable.');
			else if (missingCommands.length || missingRecommendedPackages.length)
				profileNote = _('Some recommended testing and diagnostic tools are missing.');
			else if (missingCapabilities.length || missingConditionalPackages.length)
				profileNote = _('Some profile capabilities are unavailable.');
			else
				profileNote = _('Review profile details for unavailable components.');
		}
		else if (profile.degraded) {
			profileNote = _('Some optional components are missing.');
		}

		const stats = E('div', { 'class': 'pm-overview-stats' }, [
			statCard(_('System profile'), profileValue, profileNote),
			statCard(_('Health guard'), guard.pass ? _('Passed') : _('Blocked')),
			statCard(_('Automation mode'), labels.automation(s.automation)),
			statCard(_('Rill runtime'), labels.runtimeStatusOverview(rill.status))
		]);
		overview.push(stats);

		function table(rows, className) {
			return E('table', { 'class': 'table ' + (className || '') }, rows.map(function(row) {
				return E('tr', { 'class': 'tr' }, [
					E('th', { 'class': 'th', 'scope': 'row' }, [ row[0] ]),
					E('td', { 'class': 'td' }, [ row[1] == null || row[1] === '' ? '—' : row[1] ])
				]);
			}));
		}

		const serviceInfo = E('div', { 'class': 'cbi-section' }, [
			E('h3', {}, [ _('System Information') ]),
			table([
				[_('Goal'), labels.goal(s.goal)],
				[_('Profile'), labels.profile(profile.id)],
				[_('Failsafe'), pu.badge(s.failsafe ? _('Enabled') : _('Disabled'), s.failsafe ? 'success' : 'warning')]
			], 'pm-overview-info-table')
		]);
		overview.push(serviceInfo);

		if (recommendedPackages.length || expectedCommands.length) {
			const dependencyRows = [];
			if (missingRecommendedPackages.length || missingCommands.length) {
				dependencyRows.push(pu.note(_('Some recommended testing and diagnostic tools are missing.'), 'warning'));
				function dependencyLine(label, value) {
					return E('p', {}, [ E('strong', {}, [ label + ':' ]), ' ', E('code', {}, [ value ]) ]);
				}
				if (missingRecommendedPackages.length)
					dependencyRows.push(dependencyLine(_('Missing recommended packages'), missingRecommendedPackages.join(' ')));
				if (missingCommands.length)
					dependencyRows.push(dependencyLine(_('Missing commands'), missingCommands.join(' ')));

				if (missingRecommendedPackages.length && missingRecommendedPackages.indexOf('ip-full') < 0 &&
					(profile.packageManager === 'apk' || profile.packageManager === 'opkg')) {
					const installCommand = (profile.packageManager === 'apk' ? 'apk add ' : 'opkg install ') + missingRecommendedPackages.join(' ');
					dependencyRows.push(dependencyLine(_('Install command'), installCommand));
				}
			}
			else {
				dependencyRows.push(pu.note(_('All recommended dependencies are available.'), 'success'));
			}

			overview.push(E('div', { 'class': 'cbi-section pm-overview-dependency-status' }, [
				E('h3', {}, [ _('Dependency Status') ]),
				E('div', {}, dependencyRows)
			]));
		}

		const recentBody = [
			pu.kv([
				[_('Action'), labels.actionName(recentTx.actionId)],
				[_('State'), labels.state(recentTx.state)],
				[_('Target'), labels.target(recentTx.applyTarget)]
			])
		];
		if (txs.length)
			recentBody.push(pu.jsonBox(recentTx, _('Technical details')));

		const detailGrid = E('div', { 'class': 'pm-grid pm-overview-details' }, [
			pu.card(_('System health guard'), E('div', {}, [
				pu.badge(guard.pass ? _('Health guard passed') : _('Blocked by health guard'), guard.pass ? 'success' : 'warning'),
				pu.kv([
					[_('Reasons'), (guard.reasons || []).map(labels.guardReason).join('、') || _('None')]
				])
			])),

			pu.card(_('Recent transaction'), txs.length ? E('div', {}, recentBody) : pu.note(_('No transactions are available yet.'), 'info')),

			pu.card(_('Path'), E('div', {}, [
				pu.kv([
					[_('LAN → WAN'), labels.routeIdentity(t.paths && t.paths[0] && t.paths[0].routeIdentity)],
					[_('Workload'), ((t.paths && t.paths[0] && t.paths[0].workloadClass) || []).map(labels.workloadClass).join('、') || _('None')]
				]),
				t.paths && t.paths[0] ? pu.jsonBox({
					routeIdentity: t.paths[0].routeIdentity,
					routeProvider: t.paths[0].routeProvider,
					workloadClass: t.paths[0].workloadClass,
					targetRefs: t.paths[0].targetRefs
				}, _('Technical details')) : null
			].filter(function(node) { return node != null; }))),

			pu.card(_('Advanced details'), pu.jsonBox({
				status: s,
				topology: t,
				nativePacketSteering: s.nativePacketSteering || {}
			}, _('Status, path and provider details')))
		]);
		overview.push(detailGrid);
		return pu.page(_('Performance Manager'), null, overview);
	}
});
