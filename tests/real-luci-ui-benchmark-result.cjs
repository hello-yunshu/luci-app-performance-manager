'use strict';
/* Render the controlled A/B completion branches with real LuCI assets and a
 * deterministic ubus response. The actual apply/measure/rollback lifecycle is
 * verified separately on a disposable OpenWrt instance. */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const base = process.env.PM_UI_BASE || 'http://127.0.0.1:18080';
const container = process.env.PM_UI_CONTAINER || 'pm-ui-gate';
const password = process.env.PM_UI_PASSWORD || 'pm-gate';
const output = process.env.PM_BENCHMARK_RESULT_OUT || path.join(process.cwd(), 'real-luci-ui-evidence/benchmark-result');
const language = process.env.PM_UI_LANG || 'en';
if (!['en', 'zh_cn'].includes(language)) throw new Error('Unsupported PM_UI_LANG: ' + language);
const smoke = process.env.PM_UI_SMOKE_ONLY === '1';
if (smoke && process.env.GITHUB_ACTIONS === 'true') throw new Error('Smoke-only mode is prohibited in GitHub Actions');

const themes = [
	{ id: 'bootstrap-default-light', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'light', aurora: null },
	{ id: 'bootstrap-default-dark', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'dark', aurora: null },
	{ id: 'bootstrap-light', media: 'bootstrap', theme: 'bootstrap-light', colorScheme: 'light', aurora: null },
	{ id: 'bootstrap-dark', media: 'bootstrap', theme: 'bootstrap-dark', colorScheme: 'dark', aurora: null },
	{ id: 'aurora-light', media: 'aurora', theme: 'aurora', colorScheme: 'light', aurora: 'light' },
	{ id: 'aurora-dark', media: 'aurora', theme: 'aurora', colorScheme: 'dark', aurora: 'dark' }
];
const commonWidths = [320, 360, 375, 390, 430, 640, 768, 1024, 1280, 1440, 1920];
const rpcEndpointGlob = '**/ubus/**';
const breakpoints = [600, 700, 768, 900, 991, 1048, 1100, 1200, 1280, 1319];
const widths = [...new Set([...commonWidths, ...breakpoints.flatMap(w => [w - 1, w, w + 1])])].sort((a, b) => a - b);
const shortViewports = [{ width: 320, height: 568 }, { width: 568, height: 320 }];
const scenarios = ['validated', 'unvalidated'];
const selectedThemes = smoke ? themes.filter(theme => theme.id === 'bootstrap-dark') : themes;
const selectedWidths = smoke ? [320, 1280] : widths;
const selectedViewports = smoke ? [shortViewports[0]] : shortViewports;
const selectedScenarios = smoke ? ['validated', 'unvalidated'] : scenarios;
const report = {
	schemaVersion: 1,
	sha: process.env.GITHUB_SHA || 'unknown',
	language,
	mode: smoke ? 'local-smoke-only' : 'full-matrix',
	method: 'Real LuCI benchmark view and theme assets; controlled A/B completion response is fixture-backed. Real apply/measurement/rollback is covered by a separate disposable-device run.',
	widths: selectedWidths,
	shortViewports: selectedViewports,
	themes: selectedThemes.map(t => t.id),
	scenarios: selectedScenarios,
	notCovered: ['real transaction lifecycle in this visual fixture'],
	rows: [],
	errors: []
};
fs.mkdirSync(output, { recursive: true });

function shell(command) {
	return execFileSync('docker', ['exec', container, 'sh', '-c', command], { encoding: 'utf8' }).trim();
}

async function login(page) {
	await page.goto(base + '/cgi-bin/luci/admin/network/performance-manager/benchmark', { waitUntil: 'domcontentloaded' });
	const username = page.locator('input[name="luci_username"]');
	if (await username.count()) {
		await username.fill('root');
		await page.locator('input[name="luci_password"]').fill(password);
		const submit = page.locator('button[type="submit"], input[type="submit"]');
		if (await submit.count()) await submit.first().click();
		else await page.locator('input[name="luci_password"]').press('Enter');
		await page.waitForLoadState({ state: 'domcontentloaded', timeout: 20000 }).catch(() => {});
	}
	if (await page.locator('input[name="luci_password"]').count()) throw new Error('LuCI login failed');
}

function fixture(scenario) {
	const validated = scenario === 'validated';
	return {
		ok: true,
		session: {
			schemaVersion: 2,
			sessionId: 'visual-fixture-controlled-ab-' + scenario,
			state: 'completed',
			userInitiated: true,
			actionId: 'network.buffers',
			evaluationPath: 'path:local-endpoint',
			measurementClass: 'controlled_ab',
			controlEvidence: { contract: 'pm-companion/v2', phase: 'control', fixture: true },
			candidateEvidence: { contract: 'pm-companion/v2', phase: 'candidate', fixture: true },
			result: {
				validated,
				rolledBack: true,
				health: { pass: validated, reasons: validated ? [] : ['fixture-health-check-warning'] },
				fixture: true
			}
		}
	};
}

async function installRpcFixture(page, fixtureState) {
	await page.route(rpcEndpointGlob, async route => {
		let body;
		try { body = route.request().postDataJSON(); }
		catch (_) { return route.continue(); }
		const messages = Array.isArray(body) ? body : [body];
		for (const message of messages) {
			if (!message || message.method !== 'call' || !Array.isArray(message.params) || message.params[1] !== 'performance-manager') continue;
			fixtureState.observed.push({
				method: message.params[2] || null,
				phase: message.params[3] && message.params[3].phase || null,
				parameterKeys: message.params[3] && typeof message.params[3] === 'object' ? Object.keys(message.params[3]).sort() : []
			});
		}
		const matched = messages.filter(message => message && message.method === 'call' && Array.isArray(message.params) &&
			message.params[1] === 'performance-manager' && message.params[2] === 'benchmark_start');
		if (!matched.length) return route.continue();
		/* Never forward phase=begin to the real daemon: that would start a
		 * transaction. This visual fixture replaces only the matched read-free
		 * display response and refuses unexpected mixed RPC batches. */
		if (matched.length !== messages.length || matched.some(message => !message.params[3] || message.params[3].phase !== 'begin')) {
			throw new Error('Refusing an unexpected benchmark_start request in the visual fixture');
		}
		fixtureState.intercepted.push({ scenario: fixtureState.scenario, count: matched.length, phase: matched[0].params[3].phase });
		const replacement = new Map(matched.map(message => [message.id, {
			jsonrpc: '2.0', id: message.id, result: [0, fixture(fixtureState.scenario)]
		}]));
		const response = Array.isArray(body) ? messages.map(message => replacement.get(message.id)) : replacement.get(messages[0].id);
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify(response)
		});
	});
}

async function capture(page, theme, scenario, width, height) {
	const suffix = height === 900 ? String(width) : `${width}x${height}`;
	const name = `${theme.id}-${scenario}-${suffix}.png`;
	const file = path.join(output, name);
	const expectedNote = language === 'en'
		? (scenario === 'validated'
			? 'Test complete. The candidate was rolled back and health checks passed.'
			: 'Test complete, but the result was not validated. Review the details below.')
		: (scenario === 'validated'
			? '测试已完成，候选项已回滚，健康检查通过。'
			: '测试已完成，但结果未通过验证。请查看下方详情。');
	await page.setViewportSize({ width, height });
	const expectedHeading = language === 'en' ? 'Performance test' : '性能测试';
	const metrics = await page.evaluate(({ expectedNote, scenario, media }) => {
		const root = document.documentElement;
		const main = document.querySelector('#maincontent');
		const stages = Array.from(main ? main.querySelectorAll('.pm-stage') : []);
		const stageText = stages.map(el => el.innerText.trim());
		const note = Array.from(main ? main.querySelectorAll('.alert-message') : []).find(el => el.innerText.trim() === expectedNote);
		const selects = Array.from(main ? main.querySelectorAll('.pm-benchmark-field select') : []);
		const fits = selects.every(el => {
			const r = el.getBoundingClientRect();
			const field = el.closest('.pm-benchmark-field').getBoundingClientRect();
			return r.left >= field.left - 1 && r.right <= field.right + 1 && r.right <= innerWidth + 1;
		});
		const rollback = stages.find(el => el.innerText.includes('Rollback protection') || el.innerText.includes('回滚保护'));
		const rollbackComplete = !!rollback && /complete|已完成/i.test(rollback.innerText);
		const resources = Array.from(document.querySelectorAll('link[href],script[src]')).map(el => el.href || el.src);
		return {
			hasMain: !!main,
			heading: main && (main.querySelector('h2[name="content"], .view h2, h2') || {}).textContent?.trim(),
			loading: !!(main && /Loading view|加载视图/.test(main.innerText)),
			note: note ? note.innerText.trim() : null,
			noteTone: note ? (note.className || '') : '',
			stageCount: stages.length,
			stageText,
			rollbackComplete,
			allStagesComplete: stages.every(el => /complete|已完成/i.test(el.innerText)),
			selectsFit: fits,
			themeLoaded: resources.some(src => src.includes('/luci-static/' + media + '/')),
			pluginCssLoaded: resources.some(src => src.includes('performance-manager/ui.css')),
			scenario,
			width: innerWidth,
			scrollWidth: root.scrollWidth,
			overflow: root.scrollWidth > innerWidth + 1
		};
	}, { expectedNote, scenario, media: theme.media });

	const errors = [];
	if (!metrics.hasMain || metrics.loading) errors.push('benchmark-view-missing-or-loading');
	if (metrics.heading !== expectedHeading) errors.push('wrong-benchmark-heading');
	if (!metrics.note) errors.push('expected-result-note-missing');
	if (!metrics.noteTone.includes(scenario === 'validated' ? 'success' : 'warning')) errors.push('result-note-tone-mismatch');
	if (metrics.stageCount !== 8) errors.push('controlled-ab-stage-count-not-eight');
	if (!metrics.rollbackComplete) errors.push('rollback-protection-stage-not-complete');
	if (scenario === 'validated' && !metrics.allStagesComplete) errors.push('validated-result-has-incomplete-stage');
	if (metrics.scenario !== scenario || metrics.width !== width) errors.push('scenario-or-viewport-mismatch');
	if (metrics.overflow) errors.push('horizontal-overflow');
	if (width <= 600 && !metrics.selectsFit) errors.push('benchmark-controls-exceed-available-width');
	if (!metrics.themeLoaded) errors.push('theme-assets-not-loaded');
	if (!metrics.pluginCssLoaded) errors.push('plugin-css-not-loaded');
	await page.screenshot({ path: file, fullPage: true, animations: 'disabled' });
	if (height < 900) await page.screenshot({ path: file.replace(/\.png$/, '-viewport.png'), fullPage: false, animations: 'disabled' });
	const row = { theme: theme.id, language, route: 'admin/network/performance-manager/benchmark', scenario, viewport: `${width}x${height}`, result: errors.length ? 'FAIL' : 'PASS', errors, metrics, screenshot: name };
	report.rows.push(row);
	if (errors.length) report.errors.push(row);
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}

(async () => {
	const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE || undefined });
	try {
		for (const theme of selectedThemes) {
			shell(`uci set luci.main.mediaurlbase='/luci-static/${theme.media}'; uci set luci.main.theme='${theme.theme}'; uci commit luci; rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache*; /etc/init.d/uhttpd restart >/dev/null 2>&1`);
			await new Promise(resolve => setTimeout(resolve, 800));
			const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: theme.colorScheme });
			if (theme.aurora) await context.addInitScript(mode => localStorage.setItem('aurora.theme', mode), theme.aurora);
			const page = await context.newPage();
			try {
				const browserErrors = [];
				const postRequests = [];
				page.on('pageerror', error => browserErrors.push(error.message));
				page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
				page.on('request', request => {
					if (request.method() !== 'POST') return;
					let calls = [];
					try {
						const body = request.postDataJSON();
						for (const message of Array.isArray(body) ? body : [body])
							if (message && message.method === 'call' && Array.isArray(message.params))
								calls.push({ object: message.params[1] || null, method: message.params[2] || null });
					}
					catch (_) {}
					if (calls.length || /ubus|rpc/i.test(request.url())) postRequests.push({ url: request.url(), calls });
				});
				await login(page);
				const fixtureState = { scenario: null, observed: [], intercepted: [] };
				await installRpcFixture(page, fixtureState);
				for (const scenario of selectedScenarios) {
					fixtureState.scenario = scenario;
					await page.goto(base + '/cgi-bin/luci/admin/network/performance-manager/benchmark', { waitUntil: 'domcontentloaded' });
					await page.waitForFunction(() => {
						const main = document.querySelector('#maincontent');
						return main && main.innerText.trim().length > 10 && !/Loading view|加载视图/.test(main.innerText);
					}, null, { timeout: 20000 });
					await page.locator('#maincontent button').filter({ hasText: language === 'en' ? 'Start test' : '开始测试' }).first().click();
					const expectedNote = language === 'en'
						? (scenario === 'validated' ? 'Test complete. The candidate was rolled back and health checks passed.' : 'Test complete, but the result was not validated. Review the details below.')
						: (scenario === 'validated' ? '测试已完成，候选项已回滚，健康检查通过。' : '测试已完成，但结果未通过验证。请查看下方详情。');
					try {
						await page.getByText(expectedNote, { exact: true }).waitFor({ state: 'visible', timeout: 20000 });
					}
					catch (error) {
						const diagnostic = {
							language, scenario, expectedNote, url: page.url(),
							mainText: await page.locator('#maincontent').innerText().catch(() => ''),
							observedRpc: fixtureState.observed,
							interceptedRpc: fixtureState.intercepted,
							postRequests,
							routePattern: rpcEndpointGlob,
							browserErrors
						};
						const stem = `debug-${language}-${scenario}`;
						fs.writeFileSync(path.join(output, stem + '.json'), JSON.stringify(diagnostic, null, 2) + '\n');
						await page.screenshot({ path: path.join(output, stem + '.png'), fullPage: true, animations: 'disabled' }).catch(() => {});
						console.error('BENCHMARK_RESULT_DIAGNOSTIC ' + JSON.stringify(diagnostic));
						throw error;
					}
					for (const width of selectedWidths) await capture(page, theme, scenario, width, 900);
					for (const viewport of selectedViewports) await capture(page, theme, scenario, viewport.width, viewport.height);
				}
			} finally { await context.close(); }
		}
	} finally { await browser.close(); }
	const expected = selectedThemes.length * selectedScenarios.length * (selectedWidths.length + selectedViewports.length);
	console.log('BENCHMARK_RESULT_MATRIX ' + JSON.stringify({ total: report.rows.length, expected, pass: report.rows.filter(x => x.result === 'PASS').length, fail: report.errors.length }));
	if (report.rows.length !== expected || report.errors.length) process.exitCode = 1;
})().catch(e => {
	report.errors.push({ fatal: e.stack || e.message });
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
	console.error(e);
	process.exitCode = 1;
});
