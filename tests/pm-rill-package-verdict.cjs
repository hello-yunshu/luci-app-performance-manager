'use strict';
// PM package actions must retire stale update verdicts and survive slow opkg.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const source = fs.readFileSync(process.env.PM_RILL_SOURCE || path.join(__dirname, '../package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/rill.js'), 'utf8');
const labelsSource = fs.readFileSync(path.join(__dirname, '../package/luci-app-performance-manager/htdocs/luci-static/resources/performance-manager/labels.js'), 'utf8');

if (!String.prototype.format) {
	String.prototype.format = function () {
		const args = Array.prototype.slice.call(arguments);
		return this.replace(/%[sd]/g, () => String(args.shift()))
			.replace(/\{(\d+)\}/g, (m, i) => (args[i] != null ? String(args[i]) : m));
	};
}

/* Exercise the real presentation dictionary instead of a hand-written mock.
 * A local mock made this test pass while the shipped labels mapped a refresh
 * to the generic "Package updated" notice, so it could not detect a wrong
 * action outcome. */
const realLabels = new Function('baseclass', '_', labelsSource)(
	{ extend: object => object },
	text => text
);

function E(tag, attrs, children) {
	const node = {
		tag, attrs: attrs || {}, children: [], listeners: {},
		addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
		appendChild(child) { this.children.push(child); return child; },
		replaceChildren(...items) { this.children = items.flat(); },
		setAttribute() {}, removeAttribute() {},
		classList: { add() {}, remove() {}, contains: () => false },
		get text() { return this.children.map(c => typeof c === 'string' ? c : (c && c.text ? c.text : '')).join(' '); }
	};
	for (const child of (Array.isArray(children) ? children : children == null ? [] : [children])) node.appendChild(child);
	return node;
}

function findButton(node, label) {
	if (!node || typeof node !== 'object') return null;
	if (node.attrs && node.attrs.type === 'button' && node.text.includes(label)) return node;
	for (const child of node.children || []) {
		const found = findButton(child, label);
		if (found) return found;
	}
	return null;
}

const flush = () => new Promise(resolve => setTimeout(resolve, 5));

function load(handlers) {
	const storage = new Map();
	const notices = [];
	const reloads = { count: 0 };
	const delays = [];
	const L = { env: { rpctimeout: 20 } };
	const window = {
		sessionStorage: {
			getItem: key => storage.has(key) ? storage.get(key) : null,
			setItem: (key, value) => storage.set(key, String(value)),
			removeItem: key => storage.delete(key)
		},
		setTimeout: (fn, ms) => { delays.push(ms || 0); fn(); return 0; },
		location: { reload() { reloads.count += 1; } },
		L
	};
	const pm = {
		runtimeManagerInstall: (...a) => handlers.install(...a),
		runtimeManagerRepair: (...a) => handlers.repair(...a),
		runtimeManagerRefresh: (...a) => handlers.refresh(...a),
		runtimeManagerUpdate: (...a) => handlers.update(...a),
		runtimeManagerStatus: (...a) => handlers.status(...a)
	};
	const pu = {
		page: (title, sub, body) => E('div', {}, body),
		note: (text, kind) => E('div', {}, text),
		field: (label, control, description) => E('div', {}, [label, control, description]),
		kv: rows => E('div', {}, rows.map(row => E('div', {}, row))),
		badge: (text, kind) => E('span', {}, text),
		grid: (...items) => E('div', {}, items),
		card: (...items) => E('div', {}, items),
		jsonBox: text => E('pre', {}, text),
		tableWrap: node => node,
		toolbar: (...items) => E('div', {}, items),
		setBusy: (button, label) => {
			button.busy = true;
			button.label = label;
			return function () { button.busy = false; button.label = null; };
		}
	};
	const labels = realLabels;
	const ui = { addNotification: (level, node, type) => notices.push({ level, text: node && node.text ? node.text : String(node), type }) };
	const body = source.replace(/^return view\.extend\(/m, 'const viewObject = view.extend(') +
		'\nreturn Object.assign({}, viewObject, { read: readRefreshRecord });';
	const api = new Function('view', 'ui', 'pm', 'pu', 'labels', 'E', '_', 'L', 'window', 'location', body)(
		{ extend: o => o }, ui, pm, pu, labels, E, x => x, L, window, window.location);
	const manager = {
		ok: true, supported: true, installed: true, channel: 'stable', compatible: true,
		updateAvailable: false, runtimeUpdateAvailable: false, pmUpdateAvailable: false,
		version: '1.5.6-r9'
	};
	return { api, manager, storage, notices, reloads, delays, L, window, render: extra => api.render([{}, Object.assign({}, manager, extra || {}), {}]) };
}

function seed(env, hasUpdate) {
	const at = Date.now() - 60000;
	env.storage.set('pm.rill.package-refresh', JSON.stringify({ at, hasUpdate }));
	return at;
}

async function click(env, label, extra) {
	const view = env.render(extra);
	const button = findButton(view, label);
	assert(button, 'button not found: ' + label);
	button.listeners.click[0]({});
	return button;
}

(async () => {
	{
		const env = load({});
		const seededAt = seed(env, true);
		env.render();
		const stored = JSON.parse(env.storage.get('pm.rill.package-refresh'));
		assert.equal(stored.hasUpdate, false,
			'page load must retire a stale verdict when the manager reports no pending update');
		assert.equal(stored.at, seededAt,
			'retiring a stale verdict on page load must keep the original check time');
	}

	{
		const env = load({
			update: () => Promise.resolve({ ok: true }),
			status: () => Promise.resolve({ ok: true, busy: false, updateAvailable: false, runtimeUpdateAvailable: false, pmUpdateAvailable: false }),
			refresh: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true })
		});
		seed(env, true);
		const button = await click(env, 'Update Rill Runtime', { runtimeUpdateAvailable: true });
		await flush();
		assert.equal(JSON.parse(env.storage.get('pm.rill.package-refresh')).hasUpdate, false,
			'a completed update must rewrite the stored verdict');
		assert.equal(env.reloads.count, 1);
		assert.equal(button.busy, false);
		assert.equal(env.delays.some(ms => ms >= 1000), true,
			'the reload must be deferred so the outcome notice stays readable');
		assert.equal(realLabels.managerActionOutcome('update'), 'Package updated',
			'a package update must keep the generic update outcome');
		assert.equal(env.notices.some(n => n.text === 'Package updated'), true,
			'a completed update must report its outcome through the shipped labels mapper');
	}

	{
		/* One running package action must lock every package action, not just
		 * the clicked one: opkg serialises transactions on the router, so a
		 * second click would queue a duplicate job. */
		let release;
		const pending = new Promise(resolve => { release = resolve; });
		const env = load({
			update: () => pending,
			status: () => Promise.resolve({ ok: true, busy: false, updateAvailable: false, runtimeUpdateAvailable: false, pmUpdateAvailable: false }),
			refresh: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true })
		});
		const view = env.render({ runtimeUpdateAvailable: true, pmUpdateAvailable: true });
		const updateButton = findButton(view, 'Update Rill Runtime');
		const pmButton = findButton(view, 'Update Performance Manager');
		assert(updateButton && pmButton, 'both package action buttons must render');
		updateButton.listeners.click[0]({});
		await flush();
		assert.equal(pmButton.disabled, true,
			'a running package action must disable the other package actions');
		release({ ok: true });
		await flush();
		assert.equal(pmButton.disabled, false,
			'other package actions must come back once the action finishes');
		assert.equal(env.reloads.count, 1);
	}

	{
		/* A status read that fails is not proof of an idle manager. */
		const env = load({
			update: () => Promise.reject(new Error('XHR request timed out')),
			status: () => Promise.resolve({ ok: false, busy: false }),
			refresh: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true })
		});
		const button = await click(env, 'Update Rill Runtime', { runtimeUpdateAvailable: true });
		await flush();
		assert.equal(env.reloads.count, 0,
			'an unreadable status must not reload as if the manager were idle');
		assert.equal(button.busy, true,
			'an unverified action must stay locked');
		assert(env.notices.some(n => /status could not be read/.test(String(n.text))),
			'the notice must say the status could not be read');
	}

	{
		const env = load({
			update: () => { assert.equal(env.L.env.rpctimeout, 120); return Promise.reject(new Error('XHR request timed out')); },
			status: (() => { let n = 0; return () => Promise.resolve(++n === 1 ? { busy: true, ok: true } : { ok: true, busy: false, updateAvailable: false, runtimeUpdateAvailable: false, pmUpdateAvailable: false }); })(),
			refresh: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true })
		});
		seed(env, true);
		const button = await click(env, 'Update Rill Runtime', { runtimeUpdateAvailable: true });
		await flush();
		assert.equal(env.L.env.rpctimeout, 20, 'client deadline must be restored');
		assert.equal(JSON.parse(env.storage.get('pm.rill.package-refresh')).hasUpdate, false);
		assert.equal(env.notices.some(n => n.type === 'warning' && /timed out, but the manager is now idle/.test(n.text)), true);
		assert.equal(env.reloads.count, 1);
		assert.equal(button.busy, false);
	}

	{
		const env = load({
			update: () => Promise.reject(new Error('XHR request timed out')),
			status: () => Promise.resolve({ busy: true, ok: true }),
			refresh: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true })
		});
		seed(env, true);
		const button = await click(env, 'Update Rill Runtime', { runtimeUpdateAvailable: true });
		await flush();
		assert.equal(env.storage.has('pm.rill.package-refresh'), false, 'unverified action must drop the stale verdict');
		assert.equal(env.notices.some(n => n.type === 'error' && /still busy/.test(n.text)), true);
		assert.equal(button.busy, true, 'an unverified action must keep the button disabled');
		assert.equal(env.reloads.count, 0);
	}

	{
		const env = load({
			refresh: () => Promise.resolve({ ok: true, updateAvailable: true }),
			update: () => Promise.resolve({ ok: true }), install: () => Promise.resolve({ ok: true }), repair: () => Promise.resolve({ ok: true }),
			status: () => Promise.resolve({ ok: true, updateAvailable: false })
		});
		await click(env, 'Check for updates');
		await flush();
		assert.equal(JSON.parse(env.storage.get('pm.rill.package-refresh')).hasUpdate, true,
			'refresh must still store its own feed verdict');
		assert.equal(realLabels.managerActionOutcome('refresh'), 'Package index refreshed',
			'a feed refresh must not be reported as a package update');
		assert.equal(env.notices.some(n => n.text === 'Package index refreshed'), true,
			'refresh must report its own index-refresh outcome');
		assert.equal(env.notices.some(n => n.text === 'Package updated'), false,
			'refresh must not claim that packages were updated');
	}

	console.log('PASS PM package verdicts retire after actions and slow manager RPCs verify before failing');
})().catch(error => { console.error(error); process.exitCode = 1; });
