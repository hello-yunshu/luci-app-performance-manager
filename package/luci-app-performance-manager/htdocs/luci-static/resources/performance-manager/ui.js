'use strict';
'require baseclass';

function ensureStyles() {
	if (typeof document === 'undefined' || !document.head || document.querySelector('link[data-performance-manager-style]')) return;
	const link = document.createElement('link');
	link.rel = 'stylesheet';
	link.dataset.performanceManagerStyle = 'true';
	link.href = (typeof L !== 'undefined' && L.resource) ? L.resource('performance-manager/ui.css') : '/luci-static/resources/performance-manager/ui.css';
	document.head.appendChild(link);
}

function badge(text, kind) {
	const tone = ({ success: 'success', warning: 'warning', danger: 'important', neutral: '' })[kind || 'neutral'] || '';
	return E('span', {
		'class': ('label ' + tone).trim(),
		'role': 'status',
		'aria-label': text
	}, [ text ]);
}

function page(title, description, content) {
	ensureStyles();
	const body = (Array.isArray(content) ? content : [ content ]).filter(function(node) { return node != null; });
	return E('div', { 'class': 'cbi-map' }, [
		E('h2', { 'name': 'content' }, [ title ]),
		description ? E('p', { 'class': 'cbi-map-descr' }, [ description ]) : null
	].concat(body));
}

function card(title, body) {
	return E('div', { 'class': 'cbi-section' }, [ E('h3', {}, [ title ]), body ]);
}

function kv(rows) {
	return E('div', {}, rows.map(function(r) {
		const value = r[1] == null ? '—' : (typeof r[1] === 'string' || typeof r[1] === 'number' ? String(r[1]) : r[1]);
		return E('div', { 'class': 'cbi-value' }, [
			E('label', { 'class': 'cbi-value-title' }, [ r[0] ]),
			E('div', { 'class': 'cbi-value-field' }, [ value ])
		]);
	}));
}

function jsonBox(obj, label) {
	return E('details', { 'class': 'pm-disclosure' }, [
		E('summary', {}, [ label || _('Raw JSON') ]),
		E('pre', {}, [ JSON.stringify(obj, null, 2) ])
	]);
}

function grid(items) {
	return E('div', {}, items);
}

function toolbar(items) {
	return E('div', {}, items);
}

function note(text, kind) {
	const tone = ({ success: 'success', warning: 'warning', danger: 'danger', info: 'info' })[kind || 'info'] || 'info';
	return E('div', { 'class': 'alert-message ' + tone, 'role': 'status' }, [ text ]);
}

function field(label, control, help) {
	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title' }, [ label ]),
		E('div', { 'class': 'cbi-value-field' }, [
			control,
			help ? E('div', { 'class': 'cbi-value-description' }, [ help ]) : null
		])
	]);
}

function inset(title, body) {
	return E('div', { 'class': 'cbi-section' }, [
		title ? E('h4', {}, [ title ]) : null,
		body
	]);
}

function tableWrap(table) {
	return table;
}

function setBusy(button, busyLabel) {
	const original = button.textContent;
	button.disabled = true;
	button.setAttribute('aria-busy', 'true');
	button.classList.add('pm-button--busy');
	button.replaceChildren(busyLabel || _('Working...'));
	return function() {
		button.disabled = false;
		button.removeAttribute('aria-busy');
		button.classList.remove('pm-button--busy');
		button.replaceChildren(original);
	};
}

return baseclass.extend({ badge: badge, card: card, field: field, grid: grid, inset: inset, jsonBox: jsonBox, kv: kv, note: note, page: page, setBusy: setBusy, tableWrap: tableWrap, toolbar: toolbar });
