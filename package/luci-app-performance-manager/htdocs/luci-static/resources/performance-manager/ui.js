'use strict';

const FOOTER_VERSION = '@PKG_VERSION@';
const FOOTER_OPTIONS = {
	project: _('Performance Manager'),
	repoUrl: 'https://github.com/hello-yunshu/luci-app-performance-manager'
};

function ensureStyles() {
	if (typeof document === 'undefined' || !document.head || document.querySelector('link[data-performance-manager-style]')) return;
	const link = document.createElement('link');
	link.rel = 'stylesheet';
	link.dataset.performanceManagerStyle = 'true';
	link.href = (typeof L !== 'undefined' && L.resource) ? L.resource('performance-manager/ui.css') : '/luci-static/resources/performance-manager/ui.css';
	document.head.appendChild(link);
}

function badge(text, kind) {
	return E('span', {
		'class': 'label pm-badge pm-badge--' + (kind || 'neutral'),
		'role': 'status',
		'aria-label': text
	}, [ text ]);
}

function page(title, description, content, eyebrow) {
	ensureStyles();
	return E('div', { 'class': 'pm-shell' }, [
		E('header', { 'class': 'pm-page-header' }, [
			E('div', { 'class': 'pm-page-heading' }, [
				E('div', { 'class': 'pm-eyebrow' }, [ eyebrow || _('Performance Manager') ]),
				E('h2', { 'class': 'pm-page-title' }, [ title ]),
				description ? E('p', { 'class': 'pm-page-description' }, [ description ]) : null
			]),
			E('div', { 'class': 'pm-page-mark', 'aria-hidden': 'true' }, [ E('span'), E('span'), E('span') ])
		]),
		E('div', { 'class': 'pm-page-content' }, Array.isArray(content) ? content : [ content ]),
		renderFooter()
	]);
}

function card(title, body, tone) {
	return E('div', {
		'class': 'cbi-section pm-card' + (tone ? ' pm-card--' + tone : '')
	}, [ E('h3', { 'class': 'pm-card-title' }, [ title ]), body ]);
}

function kv(rows) {
	return E('dl', { 'class': 'pm-kv' },
		rows.flatMap(function(r) { return [ E('dt', {}, [ r[0] ]), E('dd', {}, [ r[1] == null ? '—' : String(r[1]) ]) ]; }));
}

function jsonBox(obj, label) {
	return E('details', { 'class': 'pm-disclosure' }, [
		E('summary', { 'tabindex': '0' }, [ label || _('Raw JSON') ]),
		E('pre', {}, [ JSON.stringify(obj, null, 2) ])
	]);
}

function grid(items, className) {
	return E('div', { 'class': 'pm-card-grid' + (className ? ' ' + className : '') }, items);
}

function toolbar(items) {
	return E('div', { 'class': 'pm-toolbar' }, items);
}

function note(text, kind) {
	return E('div', { 'class': 'pm-note pm-note--' + (kind || 'info'), 'role': 'status' }, [ text ]);
}

function footerSeparator(extraClass) {
	const className = 'ys-tool-footer-separator' + (extraClass ? ' ' + extraClass : '');
	return E('span', { 'class': className }, [ '\u00a0·\u00a0' ]);
}

function footerIcon(name) {
	if (typeof document === 'undefined' || !document.createElementNS) return null;
	const svgNS = 'http://www.w3.org/2000/svg';
	const svg = document.createElementNS(svgNS, 'svg');
	const path = document.createElementNS(svgNS, 'path');

	svg.setAttribute('class', 'ys-tool-footer-link-icon ' + name);
	svg.setAttribute('viewBox', '0 0 24 24');
	svg.setAttribute('width', '14');
	svg.setAttribute('height', '14');
	svg.setAttribute('aria-hidden', 'true');
	svg.setAttribute('focusable', 'false');
	svg.setAttribute('style', 'width:1em;height:1em;max-width:1em;max-height:1em;display:inline-block;flex:0 0 auto;vertical-align:-0.125em');

	if (name === 'github') {
		path.setAttribute('fill', 'currentColor');
		path.setAttribute('d', 'M12 2C6.48 2 2 6.58 2 12.26c0 4.53 2.87 8.37 6.84 9.73.5.09.68-.22.68-.49v-1.9c-2.78.62-3.37-1.22-3.37-1.22-.45-1.19-1.11-1.5-1.11-1.5-.91-.64.07-.63.07-.63 1 .07 1.53 1.06 1.53 1.06.9 1.57 2.35 1.12 2.92.86.09-.67.35-1.12.63-1.38-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05A9.36 9.36 0 0 1 12 6.97c.85 0 1.71.12 2.51.34 1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.8-4.57 5.06.36.32.68.94.68 1.9v2.82c0 .27.18.59.69.49A10.24 10.24 0 0 0 22 12.26C22 6.58 17.52 2 12 2z');
	} else if (name === 'x') {
		path.setAttribute('fill', 'currentColor');
		path.setAttribute('d', 'M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.451-6.231zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z');
	} else {
		return null;
	}

	svg.appendChild(path);
	return svg;
}

function footerLink(href, label, icon) {
	const children = [];
	const iconNode = icon ? footerIcon(icon) : null;
	if (iconNode) children.push(iconNode);
	children.push(E('span', { 'class': 'ys-tool-footer-link-label' }, [ label ]));
	return E('a', {
		'class': 'ys-tool-footer-link' + (icon ? ' ' + icon : ''),
		'href': href,
		'target': '_blank',
		'rel': 'noopener noreferrer'
	}, children);
}

function footerVersion(version) {
	const value = version && version !== '-' ? version : FOOTER_VERSION;
	if (!value || value === '-' || value.charAt(0) === '@') return '';
	return /^v/i.test(value) ? value : 'v' + value;
}

function renderFooter(options) {
	options = options || {};
	const project = options.project || FOOTER_OPTIONS.project;
	const version = footerVersion(options.version);
	const repoUrl = options.repoUrl || FOOTER_OPTIONS.repoUrl;

	return E('footer', { 'class': 'ys-tool-footer' }, [
		E('div', { 'class': 'ys-tool-footer-brand' }, [
			E('span', { 'class': 'ys-tool-footer-mark' }, [ '云云舒' ]),
			footerSeparator('ys-tool-footer-title-separator'),
			E('span', { 'class': 'ys-tool-footer-title' }, [ project ]),
			version ? footerSeparator('ys-tool-footer-version-separator') : '',
			version ? E('span', { 'class': 'ys-tool-footer-version' }, [ version ]) : ''
		]),
		E('div', { 'class': 'ys-tool-footer-links' }, [
			E('span', { 'class': 'ys-tool-footer-project-link' }, [ footerLink(repoUrl, _('Project')) ]),
			footerSeparator('ys-tool-footer-project-separator'),
			footerLink('https://github.com/hello-yunshu', 'GitHub', 'github'),
			footerSeparator(),
			footerLink('https://x.com/yunyunyshu', '@云云舒', 'x')
		])
	]);
}

return { badge: badge, card: card, grid: grid, jsonBox: jsonBox, kv: kv, note: note, page: page, renderFooter: renderFooter, toolbar: toolbar };
