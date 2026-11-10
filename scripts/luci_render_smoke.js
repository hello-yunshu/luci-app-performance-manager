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
 * for real; only the browser rendering layer is replaced.  `_()` is backed by
 * the shipped zh_Hans catalog so the smoke run renders exactly the Chinese the
 * user sees and can assert that no raw contract value leaks into the UI.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const RES = path.join(ROOT, 'package', 'luci-app-performance-manager', 'htdocs', 'luci-static', 'resources');
const VIEW_DIR = path.join(RES, 'view', 'performance-manager');
const PO_FILE = path.join(ROOT, 'package', 'luci-app-performance-manager', 'po', 'zh_Hans', 'performance-manager.po');

/* ---------- zh_Hans catalog ---------- */
function loadPo(file) {
  const map = Object.create(null);
  let id = null, str = '', field = null;
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    if (raw.startsWith('msgid ')) {
      const v = raw.slice(6);
      id = v.startsWith('"') ? v.slice(1, -1) : '';
      field = 'id';
    } else if (raw.startsWith('msgstr ')) {
      const v = raw.slice(7);
      str = v.startsWith('"') ? v.slice(1, -1) : '';
      if (id !== null) map[id] = str;
      field = 'str';
    } else if (raw.startsWith('"') && field) {
      const frag = raw.slice(1, -1);
      if (field === 'id') id += frag;
      else if (id !== null) map[id] = str += frag;
    } else if (!raw.trim()) {
      field = null;
    }
  }
  return map;
}
const CATALOG = loadPo(PO_FILE);
function _(s) {
  return Object.prototype.hasOwnProperty.call(CATALOG, s) && CATALOG[s] !== '' ? CATALOG[s] : s;
}

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

/* Everything the user reads without expanding a disclosure. */
function visibleText(node) {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (node.tag === 'details') return '';
  return (node.children || []).map(visibleText).join(' ');
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
/* LuCI 26 loads module factories through baseclass.extend(); a plain object
 * literal is rejected as "factory yields invalid constructor". */
const baseclass = { extend: (o) => o };
const puModule = loadModule(path.join(RES, 'performance-manager', 'ui.js'), { E, _, baseclass });
const pu = puModule;
const labels = loadModule(path.join(RES, 'performance-manager', 'labels.js'), { _, baseclass });

const baseGlobals = { E, _, view, ui, pu, pm, rpc, form, baseclass, labels, JSON, Object, Array, String, Number };

/* ---------- mock backend payloads ---------- */
const mockTx = {
  transactionId: '5f0c9a1e-1111-4222-8333-444455556666', actionId: 'nic.ring.floor',
  state: 'awaiting_confirm', applyTarget: 'netdev:eth0', bootId: 'a1b2c3d4-0000-4000-8000-123456789012',
};
const mockStatus = {
  version: '1.0.0-rc', running: true, automation: 'conservative', goal: 'balanced',
  telemetry: true, failsafe: true, topologyGeneration: 9,
  platform: { hyperv: true, kvm: false }, profile: { healthy: true, degraded: false },
  rill: { status: 'Runtime · Available', version: '0.9.1' }, healthGuard: { pass: true, reasons: ['high-cpu-load'] },
  nativePacketSteering: { provider: 'openwrt-netifd', availability: 'available', ownership: 'user' },
};
const mockTopology = {
  paths: [{
    id: 'path:lan-to-wan', workloadClass: ['plain_forwarding'], lanInterface: 'lan', wanInterface: 'wan',
    routeResolved: true, routeIdentity: 'abc123def456', routeProvider: 'netifd-fallback',
    targetRefs: ['netdev:eth0'],
  }],
};
const mockCaps = [{
  id: 'network.packet_steering.native', provider: 'openwrt-netifd', availability: 'available',
  scope: 'system', confidence: 'high', adjustable: false, policy: 'observe-respect', targetRef: 'netdev:eth0',
}];
const mockRill = { status: 'Runtime · Available', rillVersion: '0.9.1', transport: 'connected', protocolVersion: 2 };
const mockFeedback = {
  event: 'rill.outcome.accepted',
  data: { actionId: 'tcp.cc', goal: 'latency', reward: 0.2, measurementQuality: 'controlled_ab', accepted: true },
};
const mockRec = {
  benchmarkActions: [
    { id: 'network.backlog', status: 'ready', evaluationSemantics: 'forwarding', evaluationPaths: ['path:lan-to-wan', 'path:local-endpoint'] },
    { id: 'tcp.cc', status: 'ready', evaluationSemantics: 'local', evaluationPaths: ['path:lan-to-wan'] },
    { id: 'qdisc.replace', status: 'blocked', evaluationSemantics: 'blocked', evaluationPaths: [] },
  ],
  actions: [{
    id: 'nic.ring.floor', applyTarget: 'netdev:eth0', affectedTargets: ['netdev:eth0'],
    evaluationPaths: ['path:lan-to-wan'], risk: 'safe',
    reason: 'Hyper-V hv_netvsc ring is below the conservative 1024 floor while hardware maximum supports it.',
  }],
  observations: [{ id: 'network.packet_steering.native', detail: 'Native OpenWrt provider detected; no ownership seizure.' }],
  learnedAdvisory: [{ actionId: 'benchmark.kernel-network', kind: 'benchmark', authority: 'advisory-only', confidence: 0.62, decisionId: 'd-1' }],
  smartSelection: {
    learningStage: 'warming', selectedActionId: 'nic.ring.floor',
    selectedCandidateId: 'nic.ring.floor@target=deadbeef|path=cafebabe',
    confidence: 0.71, lastReward: 0.08, autoEligible: true, coreRecommendation: 'nic.ring.floor',
    drifted: false, reason: 'runtime-selected-eligible-candidate',
    ranking: [{ actionId: 'nic.ring.floor', score: 0.71 }, { actionId: 'tcp.cc', score: 0.4 }],
    blockedReasons: [{ actionId: 'tcp.cc', reason: 'action-cooldown', cooldownRemaining: 125000 }],
    context: {
      profile: 'recommended', goal: 'balanced', pathId: 'path:lan-to-wan', workloadClass: ['plain_forwarding'],
      topologyGeneration: 9, routeIdentity: 'abc123def456', integrationState: { openclash: true, sqm: false },
    },
    lastOutcome: { candidateId: 'c1', businessActionId: 'nic.ring.floor', reward: 0.08, measurementQuality: 'controlled_ab', validated: true },
    candidateHistory: { recentRewardMean: 0.08, successCount: 3, failureCount: 0, rollbackCount: 0, cooldownReason: 'action-cooldown' },
    validatedSamples: 4, minimumSamples: 6,
  },
};
const mockPayloads = {
  overview: [mockStatus, mockTopology, { transactions: [mockTx] }],
  optimize: mockRec,
  capabilities: [{ capabilities: mockCaps }, mockTopology],
  history: [{ transactions: [mockTx] }, { locks: [] }, { history: [mockFeedback], runtimeHistory: [] }],
  rill: [mockRill, mockRec, { history: [mockFeedback] }],
  benchmark: mockRec,
};

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
    const payload = mockPayloads[name] || mockTopology;
    const rendered = module.render(payload);
    if (!byClass(rendered, 'ys-tool-footer')) throw new Error('shared footer missing');
  });
}

/* ---------- no raw contract value reaches the rendered pages ---------- */
const RAW_VALUES = [
  'nic.ring.floor', 'network.backlog', 'tcp.cc', 'qdisc.replace',
  'network.packet_steering.native', 'benchmark.kernel-network', 'netdev:eth0',
  'Runtime · Available', 'Runtime · Collecting',
  'plain_forwarding', 'controlled_ab', 'awaiting_confirm', 'action-cooldown',
  'advisory-only', 'runtime-selected-eligible-candidate', 'warming', 'recommended',
  'Native OpenWrt provider detected', 'no ownership seizure',
  '5f0c9a1e-1111-4222-8333-444455556666', '125000',
];
for (const name of ['overview', 'optimize', 'capabilities', 'rill', 'history', 'benchmark']) {
  expect('no raw contract values: ' + name, () => {
    const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
    const text = visibleText(module.render(mockPayloads[name]));
    if (!/[\u4e00-\u9fff]/.test(text)) throw new Error('page rendered without Chinese text');
    for (const raw of RAW_VALUES) {
      if (text.includes(raw)) throw new Error('raw contract value leaked to UI: ' + raw);
    }
    const machineId = text.match(/[a-z][a-z0-9]*\.[a-z][a-z0-9._-]+/);
    if (machineId) throw new Error('machine identifier leaked to UI: ' + machineId[0]);
    const uuid = text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/);
    if (uuid) throw new Error('UUID leaked to UI: ' + uuid[0]);
    if (/\b\d+\s*ms\b/.test(text)) throw new Error('bare millisecond value leaked to UI');
  });
}

/* ---------- Benchmark interactive graph ---------- */
expect('benchmark action switch rebuilds path selector (no TDZ)', () => {
  const module = loadModule(path.join(VIEW_DIR, 'benchmark.js'), baseGlobals);
  const root = module.render(mockRec);
  const action = byAria(root, _('Benchmark action'));
  const pathSelect = byAria(root, _('Evaluation path'));
  if (!action) throw new Error('action select missing');
  if (!pathSelect) throw new Error('path select missing');
  // One option per non-blocked action, labelled with the Chinese action name.
  const opts = action.options;
  if (opts.length !== 2) throw new Error('expected 2 non-blocked action options, got ' + opts.length);
  if (!(opts[0].textContent.includes(_('Kernel receive backlog')) && opts[0].textContent.includes(_('Forwarding path'))))
    throw new Error('action option label missing human-readable name+semantics: ' + opts[0].textContent);
  // Initial path list = first action's paths.
  if (pathSelect.options.length !== 2) throw new Error('initial path list should have 2 entries, got ' + pathSelect.options.length);
  // Switch to the second action -> path list rebuilds to its single path.
  action.value = 'tcp.cc';
  action.dispatch('change');
  if (pathSelect.options.length !== 1 || pathSelect.options[0].textContent !== _('LAN to WAN'))
    throw new Error('path selector did not rebuild after action switch');
  // Switch to an action with no explicit paths -> empty (no crash).
  action.value = 'qdisc.replace';
  action.dispatch('change');
  if (pathSelect.options.length !== 0) throw new Error('blocked action should yield empty path list');
});

/* ---------- optional HTML snapshot for visual evidence ---------- */
const htmlFlag = process.argv.indexOf('--html');
if (htmlFlag !== -1 && process.argv[htmlFlag + 1]) {
  const outDir = process.argv[htmlFlag + 1];
  fs.mkdirSync(outDir, { recursive: true });
  const css = fs.readFileSync(path.join(RES, 'performance-manager', 'ui.css'), 'utf8');
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const toHtml = (node) => {
    if (node == null) return '';
    if (typeof node === 'string' || typeof node === 'number') return esc(node);
    const attrs = Object.entries(node.attrs || {}).map(([k, v]) => ` ${k}="${esc(v)}"`).join('');
    const inner = (node.children || []).map(toHtml).join('');
    return node.tag === '#fragment' ? inner : `<${node.tag}${attrs}>${inner}</${node.tag}>`;
  };
  for (const name of ['overview', 'optimize', 'capabilities', 'rill', 'history', 'benchmark']) {
    const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
    const body = toHtml(module.render(mockPayloads[name]));
    fs.writeFileSync(path.join(outDir, name + '.html'),
      `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${name}</title>` +
      `<style>${css}</style><style>body{background:#f6f7f9;margin:0;padding:24px;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}</style>` +
      `</head><body>${body}</body></html>`);
  }
  console.log('html snapshots written to ' + outDir);
}

/* ---------- pomodoro: never let a missing require leak a crash ---------- */
process.exit(failures === 0 ? 0 : 1);
