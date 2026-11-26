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
const EN_CATALOG = loadPo(path.join(ROOT, 'package', 'luci-app-performance-manager', 'po', 'en', 'performance-manager.po'));
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
    this.classList = {
      add: (name) => { this.attrs['class'] = [this.attrs['class'], name].filter(Boolean).join(' '); },
      remove: (name) => { this.attrs['class'] = String(this.attrs['class'] || '').split(/\s+/).filter((c) => c && c !== name).join(' '); },
      contains: (name) => String(this.attrs['class'] || '').split(/\s+/).includes(name),
    };
    if (this.attrs.class) this.class = this.attrs['class'];
    /* LuCI's `dom.append` stringifies every array member that is not a node and
     * guards with `children !== null` — the ARRAY, never the member — so a null
     * element inside a children array renders as the literal text "null".
     * Mirror that exactly, otherwise the smoke run cannot see the leak. */
    if (Array.isArray(children))
      children.forEach((c) => this.children.push(c instanceof FakeEl ? c : String(c)));
    else if (children != null)
      this.appendChild(children);
  }
  get value() { return this._value !== undefined ? this._value : (this.options.length ? this.options[0].attrs.value : ''); }
  set value(v) { this._value = v; }
  appendChild(c) { if (c != null) this.children.push(c); return c; }
  replaceChildren(...nodes) { this.children = []; nodes.forEach((n) => this.appendChild(n)); }
  querySelector(selector) {
    if (selector.startsWith('.')) return byClass(this, selector.slice(1));
    return null;
  }
  addEventListener(evt, fn) { (this._listeners[evt] = this._listeners[evt] || []).push(fn); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  removeAttribute(name) { delete this.attrs[name]; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name); }
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

/* Everything the user reads without expanding a disclosure.  <summary> is
 * always visible, so it is included; the disclosure body is covered by the
 * separate raw-JSON check. */
function visibleText(node) {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (node.tag === 'details')
    return (node.children || []).filter((c) => c && c.tag === 'summary').map(visibleText).join(' ');
  return (node.children || []).map(visibleText).join(' ');
}

/* Text carried by attributes that assistive tech or the user reads directly. */
function attributeText(node) {
  if (node == null || typeof node !== 'object') return '';
  const out = [];
  for (const key of ['aria-label', 'title', 'placeholder', 'alt']) {
    if (typeof node.attrs?.[key] === 'string') out.push(node.attrs[key]);
  }
  for (const c of node.children || []) out.push(attributeText(c));
  return out.join('\n');
}

function allText(node) {
  if (node == null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  return (node.children || []).map(allText).join(' ');
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

/* Minimal `form` (settings view).  Option labels, descriptions and list values
 * are rendered as text so the settings page is subject to the same language
 * and raw-value assertions as the other pages. */
function Opt(label) {
  this.label = label;
  this.description = '';
  this._values = [];
  this.value = function (value, text) { if (text != null) this._values.push(text); };
  this.depends = function () {};
  this.default = null;
  this.readonly = false;
  this.disabled = false;
  this.enabled = false;
  this.placeholder = '';
}
function Sec(title) {
  this.title = title;
  this._opts = [];
  this.option = function (kind, key, label) { const o = new Opt(label); this._opts.push(o); return o; };
  this.tab = function () {};
  this.taboption = function (tab, kind, key, label) { return this.option(kind, key, label); };
}
function FormMap(title, description) {
  this.title = title;
  this.description = description;
  this._sections = [];
  this.section = function (kind, name, type, title) { const s = new Sec(title); this._sections.push(s); return s; };
  this.render = function () {
    return E('form', null, this._sections.map((s) => E('fieldset', null, [
      E('legend', null, [s.title]),
      ...s._opts.map((o) => E('div', null, [o.label, o.description || '', ...o._values]))
    ])));
  };
}
const form = {
  Map: FormMap,
  NamedSection: Symbol('NamedSection'), Flag: Symbol('Flag'), ListValue: Symbol('ListValue'), Value: Symbol('Value'),
};

const rpc = { declare: (d) => () => Promise.resolve({ ok: false, error: 'rpc-unavailable-in-smoke' }) };
const pm = { status: rpc.declare({}), capabilities: rpc.declare({}), topology: rpc.declare({}),
  recommendations: rpc.declare({}), transactions: rpc.declare({}), locks: rpc.declare({}),
  history: rpc.declare({}), rill: rpc.declare({}), diagnostics: rpc.declare({}), apply: rpc.declare({}),
  rillRefresh: rpc.declare({}),
  confirm: rpc.declare({}), rollback: rpc.declare({}), benchmarkStart: rpc.declare({}),
  benchmarkStatus: rpc.declare({}), benchmarkStop: rpc.declare({}) };
const notifications = [];
const ui = { addNotification: (level, node, type) => { notifications.push({ level, node, type }); } };
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
  platform: { hyperv: true, kvm: false },
  rill: { status: 'Runtime · Available', version: '0.9.1' }, healthGuard: { pass: true, reasons: ['high-cpu-load'] },
  profile: { id: 'recommended', healthy: true, degraded: false },
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
  rill: [mockRill, { history: [mockFeedback] }, mockRec],
  benchmark: mockRec,
};

(async () => {
let failures = 0;
async function expect(name, fn) {
  try {
    await fn();
    console.log('ok  - ' + name);
  } catch (e) {
    failures++;
    console.error('FAIL- ' + name + ': ' + (e && e.stack ? e.stack : e));
  }
}

const PAGES = ['overview', 'optimize', 'capabilities', 'rill', 'history', 'benchmark', 'settings', 'advanced'];
const LABELS_SRC = fs.readFileSync(path.join(RES, 'performance-manager', 'labels.js'), 'utf8');

await expect('field without help omits a null DOM child', () => {
  const strictE = (tag, attrs, children) => {
    if (Array.isArray(children) && children.includes(null))
      throw new Error('null passed as a DOM child');
    return E(tag, attrs, children);
  };
  const strictPu = loadModule(path.join(RES, 'performance-manager', 'ui.js'), { E: strictE, _, baseclass });
  const rendered = strictPu.field('Label', E('select'), undefined);
  if (!visibleText(rendered).includes('Label')) throw new Error('field label is missing');
});

/* Read the real mapping tables so coverage is driven by every value the module
 * knows about, not by a hand-picked sample. */
function tableKeys(name) {
  const start = LABELS_SRC.indexOf(`const ${name} = {`);
  if (start < 0) throw new Error('labels table not found: ' + name);
  let i = LABELS_SRC.indexOf('{', start), depth = 0, end = -1;
  for (; i < LABELS_SRC.length; i++) {
    if (LABELS_SRC[i] === '{') depth++;
    else if (LABELS_SRC[i] === '}' && --depth === 0) { end = i; break; }
  }
  const keys = [];
  for (const line of LABELS_SRC.slice(i === -1 ? 0 : LABELS_SRC.indexOf('{', start), end + 1).split('\n')) {
    const m = line.match(/^\t'?([A-Za-z0-9][A-Za-z0-9._:@-]*)'?\s*:\s*(?:_\(|\{)/);
    if (m) keys.push(m[1]);
  }
  return keys;
}
const TABLE_NAMES = (LABELS_SRC.match(/^const ([A-Z_]+) = \{/gm) || [])
  .map((l) => l.match(/^const ([A-Z_]+) = \{/)[1]);
const CATALOG_KEYS = TABLE_NAMES.flatMap((t) => tableKeys(t));
const RUNTIME_STATUS_VALUES = [
  'Runtime · Disabled', 'Runtime · Binary invalid', 'Runtime · Not provisioned', 'Runtime · Unavailable',
  'Runtime · Version mismatch', 'Runtime · Error', 'Runtime · Missing capabilities', 'Runtime · Unhealthy',
  'Runtime · Learning', 'Runtime · Available',
];
/* Values the ucode backend actually emits into smartSelection.reason,
 * rill.reason, blockedReasons[].reason and candidateHistory.cooldownReason. */
const BACKEND_REASONS = [
  'external-runtime-not-provisioned', 'runtime-spawn-failed', 'runtime-exit-7', 'empty-response', 'bad-response',
  'oversized-local-context', 'unsupported-operation', 'runtime-state-invalid', 'sent-unknown-journal-failed',
  'throttled', 'no-available-actions', 'invalid-observe-response', 'binding-registration-failed',
  'runtime-version-mismatch', 'runtime-unavailable', 'missing-required-capability', 'model-unhealthy',
  'duplicate-candidate-id', 'duplicate-ranking-candidate-id', 'rill-selected-candidate-missing',
  'rill-score-invalid', 'rill-ranking-candidate-unknown', 'mode-policy-blocked', 'target-unresolved',
  'compatibility-blocked', 'action-cooldown', 'negative-reward', 'validated-success', 'success-debounce',
  'health-regression-rollback', 'execution-failure', 'response-not-object', 'ok-not-boolean',
  'status-fields-invalid', 'status-version-missing', 'decision-id-invalid', 'recommendation-invalid',
  'confidence-invalid', 'scores-invalid', 'score-row-invalid', 'score-candidate-duplicate',
  'score-action-unknown', 'recommendation-action-unknown', 'outcome-not-accepted',
  'disabled', 'not-provisioned', 'binary-invalid', 'starting', 'incompatible', 'unhealthy', 'unavailable',
];
const UNKNOWN_REASON_TEXT = _('Unrecognized reason, see technical details');

function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

function findByText(root, tag, text) {
  if (root == null || typeof root !== 'object') return null;
  if (root.tag === tag && String(root.textContent || '').includes(text)) return root;
  for (const c of root.children || []) {
    const hit = findByText(c, tag, text);
    if (hit) return hit;
  }
  return null;
}

/* ---------- catalog and backend enum coverage ---------- */
await expect('zh_Hans catalog is complete and non-empty', () => {
  const empty = Object.keys(CATALOG).filter((k) => k !== '' && !CATALOG[k]);
  if (empty.length) throw new Error('empty translations: ' + empty.slice(0, 5).join(', '));
});
await expect('en catalog mirrors the zh_Hans msgid set', () => {
  const zh = Object.keys(CATALOG).filter((k) => k !== '');
  const en = Object.keys(EN_CATALOG).filter((k) => k !== '');
  const missing = zh.filter((k) => !(k in EN_CATALOG));
  const extra = en.filter((k) => !(k in CATALOG));
  if (missing.length || extra.length)
    throw new Error(`catalog drift: missing in en ${missing.slice(0, 5).join(' | ')}; extra in en ${extra.slice(0, 5).join(' | ')}`);
  const bad = en.filter((k) => EN_CATALOG[k] !== k);
  if (bad.length) throw new Error('en translations must equal msgid: ' + bad.slice(0, 5).join(' | '));
});
await expect('every Rill runtime status maps to text', () => {
  for (const value of RUNTIME_STATUS_VALUES) {
    const text = labels.runtimeStatus(value);
    if (text === _('Unknown state')) throw new Error('unmapped runtime status: ' + value);
  }
  if (labels.runtimeStatusOverview('Runtime · Not provisioned') !== _('Not provisioned'))
    throw new Error('overview runtime status should use its concise translated label');
  if (labels.runtimeStatusOverview('Runtime · Available') !== _('Available'))
    throw new Error('overview available runtime status should be concise');
  if (labels.runtimeStatus('Runtime · Not provisioned') !== _('Runtime not provisioned'))
    throw new Error('Rill runtime detail should retain its full status label');
});
await expect('every backend Rill reason maps to text (plain and rill- prefixed)', () => {
  for (const value of BACKEND_REASONS) {
    for (const key of [value, 'rill-' + value]) {
      const text = labels.smartReason(key);
      if (text === UNKNOWN_REASON_TEXT || text === '—') throw new Error('unmapped Rill reason: ' + key);
    }
  }
});
await expect('every ERROR_CODE table key resolves instead of falling back', () => {
  for (const key of tableKeys('ERROR_CODE')) {
    const text = labels.errorSummary(key);
    if (text === _('Unknown error, see technical details')) throw new Error('unmapped error code: ' + key);
  }
});
/* The shared rill-runtime-manager reports these codes verbatim in its RPC
 * result.  Package actions surface the code, so an unmapped one turns a precise
 * manager failure into "未知错误，详见技术详情". */
const MANAGER_ERROR_CODES = [
  'feed-not-configured', 'feed-refresh-failed', 'legacy-feed-configured',
  'legacy-runtime-migration-required', 'legacy-preview', 'package-manager-busy',
  'package-manager-failed', 'package-manager-unavailable', 'package-action-not-supported',
  'package-not-allowed', 'trust-key-missing', 'runtime-not-installed',
  'runtime-binary-missing', 'runtime-package-unavailable', 'runtime-repair-required',
  'runtime-unsupported-architecture', 'unknown-runtime-owner',
  'consumer-runtime-incompatible', 'consumer-compatibility-unknown', 'unsupported-release',
];
await expect('every rill-runtime-manager error code maps to text', () => {
  for (const code of MANAGER_ERROR_CODES) {
    const text = labels.errorSummary(code);
    if (text === _('Unknown error, see technical details')) throw new Error('unmapped manager error code: ' + code);
  }
});

/* ---------- percent / duration / identity / error formatting ---------- */
await expect('percent renders ratios above 1 as percentages', () => {
  const cases = [[1.2, '120%'], [2, '200%'], [0.4, '40%'], [0.085, '8.5%'], [-0.2, '-20%'], [0, '0%']];
  for (const [input, want] of cases) {
    const got = labels.percent(input);
    if (got !== want) throw new Error(`percent(${input}) = ${got}, want ${want}`);
  }
});
await expect('duration keeps Chinese units and singular forms', () => {
  const cases = [[1000, _('About 1 second')], [125000, _('About %s min %s sec').format(2, 5)], [60000, _('About 1 minute')]];
  for (const [input, want] of cases) {
    const got = labels.duration(input);
    if (got !== want) throw new Error(`duration(${input}) = ${got}, want ${want}`);
  }
});
await expect('raw identifiers are reported without exposing short UUIDs', () => {
  const value = labels.reference('5f0c9a1e-1111-4222-8333-444455556666');
  if (!value.includes(_('Recorded, see technical details'))) throw new Error('reference() did not use the human label');
  if (/\b[0-9a-f]{8}\b/.test(value)) throw new Error('reference() leaked a truncated UUID');
  if (labels.transaction('5f0c9a1e-1111-4222-8333-444455556666') !== _('Change transaction'))
    throw new Error('transaction() must render a human title, not a short UUID');
});
await expect('errorSummary is readable and never repeats the details suffix', () => {
  const a = labels.errorSummary('lock-conflict: lock exists');
  if (a !== _('Another operation holds the required lock')) throw new Error('lock-conflict not readable: ' + a);
  const b = labels.errorSummary({ ok: false, error: 'transaction-not-found' });
  if (b !== _('The transaction no longer exists')) throw new Error('object error not readable: ' + b);
  const c = labels.errorSummary('something-unmapped: detail');
  if ((c.match(/详见技术详情/g) || []).length > 1) throw new Error('details suffix repeated: ' + c);
  for (const state of ['no-available-actions', 'invalid-observe-response', 'binding-registration-failed',
    'throttled', 'empty-response', 'bad-response', 'runtime-spawn-failed',
    'external-runtime-not-provisioned', 'runtime-state-invalid']) {
    const text = labels.errorSummary({ ok: false, state });
    if (text === _('Unknown error, see technical details') || text === UNKNOWN_REASON_TEXT)
      throw new Error('Rill failure state is not readable: ' + state);
  }
});

/* ---------- render every view, including settings and advanced ---------- */
const MOCK = {
  overview: [mockStatus, mockTopology, { transactions: [mockTx] }],
  optimize: mockRec,
  capabilities: [{ capabilities: mockCaps }, mockTopology],
  history: [{ transactions: [mockTx] }, { locks: [] }, { history: [mockFeedback], runtimeHistory: [] }],
  rill: [mockRill, { history: [mockFeedback] }, mockRec],
  benchmark: mockRec,
  settings: undefined,
  advanced: [mockStatus, { capabilities: mockCaps }, mockTopology, mockRec, { transactions: [mockTx] }, { locks: [] }, { resources: {} }],
};
const EMPTY = {
  overview: [{}, {}, { transactions: [] }],
  optimize: { actions: [], observations: [], learnedAdvisory: [], benchmarkActions: [], smartSelection: null },
  capabilities: [{ capabilities: [] }, { paths: [] }],
  history: [{ transactions: [] }, { locks: [] }, { history: [], runtimeHistory: [] }],
  rill: [{}, {}, { history: [] }],
  benchmark: { benchmarkActions: [], learnedAdvisory: [] },
  settings: undefined,
  advanced: [{}, {}, {}, {}, {}, {}, {}],
};

for (const name of PAGES) {
  await expect('render ' + name, () => {
    const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
    if (!module || typeof module.render !== 'function') throw new Error('view does not expose render()');
    const rendered = module.render(MOCK[name]);
    if (!byClass(rendered, 'ys-tool-footer')) throw new Error('shared footer missing');
    const text = visibleText(rendered) + ' ' + attributeText(rendered);
    if (!/[\u4e00-\u9fff]/.test(visibleText(rendered))) throw new Error('page rendered without Chinese text');
    if (text.length < 40) throw new Error('page rendered almost no text');
  });
  await expect('render empty state: ' + name, () => {
    const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
    const rendered = module.render(EMPTY[name]);
    if (!byClass(rendered, 'ys-tool-footer')) throw new Error('shared footer missing');
    if (!/[\u4e00-\u9fff]/.test(visibleText(rendered))) throw new Error('empty state rendered without Chinese text');
  });
}

await expect('overview explains missing recommended tools and guards ip-full install advice', () => {
  const view = loadModule(path.join(VIEW_DIR, 'overview.js'), baseGlobals);
  const profile = {
    ...mockStatus.profile,
    healthy: false,
    degraded: false,
    targetMatched: true,
    packageManager: 'opkg',
    missingRecommendedPackages: ['iperf3', 'ethtool'],
    missingCommands: ['iperf3'],
    recommendedPackages: ['iperf3', 'ethtool'],
    expectedCommands: ['iperf3'],
  };
  const text = visibleText(view.render([{ ...mockStatus, profile }, mockTopology, { transactions: [] }]));
  if (!text.includes(_('Recommended tools missing'))) throw new Error('overview status does not identify missing recommended tools');
  for (const name of ['iperf3', 'ethtool']) {
    if (!text.includes(name)) throw new Error('overview did not list missing package: ' + name);
  }
  if (!text.includes(_('Install command')) || !text.includes('opkg install iperf3 ethtool'))
    throw new Error('overview did not show the supported package install command');

  const ipFullProfile = {
    ...profile,
    missingRecommendedPackages: ['ip-full'],
    missingCommands: ['ip'],
    recommendedPackages: ['ip-full'],
    expectedCommands: ['ip'],
  };
  const ipFullText = visibleText(view.render([{ ...mockStatus, profile: ipFullProfile }, mockTopology, { transactions: [] }]));
  if (!ipFullText.includes('ip-full')) throw new Error('overview hid the missing ip-full package');
  if (ipFullText.includes(_('Install command')) || ipFullText.includes('opkg install ip-full'))
    throw new Error('overview suggested an install command that could conflict with ip-full');
});

/* ---------- no raw contract value or English prose reaches the UI ---------- */
const RAW_VALUES = [
  'nic.ring.floor', 'network.backlog', 'tcp.cc', 'qdisc.replace',
  'network.packet_steering.native', 'benchmark.kernel-network', 'netdev:eth0', 'netdev:wan',
  'Runtime · Available', 'Runtime · Collecting',
  'plain_forwarding', 'controlled_ab', 'awaiting_confirm', 'action-cooldown',
  'advisory-only', 'runtime-selected-eligible-candidate', 'warming', 'recommended',
  'Native OpenWrt provider detected', 'no ownership seizure',
  '5f0c9a1e-1111-4222-8333-444455556666', 'a1b2c3d4-0000-4000-8000-123456789012',
  '5f0c9a1e', 'a1b2c3d4', 'deadbeef', 'cafebabe', 'abc123def456', 'd-1', '125000',
  'performance-x86', 'openclash', 'path:lan-to-wan', 'path:local-endpoint',
];
function assertCleanPage(name, payload) {
  const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
  const rendered = module.render(payload);
  const text = visibleText(rendered);
  if (!/[\u4e00-\u9fff]/.test(text)) throw new Error('page rendered without Chinese text');
  for (const raw of RAW_VALUES.concat(CATALOG_KEYS)) {
    const re = new RegExp('(^|[^A-Za-z0-9_.:@-])' + escapeRe(raw) + '($|[^A-Za-z0-9_.:@-])');
    if (re.test(text)) throw new Error('raw contract value leaked to UI: ' + raw);
  }
  /* hv_netvsc is a Linux driver name in a translated description, not a
   * contract identifier leaking from the backend. */
  const machineText = text.replace(/hv_netvsc/g, '');
  const machineId = machineText.match(/[a-z][a-z0-9]*(?:[._:][a-z0-9][a-z0-9._:-]*)+/);
  if (machineId) throw new Error('machine identifier leaked to UI: ' + machineId[0]);
  const kebab = machineText.match(/(^|[^A-Za-z0-9_-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?=$|[^A-Za-z0-9_-])/);
  if (kebab) throw new Error('kebab-case identifier leaked to UI: ' + kebab[0].trim());
  const uuid = text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i);
  if (uuid) throw new Error('UUID leaked to UI: ' + uuid[0]);
  /* M3 regression guard: an 8-character truncated UUID must not come back. */
  const shortUuid = text.match(/(^|[^0-9A-Za-z])[0-9a-f]{8}(?=$|[^0-9A-Za-z])/i);
  if (shortUuid) throw new Error('short UUID leaked to UI: ' + shortUuid[0]);
  if (/\b\d+\s*ms\b/.test(text)) throw new Error('bare millisecond value leaked to UI');
  /* LuCI stringifies a null/undefined children entry, so a conditional block
   * that stays empty must be filtered out instead of rendered. */
  const placeholder = text.match(/(^|[^A-Za-z0-9_])(null|undefined|NaN)(?=$|[^A-Za-z0-9_])/);
  if (placeholder) throw new Error('placeholder value rendered to UI: ' + placeholder[2]);
  const english = text.match(/[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){2,}/);
  if (english) throw new Error('English prose leaked to UI: ' + english[0]);
  const attrs = attributeText(rendered);
  for (const value of attrs.split('\n')) {
    if (/^\/|^<|^$/.test(value) || /[\u4e00-\u9fff]/.test(value)) continue;
    /* Values with no Latin letters (for example "—") are not untranslated text. */
    if (!/[A-Za-z]/.test(value)) continue;
    throw new Error('untranslated attribute text: ' + value);
  }
}
for (const name of PAGES) {
  await expect('no raw contract values: ' + name, () => assertCleanPage(name, MOCK[name]));
  await expect('no raw contract values (empty state): ' + name, () => assertCleanPage(name, EMPTY[name]));
}

/* Default install: the external Rill runtime is not provisioned.  This is the
 * first screen a fresh user sees, so it must explain itself instead of
 * falling back to the generic "unknown state" label. */
const DEFAULT_INSTALL_RILL = [
  { status: 'Runtime · Not provisioned', transport: 'unavailable' },
  { history: [] },
  { smartSelection: { reason: 'external-runtime-not-provisioned', ranking: [] } },
];
await expect('default install Rill page explains the missing runtime', () => {
  assertCleanPage('rill', DEFAULT_INSTALL_RILL);
  const text = visibleText(loadModule(path.join(VIEW_DIR, 'rill.js'), baseGlobals).render(DEFAULT_INSTALL_RILL));
  if (!text.includes(_('Runtime not provisioned'))) throw new Error('runtime state is not explained: ' + text.slice(0, 160));
  if (!text.includes(_('The external Rill runtime is not installed')))
    throw new Error('policy reason is not explained: ' + text.slice(0, 160));
  if (text.includes(_('Unknown state')) || text.includes(_('Unrecognized reason, see technical details')))
    throw new Error('default install fell back to an unknown label');
  if (text.includes(_('Unknown action')))
    throw new Error('default install invented an unknown action instead of showing a dash');
  /* Every absent field must read as "not recorded", never as "unknown". */
  const unknown = text.match(/未知[^\s，。]{0,4}/);
  if (unknown) throw new Error('default install shows an unknown value: ' + unknown[0]);
});

await expect('lazy recommendation failures expose a working retry on Optimize and Rill', async () => {
  const previousWindow = global.window;
  const previousRecommendations = pm.recommendations;
  try {
    const observers = [];
    global.window = {
      IntersectionObserver: function (callback) {
        this.callback = callback;
        this.observe = function () {};
        this.disconnect = function () {};
        observers.push(this);
      },
    };
    for (const [name, payload] of [
      ['optimize', { _lazy: true }],
      ['rill', [mockRill, { ok: true, supported: true, installed: true, compatible: true }, null]],
    ]) {
      let attempts = 0;
      pm.recommendations = () => {
        attempts++;
        return Promise.reject(new Error('controlled recommendation failure'));
      };
      const page = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals).render(payload);
      const observer = observers.pop();
      if (!observer) throw new Error(name + ' did not register a lazy-load observer');
      observer.callback([{ isIntersecting: true }]);
      await new Promise((resolve) => setImmediate(resolve));

      const retry = findByText(page, 'button', _('Retry'));
      if (!retry) throw new Error(name + ' did not offer Retry after the first RPC failure');
      if (!visibleText(page).includes(_('Unable to load recommendations: %s').split('%s')[0]))
        throw new Error(name + ' did not explain the recommendation load failure');

      retry.attrs.click.call(retry);
      await new Promise((resolve) => setImmediate(resolve));
      if (attempts !== 2) throw new Error(name + ' Retry did not issue a second recommendations RPC');
      if (!findByText(page, 'button', _('Retry')))
        throw new Error(name + ' did not retain Retry after the second RPC failure');
    }
  } finally {
    pm.recommendations = previousRecommendations;
    if (previousWindow === undefined) delete global.window;
    else global.window = previousWindow;
  }
});

await expect('PM update action follows the PM-specific availability flag', () => {
  const view = loadModule(path.join(VIEW_DIR, 'rill.js'), baseGlobals);
  const renderPackageControls = (manager) => visibleText(view.render([mockRill, {
    ok: true, supported: true, installed: true, channel: 'stable', compatible: true,
    runtimeUpdateAvailable: false, ...manager,
  }, mockRec]));
  const noRuntime = renderPackageControls({ installed: false, channel: 'none', compatible: false });
  if (!noRuntime.includes(_('Install Rill Runtime')))
    throw new Error('missing Runtime incorrectly hid the install action');
  const cfiOnly = renderPackageControls({ pmUpdateAvailable: false, clientUpdateAvailable: true });
  if (cfiOnly.includes(_('Update Performance Manager')))
    throw new Error('CFI-only update incorrectly displayed the PM update action');
  const pmOnly = renderPackageControls({ pmUpdateAvailable: true, clientUpdateAvailable: false });
  if (!pmOnly.includes(_('Update Performance Manager')))
    throw new Error('PM update action was hidden when PM-specific update was available');
  const repairAvailable = renderPackageControls({ repairAvailable: true });
  if (!repairAvailable.includes(_('Repair Rill Runtime')))
    throw new Error('Runtime repair action was hidden when the manager confirmed safe repair');
  const legacyPreview = renderPackageControls({
    installed: true, channel: 'legacy-preview', version: '1.5.6-r10',
    runtimeUpdateAvailable: true, repairAvailable: true,
  });
  if (!legacyPreview.includes('rill-runtime-preview') || !legacyPreview.includes('1.5.6-r10'))
    throw new Error('legacy Runtime owner/version was not identified');
  if (!legacyPreview.includes('opkg remove luci-app-performance-manager-all rill-runtime-preview') ||
      !legacyPreview.includes('apk del luci-app-performance-manager-all rill-runtime-preview'))
    throw new Error('legacy Runtime migration steps were not shown');
  if (legacyPreview.includes(_('Install Rill Runtime')) || legacyPreview.includes(_('Update Rill Runtime')) ||
      legacyPreview.includes(_('Repair Rill Runtime')))
    throw new Error('legacy Preview Runtime could be replaced without a manual migration');
  if (!view.render.toString().includes('pm.runtimeManagerRepair(packageName)'))
    throw new Error('Runtime repair action does not call the dedicated repair RPC');
  const unknownRuntime = renderPackageControls({ installed: false, channel: 'unknown', compatible: false });
  if (unknownRuntime.includes(_('Install Rill Runtime')))
    throw new Error('unknown Runtime ownership must not show an install action');
});

/* The shared rill-runtime-manager parses the installed package metadata itself.
 * When that parse fails (apk 3.x prints the package description for
 * `apk info -v`) it reports incompatible while the Runtime answered PM's own
 * version handshake.  The handshake is authoritative, so the page must not
 * raise the conflict banner, must keep the package actions enabled, and must
 * never print the unparsed description as the Runtime version. */
await expect('a manager version-parse failure does not fake a Runtime conflict', () => {
  const view = loadModule(path.join(VIEW_DIR, 'rill.js'), baseGlobals);
  const description = 'Generic Rill Runtime packaged for OpenWrt. This distribution recipe installs only the runtime executable from an immutable upstream Git commit promoted to the Stable package channel.';
  const handshakeOk = { ...mockRill, compatibility: 'compatible' };
  const page = visibleText(view.render([handshakeOk, {
    ok: true, supported: true, installed: true, channel: 'stable',
    compatible: false, version: description, runtimeUpdateAvailable: true,
  }, mockRec]));
  if (page.includes(_('An incompatible Rill Runtime is installed. Resolve that package conflict before changing Runtime packages.')))
    throw new Error('handshake-compatible Runtime was reported as a package conflict');
  if (!page.includes(_('Update Rill Runtime')))
    throw new Error('Runtime update action stayed hidden after the handshake cleared the conflict');
  if (page.includes('packaged for OpenWrt'))
    throw new Error('unparsed manager version leaked the package description into the details table');
  /* A real ownership conflict still wins over a passing handshake. */
  const legacy = visibleText(view.render([handshakeOk, {
    ok: true, supported: true, installed: true, channel: 'legacy-preview',
    compatible: false, version: description, runtimeUpdateAvailable: true,
  }, mockRec]));
  if (!legacy.includes('rill-runtime-preview'))
    throw new Error('handshake override silently dropped the legacy Preview conflict');
});

/* Prove the scanner itself would catch the exact regressions it is meant to
 * catch, so a future refactor cannot silently weaken it. */
await expect('raw-value scanner self-test', () => {
  const bad = '事务 5f0c9a1e 冷却 success-debounce 路径 nic.ring.floor 延迟 125000 ms';
  const found = [];
  if (/(^|[^0-9A-Za-z])[0-9a-f]{8}(?=$|[^0-9A-Za-z])/i.test(bad)) found.push('short-uuid');
  if (/(^|[^A-Za-z0-9_-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?=$|[^A-Za-z0-9_-])/.test(bad)) found.push('kebab');
  if (/[a-z][a-z0-9]*(?:[._:][a-z0-9][a-z0-9._:-]*)+/.test(bad)) found.push('machine-id');
  if (/\b\d+\s*ms\b/.test(bad)) found.push('bare-ms');
  if (found.sort().join(',') !== 'bare-ms,kebab,machine-id,short-uuid')
    throw new Error('scanner missed a known-bad fixture: ' + found.join(','));
});

/* ---------- interactive error branches surface readable reasons ---------- */
await expect('optimize apply failure shows a readable reason and details', async () => {
  notifications.length = 0;
  pm.apply = () => Promise.resolve({ ok: false, error: 'lock-conflict: lock exists' });
  const module = loadModule(path.join(VIEW_DIR, 'optimize.js'), baseGlobals);
  const root = module.render(mockRec);
  const button = findByText(root, 'button', _('Apply safely'));
  if (!button) throw new Error('apply button missing');
  button.dispatch('click');
  await new Promise((r) => setTimeout(r, 0));
  if (!notifications.length) throw new Error('no notification emitted');
  const text = allText(notifications[0].node);
  if (!text.includes(_('Another operation holds the required lock')))
    throw new Error('notification did not surface the readable reason: ' + text);
  if (!byClass(notifications[0].node, 'pm-disclosure')) throw new Error('notification has no collapsed technical details');
  if ((text.match(/详见技术详情/g) || []).length > 1) throw new Error('details suffix repeated: ' + text);
});
await expect('benchmark start failure shows a readable reason and details', async () => {
  pm.benchmarkStart = () => Promise.resolve({ ok: false, error: 'benchmark-session-not-running' });
  const module = loadModule(path.join(VIEW_DIR, 'benchmark.js'), baseGlobals);
  const root = module.render(mockRec);
  const button = findByText(root, 'button', _('Start test'));
  if (!button) throw new Error('start button missing');
  button.dispatch('click');
  await new Promise((r) => setTimeout(r, 0));
  const text = visibleText(root) + ' ' + allText(root);
  if (!text.includes(_('The performance test session is not running')))
    throw new Error('blocked panel did not surface the readable reason');
});

/* ---------- Benchmark interactive graph ---------- */
await expect('benchmark action switch rebuilds path selector (no TDZ)', () => {
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
  for (const name of PAGES) {
    const module = loadModule(path.join(VIEW_DIR, name + '.js'), baseGlobals);
    const body = toHtml(module.render(MOCK[name]));
    fs.writeFileSync(path.join(outDir, name + '.html'),
      `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${name}</title>` +
      `<style>${css}</style><style>body{background:#f6f7f9;margin:0;padding:24px;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}</style>` +
      `</head><body>${body}</body></html>`);
  }
  const rillDefault = toHtml(loadModule(path.join(VIEW_DIR, 'rill.js'), baseGlobals).render(DEFAULT_INSTALL_RILL));
  fs.writeFileSync(path.join(outDir, 'rill-default-install.html'),
    `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>rill-default-install</title>` +
    `<style>${css}</style><style>body{background:#f6f7f9;margin:0;padding:24px;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}</style>` +
    `</head><body>${rillDefault}</body></html>`);
  console.log('html snapshots written to ' + outDir);
}

/* ---------- pomodoro: never let a missing require leak a crash ---------- */
process.exit(failures === 0 ? 0 : 1);
})();
