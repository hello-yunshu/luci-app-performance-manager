#!/usr/bin/env node
'use strict';
/*
 * LuCI render smoke harness (host-side, non-compiling).
 *
 * This is NOT a syntax check: it loads each view's `render()` against a real
 * (mock) payload and asserts it does not throw, then exercises the Benchmark
 * view's interactive graph (action switch -> path selector rebuild) to prove
 * there is no temporal-dead-zone or missing-element runtime crash.
 *
 * The LuCI runtime is mimicked with a tiny fake DOM (`E`, element with
 * appendChild/replaceChildren/addEventListener/value) so render logic executes
 * for real; only the browser rendering layer is replaced.
 */
const fs = require('fs');
const path = require('path');

const RES = path.join(__dirname, '..', 'package', 'luci-app-performance-manager', 'htdocs', 'luci-static', 'resources');
const VIEW_DIR = path.join(RES, 'view', 'performance-manager');

/* ---------- minimal fake DOM ---------- */
class FakeEl {
  constructor(tag, attrs, children) {
    this.tag = tag;
    this.attrs = attrs || {};
    this.children = [];
    this._listeners = {};
    this.disabled = false;
    this.style = {};
    if (this.attrs.class) this.class = this.attrs['class'];
    (children || []).forEach((c) => this.appendChild(c));
  }
  get value() { return this._value !== undefined ? this._value : (this.options.length ? this.options[0].attrs.value : ''); }
  set value(v) { this._value = v; }
  appendChild(c) { if (c != null) this.children.push(c); return c; }
  replaceChildren(...nodes) { this.children = []; nodes.forEach((n) => this.appendChild(n)); }
  addEventListener(evt, fn) { (this._listeners[evt] = this._listeners[evt] || []).push(fn); }
  dispatch(evt) { (this._listeners[evt] || []).forEach((fn) => fn({})); }
  get options() { return this.children.filter((c) => c.tag === 'option'); }
  get textContent() { return this.children.map((c) => (typeof c === 'string' ? c : c.textContent)).join(''); }
}

function E(a, b, c) {
  if (Array.isArray(a)) return new FakeEl('#fragment', null, b || []);
  return new FakeEl(a, b, c);
}
/* LuCI's `_()` returns a string whose `.format()` substitutes %s / {n}. */
String.prototype.format = function () {
  const args = Array.prototype.slice.call(arguments);
  return this.replace(/%[sd]/g, () => String(args.shift()))
             .replace(/\{(\d+)\}/g, (m, i) => (args[i] != null ? String(args[i]) : m));
};
function _(s) { return s; }

/* ---------- element search helper ---------- */
function byAria(root, label) {
  if (!root) return null;
  if (root.attrs && root.attrs['aria-label'] === label) return root;
  for (const c of root.children || []) {
    if (typeof c === 'string') continue;
    const hit = byAria(c, label);
    if (hit) return hit;
  }
  return null;
}

function byClass(root, className) {
  if (!root) return null;
  if (root.attrs && String(root.attrs.class || '').split(/\s+/).includes(className)) return root;
  for (const c of root.children || []) {
    if (typeof c === 'string') continue;
    const hit = byClass(c, className);
    if (hit) return hit;
  }
  return null;
}

/* ---------- LuCI module shims ---------- */
function stripRequires(body) {
  return body.split('\n').filter((l) => !/^\s*'require\s/.test(l) && !/^\s*'use strict';?/.test(l)).join('\n');
}

function loadModule(file, globals) {
  const src = stripRequires(fs.readFileSync(file, 'utf8'));
  const keys = Object.keys(globals);
  const vals = Object.values(globals);
  const body = `return (function(){ ${src}\n})();`;
  // eslint-disable-next-line no-new-func
  return new Function(...keys, `"use strict"; ${body}`)(...vals);
}

/* Minimal `form` (settings view) — only the surface used by the view runs. */
function Opt() { this.value = function () {}; this.depends = function () {}; this.default = null; this.readonly = false; this.disabled = false; this.enabled = false; }
function Sec() { this.option = function () { return new Opt(); }; }
const form = {
  Map: function () { this.section = function () { return new Sec(); }; this.render = function () { return E('form'); }; },
  NamedSection: Symbol('NamedSection'), Flag: Symbol('Flag'), ListValue: Symbol('ListValue'), Value: Symbol('Value'),
};

const rpc = { declare: (d) => () => Promise.resolve({ ok: false, error: 'rpc-unavailable-in-smoke' }) };
const pm = { status: rpc.declare({}), capabilities: rpc.declare({}), topology: rpc.declare({}),
  recommendations: rpc.declare({}), transactions: rpc.declare({}), locks: rpc.declare({}),
  history: rpc.declare({}), rill: rpc.declare({}), diagnostics: rpc.declare({}), apply: rpc.declare({}),
  rillRefresh: rpc.declare({}),
  confirm: rpc.declare({}), rollback: rpc.declare({}), benchmarkStart: rpc.declare({}),
  benchmarkStatus: rpc.declare({}), benchmarkStop: rpc.declare({}) };
const ui = { addNotification: () => {} };
const view = { extend: (o) => o };
const puModule = loadModule(path.join(RES, 'performance-manager', 'ui.js'), { E, _ });
const pu = puModule;

const baseGlobals = { E, _, view, ui, pu, pm, rpc, form, JSON, Object, Array, String, Number };

/* ---------- mock backend payloads ---------- */
const mockRec = {
  benchmarkActions: [
    { id: 'network.backlog', status: 'ready', evaluationSemantics: 'device-pinned backlog', evaluationPaths: ['path:lan-to-wan', 'path:local-endpoint'] },
    { id: 'tcp.cc', status: 'ready', evaluationSemantics: 'cubic-to-bbr', evaluationPaths: ['path:lan-to-wan'] },
    { id: 'qdisc.replace', status: 'blocked', evaluationSemantics: 'blocked', evaluationPaths: [] },
  ],
};
const mockStatus = { version: '1.0.0-rc', running: true, rill: { state: 'unavailable', reason: 'external-runtime-missing' } };
const mockTopology = { paths: [{ id: 'path:lan-to-wan', workloadClass: ['plain_forwarding'], lanInterface: 'lan', wanInterface: 'wan', routeResolved: true }] };

let failures = 0;
function expect(name, fn) {
  try {
    fn();
    console.log('ok  - ' + name);
  } catch (e) {
    failures++;
    console.error('FAIL- ' + name + ': ' + (e && e.stack ? e.stack : e));
  }
}

/* ---------- render every view ---------- */
const viewFiles = fs.readdirSync(VIEW_DIR).filter((f) => f.endsWith('.js'));
for (const f of viewFiles) {
  const name = f.replace(/\.js$/, '');
  expect('render ' + name, () => {
    const module = loadModule(path.join(VIEW_DIR, f), baseGlobals);
    if (!module || typeof module.render !== 'function') throw new Error('view does not expose render()');
    const payload = name === 'benchmark' ? mockRec : name === 'overview' ? mockStatus : mockTopology;
    const rendered = module.render(payload);
    if (!byClass(rendered, 'ys-tool-footer')) throw new Error('shared footer missing');
  });
}

/* ---------- Benchmark interactive graph ---------- */
expect('benchmark action switch rebuilds path selector (no TDZ)', () => {
  const module = loadModule(path.join(VIEW_DIR, 'benchmark.js'), baseGlobals);
  const root = module.render(mockRec);
  const action = byAria(root, 'Benchmark action');
  const pathSelect = byAria(root, 'Evaluation path');
  if (!action) throw new Error('action select missing');
  if (!pathSelect) throw new Error('path select missing');
  // One option per non-blocked action, label carries the evaluation semantics.
  const opts = action.options;
  if (opts.length !== 2) throw new Error('expected 2 non-blocked action options, got ' + opts.length);
  if (!(opts[0].textContent.includes('network.backlog') && opts[0].textContent.includes('device-pinned backlog')))
    throw new Error('action option label missing id+semantics');
  // Initial path list = first action's paths.
  if (pathSelect.options.length !== 2) throw new Error('initial path list should have 2 entries, got ' + pathSelect.options.length);
  // Switch to the second action -> path list rebuilds to its single path.
  action.value = 'tcp.cc';
  action.dispatch('change');
  if (pathSelect.options.length !== 1 || pathSelect.options[0].textContent !== 'path:lan-to-wan')
    throw new Error('path selector did not rebuild after action switch');
  // Switch to an action with no explicit paths -> empty (no crash).
  action.value = 'qdisc.replace';
  action.dispatch('change');
  if (pathSelect.options.length !== 0) throw new Error('blocked action should yield empty path list');
});

/* ---------- pomodoro: never let a missing require leak a crash ---------- */
process.exit(failures === 0 ? 0 : 1);
