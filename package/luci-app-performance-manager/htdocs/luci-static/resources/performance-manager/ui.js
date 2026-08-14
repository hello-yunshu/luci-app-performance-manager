'use strict';

function badge(text, kind) {
	return E('span', {
		'class': 'label ' + (kind || ''),
		'role': 'status',
		'aria-label': text,
		'style': 'display:inline-block;margin:0 .35rem .35rem 0;padding:.25rem .5rem;border:1px solid var(--border-color-medium,#bbb);border-radius:.35rem;font-weight:600'
	}, [ text ]);
}

function card(title, body) {
	return E('div', {
		'class': 'cbi-section',
		'style': 'border:1px solid var(--border-color-medium,#ddd);border-radius:.55rem;padding:1rem;margin:.75rem 0'
	}, [ E('h3', {}, [ title ]), body ]);
}

function kv(rows) {
	return E('dl', { 'style': 'display:grid;grid-template-columns:minmax(10rem,1fr) 2fr;gap:.45rem .9rem;margin:0' },
		rows.flatMap(function(r) { return [ E('dt', { 'style': 'font-weight:600' }, [ r[0] ]), E('dd', { 'style': 'margin:0;word-break:break-word' }, [ r[1] == null ? '—' : String(r[1]) ]) ]; }));
}

function jsonBox(obj, label) {
	return E('details', { 'style': 'margin:.6rem 0' }, [
		E('summary', { 'tabindex': '0' }, [ label || _('Raw JSON') ]),
		E('pre', { 'style': 'max-height:26rem;overflow:auto;white-space:pre-wrap' }, [ JSON.stringify(obj, null, 2) ])
	]);
}

return { badge: badge, card: card, kv: kv, jsonBox: jsonBox };
