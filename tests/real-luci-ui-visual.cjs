'use strict';
/* Real OpenWrt/LuCI route and responsive screenshot matrix. Screenshots still
 * require human visual review; this script only checks load, assets, overflow,
 * truncation, headings and browser errors. */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const base = process.env.PM_UI_BASE || 'http://127.0.0.1:18080';
const container = process.env.PM_UI_CONTAINER || 'pm-ui-gate';
const password = process.env.PM_UI_PASSWORD || 'pm-gate';
const output = process.env.PM_VISUAL_OUT || path.join(process.cwd(), 'real-luci-ui-evidence');
const language = process.env.PM_UI_LANG || 'en';
const langIndex = language === 'en' ? 0 : language === 'zh_cn' ? 1 : -1;
if (langIndex < 0) throw new Error('Unsupported PM_UI_LANG: ' + language);

const routes = [
	{ path: 'overview', id: 'overview', title: ['Performance Manager', '性能管理器'] },
	{ path: 'optimize', id: 'optimize', title: ['Smart optimization', '智能优化'] },
	{ path: 'benchmark', id: 'benchmark', title: ['Performance test', '性能测试'] },
	{ path: 'capabilities', id: 'capabilities', title: ['Capabilities', '能力'] },
	{ path: 'rill', id: 'rill', title: ['Rill smart decisions', 'Rill 智能决策'] },
	{ path: 'history', id: 'history', title: ['History and rollback', '历史与回滚'] },
	{ path: 'settings', id: 'settings', title: ['Settings', '设置'] },
	{ path: 'advanced', id: 'advanced', title: ['Advanced', '高级'] }
];
const commonWidths = [320, 360, 375, 390, 430, 640, 768, 1024, 1280, 1440, 1920];
const breakpoints = [600, 700, 768, 900, 991, 1048, 1100, 1200, 1280, 1319];
const allWidths = [...new Set([...commonWidths, ...breakpoints.flatMap(w => [w - 1, w, w + 1])])].sort((a, b) => a - b);
const shortViewports = [{ width: 320, height: 568 }, { width: 568, height: 320 }];
const themes = [
	{ id: 'bootstrap-default-light', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'light', dark: 'false' },
	{ id: 'bootstrap-default-dark', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'dark', dark: 'true' },
	{ id: 'bootstrap-light', media: 'bootstrap', theme: 'bootstrap-light', colorScheme: 'light', dark: 'false' },
	{ id: 'bootstrap-dark', media: 'bootstrap', theme: 'bootstrap-dark', colorScheme: 'dark', dark: 'true' },
	{ id: 'aurora-light', media: 'aurora', theme: 'aurora', colorScheme: 'light', dark: 'false', aurora: 'light' },
	{ id: 'aurora-dark', media: 'aurora', theme: 'aurora', colorScheme: 'dark', dark: 'true', aurora: 'dark' }
];
const smoke = process.env.PM_UI_SMOKE_ONLY === '1';
if (smoke && process.env.GITHUB_ACTIONS === 'true') throw new Error('Smoke-only mode is prohibited in GitHub Actions');
const selectedThemes = smoke ? themes.filter(t => t.id === 'aurora-light') : themes;
const selectedWidths = smoke ? [320, 1280] : allWidths;

const report = {
	schemaVersion: 1,
	sha: process.env.GITHUB_SHA || 'unknown',
	environment: 'OpenWrt 24.10.8 rootfs with LuCI, uhttpd, rpcd, Performance Manager and Chromium',
	language, mode: smoke ? 'local-smoke-only' : 'full-matrix',
	routes: routes.map(r => r.path), widths: selectedWidths, shortViewports,
	method: 'All 8 registered views; common and breakpoint-adjacent CSS widths; short portrait and landscape; Bootstrap system/default, explicit Light/Dark, Aurora Light/Dark.',
	notCovered: ['manual visual review', 'controlled A/B apply and restore lifecycle', 'business mutations outside health/passive benchmark observations', 'installed router behavior'], rows: [], errors: []
};
fs.mkdirSync(output, { recursive: true });

function shell(cmd) {
	return execFileSync('docker', ['exec', container, 'sh', '-c', cmd], { encoding: 'utf8' }).trim();
}

async function login(page) {
	await page.goto(base + '/cgi-bin/luci/', { waitUntil: 'domcontentloaded' });
	const username = page.locator('input[name="luci_username"]');
	if (await username.count()) {
		await username.fill('root');
		await page.locator('input[name="luci_password"]').fill(password);
		const submit = page.locator('button[type="submit"], input[type="submit"]').first();
		if (await submit.count()) await submit.click(); else await page.locator('input[name="luci_password"]').press('Enter');
	}
	await page.waitForTimeout(800);
	if (await page.locator('input[name="luci_password"]').count()) throw new Error('LuCI login failed');
}

async function capture(page, theme, route, width, height, viewId) {
	const suffix = height === 900 ? `${width}` : `${width}x${height}`;
	const fileName = `${theme.id}-${suffix}-${viewId}.png`;
	const file = path.join(output, fileName);
	const browserErrors = [];
	const onConsole = m => { if (m.type() === 'error') browserErrors.push(m.text()); };
	const onPageError = e => browserErrors.push('PAGE_ERROR ' + e.message);
	page.on('console', onConsole); page.on('pageerror', onPageError);
	let metrics = null, navigationError = null;
	try {
		await page.setViewportSize({ width, height });
		await page.goto(base + '/cgi-bin/luci/admin/services/performance-manager/' + route.path, { waitUntil: 'domcontentloaded', timeout: 30000 });
		await page.waitForFunction(() => {
			const main = document.querySelector('#maincontent');
			return main && main.innerText.trim().length > 10 && !/Loading view|加载视图/.test(main.innerText);
		}, null, { timeout: 20000 });
		await page.waitForTimeout(350);
		metrics = await page.evaluate(({ media, viewId }) => {
			const root = document.documentElement, main = document.querySelector('#maincontent');
			const heading = main && main.querySelector('h2[name="content"], .view h2, h2');
			const resources = Array.from(document.querySelectorAll('link[href],script[src]')).map(el => el.href || el.src);
			const truncated = Array.from((main || document).querySelectorAll('*')).filter(el => {
				if (/^(INPUT|TEXTAREA|SELECT|CAPTION)$/.test(el.tagName) || el.closest('.cbi-dropdown, #tabmenu')) return false;
				const css = getComputedStyle(el);
				return css.whiteSpace === 'nowrap' && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2;
			}).slice(0, 8).map(el => ({ tag: el.tagName, text: (el.innerText || '').trim().slice(0, 80) }));
			const overviewBadges = main
				? Array.from(main.querySelectorAll('.pm-overview-status .label')).map(el => el.getClientRects().length)
				: [];
			const benchmarkSelect = viewId === 'benchmark' && main && main.querySelector('.pm-benchmark-select');
			const benchmarkField = benchmarkSelect && benchmarkSelect.closest('.pm-benchmark-field');
			const benchmarkSelectRect = benchmarkSelect && benchmarkSelect.getBoundingClientRect();
			const benchmarkFieldRect = benchmarkField && benchmarkField.getBoundingClientRect();
			const benchmarkSelectFits = !benchmarkSelect || !!(benchmarkSelectRect && benchmarkFieldRect &&
				benchmarkSelectRect.left >= benchmarkFieldRect.left - 1 &&
				benchmarkSelectRect.right <= benchmarkFieldRect.right + 1 &&
				benchmarkSelectRect.right <= innerWidth + 1);
			return {
				heading: heading ? heading.textContent.trim() : '',
				hasMain: !!main, mainLength: (main && main.innerText || '').trim().length,
				loading: !!(main && /Loading view|加载视图/.test(main.innerText)),
				darkMode: root.getAttribute('data-darkmode'), scrollWidth: root.scrollWidth, width: innerWidth,
				overflow: root.scrollWidth > innerWidth + 1,
				benchmarkSelectFits,
				overviewBadgesIntact: !overviewBadges.length || overviewBadges.every(rects => rects === 1),
				themeLoaded: resources.some(src => src.includes('/luci-static/' + media + '/')),
				pluginCssLoaded: resources.some(src => src.includes('performance-manager/ui.css')),
				tabMenu: (() => {
					const menu = document.querySelector('#tabmenu');
					if (!menu) return null;
					const items = Array.from(menu.querySelectorAll('a')).map(a => {
						const r = a.getBoundingClientRect();
						return { label: a.textContent.trim(), active: !!a.closest('li.active, [aria-current="page"]'), left: Math.round(r.left), right: Math.round(r.right),
							visible: r.width > 0 && r.height > 0 && r.left >= -1 && r.right <= innerWidth + 1 };
					});
					return { count: items.length, visibleCount: items.filter(x => x.visible).length, items,
						activeItems: items.filter(x => x.active),
						clientWidth: menu.clientWidth, scrollWidth: menu.scrollWidth,
						horizontalOverflow: menu.scrollWidth > menu.clientWidth + 1 };
				})(),
				rillHeaders: viewId === 'rill' ? Array.from(main ? main.querySelectorAll('.pu-table-scroll table thead tr') : []).map(row => ({
					native: row.classList.contains('cbi-section-table-titles'), visible: getComputedStyle(row).display !== 'none'
				})) : null,
				truncated
			};
		}, { media: theme.media, viewId });
		await page.screenshot({ path: file, fullPage: true, animations: 'disabled' });
		if (height < 900) {
			const viewportFile = file.replace(/\.png$/, '-viewport.png');
			await page.screenshot({ path: viewportFile, fullPage: false, animations: 'disabled' });
			var viewportScreenshot = path.basename(viewportFile);
		}
	} catch (e) { navigationError = e.message; }
	finally { page.off('console', onConsole); page.off('pageerror', onPageError); }
	const failures = [];
	if (navigationError) failures.push('navigation-or-render: ' + navigationError);
	if (metrics) {
		if (!metrics.hasMain || metrics.mainLength < 10 || metrics.loading) failures.push('blank-or-loading-view');
		if (!metrics.themeLoaded) failures.push('theme-assets-not-loaded');
		if (!metrics.pluginCssLoaded) failures.push('plugin-css-not-loaded');
		if (metrics.overflow) failures.push('horizontal-overflow');
		if (route.id === 'benchmark' && width <= 600 && !metrics.benchmarkSelectFits) failures.push('benchmark-action-select-exceeds-available-width');
		if (!metrics.overviewBadgesIntact) failures.push('overview-status-badge-split-across-lines');
		if (metrics.tabMenu && metrics.tabMenu.activeItems.some(x => !x.visible)) failures.push('active-tab-outside-visible-strip');
		if (!metrics.tabMenu || metrics.tabMenu.count !== routes.length || metrics.tabMenu.visibleCount !== metrics.tabMenu.count) failures.push('route-tab-outside-visible-strip');
		// The feedback table is mounted only after its collapsed details section opens.
		if (route.id === 'rill' && (!metrics.rillHeaders || metrics.rillHeaders.length < 1 || metrics.rillHeaders.length > 2 || metrics.rillHeaders.some(row => !row.native) || (width <= 600 && metrics.rillHeaders.some(row => row.visible)))) failures.push('rill-table-headers-not-native-or-count-unexpected');
		if (metrics.truncated.length) failures.push('truncated-non-dropdown-text');
		if (metrics.darkMode !== theme.dark) failures.push('theme-dark-mode-mismatch');
		if (metrics.heading !== route.title[langIndex]) failures.push('wrong-view-heading: ' + metrics.heading);
	}
	if (browserErrors.length) failures.push('browser-errors');
	const row = {
		theme: theme.id, language, route: 'admin/services/performance-manager/' + route.path,
		view: viewId, viewport: `${width}x${height}`, result: failures.length ? 'FAIL' : 'PASS',
		failures, metrics, screenshot: fileName, viewportScreenshot: typeof viewportScreenshot === 'undefined' ? undefined : viewportScreenshot, browserErrors: browserErrors.slice(0, 8)
	};
	report.rows.push(row);
	if (failures.length) report.errors.push({ route: row.route, theme: theme.id, viewport: row.viewport, failures, browserErrors: browserErrors.slice(0, 8) });
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
	console.log(`${row.result} ${theme.id} ${row.viewport} ${viewId}${failures.length ? ' -- ' + failures.join(', ') : ''}`);
}

async function captureBenchmarkScenario(page, theme, mode, scenarioId, width, height) {
	const suffix = height === 900 ? `${width}` : `${width}x${height}`;
	const fileName = `${theme.id}-${suffix}-benchmark-${scenarioId}.png`;
	const file = path.join(output, fileName);
	const expectedNote = language === 'en'
		? (mode === 'health_only' ? 'Health snapshot captured. This is not a performance result.' : 'Passive observation captured. No settings were changed.')
		: (mode === 'health_only' ? '已采集健康状态；这不是性能测试结果。' : '已完成被动观测；没有修改任何设置。');
	const failures = [];
	let metrics = null;
	try {
		await page.setViewportSize({ width, height });
		metrics = await page.evaluate(({ expectedNote, media }) => {
			const root = document.documentElement;
			const main = document.querySelector('#maincontent');
			const stages = main && main.querySelector('.pm-stage-list');
			const stageText = stages ? stages.innerText : '';
			const noteTexts = Array.from(main ? main.querySelectorAll('.alert-message') : []).map(el => el.innerText.trim());
			const sessionJson = Array.from(main ? main.querySelectorAll('.pm-disclosure pre') : []).map(el => el.textContent)
				.map(text => { try { return JSON.parse(text); } catch (_) { return null; } })
				.find(value => value && value.sessionId);
			const benchmarkSelect = main && main.querySelector('.pm-benchmark-select');
			const selectField = benchmarkSelect && benchmarkSelect.closest('.pm-benchmark-field');
			const selectRect = benchmarkSelect && benchmarkSelect.getBoundingClientRect();
			const fieldRect = selectField && selectField.getBoundingClientRect();
			const resources = Array.from(document.querySelectorAll('link[href],script[src]')).map(el => el.href || el.src);
			return {
				hasMain: !!main,
				noteVisible: noteTexts.includes(expectedNote),
				stageText,
				loading: !!(main && /Loading view|加载视图/.test(main.innerText)),
				overflow: root.scrollWidth > innerWidth + 1,
				benchmarkSelectFits: !benchmarkSelect || !!(selectRect && fieldRect && selectRect.left >= fieldRect.left - 1 && selectRect.right <= fieldRect.right + 1 && selectRect.right <= innerWidth + 1),
				themeLoaded: resources.some(src => src.includes('/luci-static/' + media + '/')),
				pluginCssLoaded: resources.some(src => src.includes('performance-manager/ui.css')),
				session: sessionJson ? { state: sessionJson.state, measurementClass: sessionJson.measurementClass, changedSystemState: sessionJson.result?.changedSystemState } : null
			};
		}, { expectedNote, media: theme.media });
		await page.screenshot({ path: file, fullPage: true, animations: 'disabled' });
		if (height < 900) {
			const viewportFile = file.replace(/\.png$/, '-viewport.png');
			await page.screenshot({ path: viewportFile, fullPage: false, animations: 'disabled' });
		}
	} catch (e) {
		failures.push('navigation-or-render: ' + e.message);
	}
	if (metrics) {
		if (!metrics.hasMain || metrics.loading) failures.push('blank-or-loading-view');
		if (!metrics.noteVisible) failures.push('scenario-result-note-missing');
		if (!metrics.stageText.includes(mode === 'health_only' ? (language === 'en' ? 'Health snapshot' : '健康快照') : (language === 'en' ? 'Passive observation' : '被动观察'))) failures.push('scenario-stage-label-missing');
		const forbiddenStages = language === 'en' ? ['Baseline', 'Candidate', 'Commit-confirm'] : ['基线', '候选项', '提交确认'];
		if (forbiddenStages.some(stage => metrics.stageText.includes(stage))) failures.push('irrelevant-controlled-ab-stage-visible');
		if (!metrics.session || metrics.session.state !== 'completed' || metrics.session.measurementClass !== mode) failures.push('scenario-session-state-invalid');
		if (!metrics.session || metrics.session.changedSystemState !== false) failures.push('scenario-mutated-system-state');
		if (!metrics.themeLoaded) failures.push('theme-assets-not-loaded');
		if (!metrics.pluginCssLoaded) failures.push('plugin-css-not-loaded');
		if (metrics.overflow) failures.push('horizontal-overflow');
		if (width <= 600 && !metrics.benchmarkSelectFits) failures.push('benchmark-action-select-exceeds-available-width');
	}
	const row = {
		theme: theme.id, language, route: 'admin/services/performance-manager/benchmark', view: 'benchmark', scenario: scenarioId,
		viewport: `${width}x${height}`, result: failures.length ? 'FAIL' : 'PASS', failures, metrics, screenshot: fileName
	};
	report.rows.push(row);
	if (failures.length) report.errors.push({ route: row.route, theme: theme.id, viewport: row.viewport, scenario: scenarioId, failures });
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
	console.log(`${row.result} ${theme.id} ${row.viewport} benchmark-${scenarioId}${failures.length ? ' -- ' + failures.join(', ') : ''}`);
}

async function runBenchmarkScenario(page, theme, mode, scenarioId) {
	await page.setViewportSize({ width: 1280, height: 900 });
	await page.goto(base + '/cgi-bin/luci/admin/services/performance-manager/benchmark', { waitUntil: 'domcontentloaded', timeout: 30000 });
	await page.waitForFunction(() => {
		const main = document.querySelector('#maincontent');
		return main && main.innerText.trim().length > 10 && !/Loading view|加载视图/.test(main.innerText);
	}, null, { timeout: 20000 });
	await page.locator('.pm-benchmark-select').nth(2).selectOption(mode);
	const startLabel = language === 'en' ? 'Start test' : '开始测试';
	await page.locator('#maincontent button').filter({ hasText: startLabel }).first().click();
	const expectedNote = language === 'en'
		? (mode === 'health_only' ? 'Health snapshot captured. This is not a performance result.' : 'Passive observation captured. No settings were changed.')
		: (mode === 'health_only' ? '已采集健康状态；这不是性能测试结果。' : '已完成被动观测；没有修改任何设置。');
	await page.getByText(expectedNote, { exact: true }).waitFor({ state: 'visible', timeout: 20000 });
	await page.waitForTimeout(250);
	for (const width of selectedWidths) await captureBenchmarkScenario(page, theme, mode, scenarioId, width, 900);
	for (const viewport of shortViewports) await captureBenchmarkScenario(page, theme, mode, scenarioId, viewport.width, viewport.height);
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
				await login(page);
				for (const width of selectedWidths) for (const route of routes) await capture(page, theme, route, width, 900, route.id);
				for (const viewport of shortViewports) for (const route of routes) await capture(page, theme, route, viewport.width, viewport.height, route.id);
				for (const scenario of [
					{ mode: 'health_only', id: 'health-only' },
					{ mode: 'passive_before_after', id: 'passive-before-after' }
				]) await runBenchmarkScenario(page, theme, scenario.mode, scenario.id);
			} finally { await context.close(); }
		}
	} finally { await browser.close(); }
	const expected = selectedThemes.length * ((selectedWidths.length + shortViewports.length) * routes.length + 2 * (selectedWidths.length + shortViewports.length));
	console.log('VISUAL_MATRIX ' + JSON.stringify({ total: report.rows.length, expected, pass: report.rows.filter(x => x.result === 'PASS').length, fail: report.errors.length }));
	if (report.rows.length !== expected || report.errors.length) process.exitCode = 1;
})().catch(e => {
	report.errors.push({ fatal: e.stack || e.message });
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
	console.error(e);
	process.exitCode = 1;
});
