'use strict';
/* Focused visual matrix for the Overview summary-card breakpoint. */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const base = process.env.PM_UI_BASE || 'http://127.0.0.1:18080';
const container = process.env.PM_UI_CONTAINER || 'pm-ui-gate';
const password = process.env.PM_UI_PASSWORD || 'pm-gate';
const output = process.env.PM_BREAKPOINT_OUT || path.join(process.cwd(), 'overview-breakpoint-evidence');
const language = process.env.PM_UI_LANG || 'en';
if (!['en', 'zh_cn'].includes(language)) throw new Error('Unsupported PM_UI_LANG: ' + language);

const themes = [
	{ id: 'bootstrap-default-light', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'light', dark: 'false' },
	{ id: 'bootstrap-default-dark', media: 'bootstrap', theme: 'bootstrap', colorScheme: 'dark', dark: 'true' },
	{ id: 'bootstrap-light', media: 'bootstrap', theme: 'bootstrap-light', colorScheme: 'light', dark: 'false' },
	{ id: 'bootstrap-dark', media: 'bootstrap', theme: 'bootstrap-dark', colorScheme: 'dark', dark: 'true' },
	{ id: 'aurora-light', media: 'aurora', theme: 'aurora', colorScheme: 'light', dark: 'false', aurora: 'light' },
	{ id: 'aurora-dark', media: 'aurora', theme: 'aurora', colorScheme: 'dark', dark: 'true', aurora: 'dark' }
];
const widths = [431, 432, 433];
const report = { schemaVersion: 1, sha: process.env.GITHUB_SHA || 'unknown', language,
	method: 'Real LuCI Overview screenshots at 431/432/433px, adjacent to the 27rem summary-card grid breakpoint; six supported theme modes.',
	widths, rows: [], errors: [] };
fs.mkdirSync(output, { recursive: true });

function shell(command) {
	return execFileSync('docker', ['exec', container, 'sh', '-c', command], { encoding: 'utf8' }).trim();
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

(async () => {
	const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE || undefined });
	try {
		for (const theme of themes) {
			shell(`uci set luci.main.mediaurlbase='/luci-static/${theme.media}'; uci set luci.main.theme='${theme.theme}'; uci commit luci; rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache*; /etc/init.d/uhttpd restart >/dev/null 2>&1`);
			await new Promise(resolve => setTimeout(resolve, 800));
			const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: theme.colorScheme });
			if (theme.aurora) await context.addInitScript(mode => localStorage.setItem('aurora.theme', mode), theme.aurora);
			const page = await context.newPage();
			const browserErrors = [];
			page.on('console', message => { if (message.type() === 'error') browserErrors.push(message.text()); });
			page.on('pageerror', error => browserErrors.push('PAGE_ERROR ' + error.message));
			try {
				await login(page);
				for (const width of widths) {
					const screenshot = `${theme.id}-${width}-overview-breakpoint.png`;
					const failures = [];
					await page.setViewportSize({ width, height: 900 });
					await page.goto(base + '/cgi-bin/luci/admin/network/performance-manager/overview', { waitUntil: 'domcontentloaded', timeout: 30000 });
					await page.waitForFunction(() => {
						const main = document.querySelector('#maincontent');
						return main && main.querySelector('.pm-overview-stats > .pm-overview-stat-card');
					}, null, { timeout: 20000 });
					await page.waitForTimeout(350);
					const metrics = await page.evaluate(({ media, expectedColumns, dark }) => {
						const root = document.documentElement;
						const grid = document.querySelector('#maincontent .pm-overview-stats');
						const cards = grid ? Array.from(grid.querySelectorAll(':scope > .pm-overview-stat-card')) : [];
						const columns = grid ? getComputedStyle(grid).gridTemplateColumns.trim().split(/\s+/).length : 0;
						const labels = cards.flatMap(card => Array.from(card.querySelectorAll('.pm-overview-stat-label, .pm-overview-stat-value')).map(el => ({
							text: el.textContent.trim(), width: Math.round(el.getBoundingClientRect().width), scrollWidth: el.scrollWidth,
							overflowWrap: getComputedStyle(el).overflowWrap, wordBreak: getComputedStyle(el).wordBreak
						})));
						const resources = Array.from(document.querySelectorAll('link[href],script[src]')).map(el => el.href || el.src);
						return { columns, expectedColumns, cardCount: cards.length, labels,
							horizontalOverflow: root.scrollWidth > innerWidth + 1, scrollWidth: root.scrollWidth,
							darkMode: root.getAttribute('data-darkmode'), expectedDarkMode: dark,
							themeLoaded: resources.some(src => src.includes('/luci-static/' + media + '/')),
							pluginCssLoaded: resources.some(src => src.includes('performance-manager/ui.css')) };
					}, { media: theme.media, expectedColumns: width < 432 ? 1 : 2, dark: theme.dark });
					if (metrics.columns !== metrics.expectedColumns) failures.push('unexpected-grid-column-count');
					if (metrics.cardCount !== 4) failures.push('expected-four-summary-cards');
					if (metrics.horizontalOverflow) failures.push('horizontal-overflow');
					if (metrics.darkMode !== metrics.expectedDarkMode) failures.push('theme-mode-mismatch');
					if (!metrics.themeLoaded || !metrics.pluginCssLoaded) failures.push('theme-or-plugin-css-not-loaded');
				if (metrics.labels.some(label => label.scrollWidth > label.width + 1 || label.overflowWrap !== 'normal' || label.wordBreak !== 'normal')) failures.push('summary-label-overflow-or-forced-word-break');
					await page.screenshot({ path: path.join(output, screenshot), fullPage: true, animations: 'disabled' });
					const row = { theme: theme.id, language, width, height: 900, screenshot, result: failures.length ? 'FAIL' : 'PASS', failures, metrics, browserErrors: browserErrors.splice(0, 8) };
					if (row.browserErrors.length) { row.result = 'FAIL'; row.failures.push('browser-errors'); }
					report.rows.push(row);
					if (failures.length) report.errors.push({ theme: theme.id, width, failures: row.failures });
					fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
					console.log(`${row.result} ${theme.id} ${width}px columns=${metrics.columns}${row.failures.length ? ' -- ' + row.failures.join(', ') : ''}`);
				}
			} finally { await context.close(); }
		}
	} finally { await browser.close(); }
	console.log('OVERVIEW_BREAKPOINT_MATRIX ' + JSON.stringify({ total: report.rows.length, expected: themes.length * widths.length, pass: report.rows.filter(row => row.result === 'PASS').length, fail: report.errors.length }));
	if (report.rows.length !== themes.length * widths.length || report.errors.length) process.exitCode = 1;
})().catch(error => {
	report.errors.push({ fatal: error.stack || error.message });
	fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
	console.error(error);
	process.exitCode = 1;
});
