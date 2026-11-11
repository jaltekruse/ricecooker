#!/usr/bin/env node
/*
 * Converts TeX to MathML with MathJax (https://www.mathjax.org), which understands far more LaTeX than pandoc's
 * converter: \cancel, \color, \boxed, \ce (mhchem), \tag, commutative diagrams, and the rest of MathJax's TeX packages.
 * Used by ricecooker/utils/markdown_kpub.py.
 *
 *   echo '[{"tex": "\\frac{a}{b}", "display": false}, ...]' | node tex2mathml.js
 *
 * prints a JSON list with, for each expression, {"mathml": "<math ...>...</math>"}, or {"error": "..."} when MathJax
 * can't convert it. The MathML keeps the TeX it was made from, in <annotation encoding="application/x-tex">, so the
 * expression's source travels with it.
 *
 * Needs the mathjax-full npm package (version 3): its directory is found from MATHJAX_FULL_PATH, or by node's module
 * resolution (NODE_PATH), see markdown_kpub.find_mathjax.
 */
'use strict';

const path = require('path');

const root = process.env.MATHJAX_FULL_PATH || path.dirname(require.resolve('mathjax-full/package.json'));
const load = (module) => require(path.join(root, 'js', module));

const { mathjax } = load('mathjax.js');
const { TeX } = load('input/tex.js');
const { AllPackages } = load('input/tex/AllPackages.js');
const { liteAdaptor } = load('adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = load('handlers/html.js');
const { SerializedMmlVisitor } = load('core/MmlTree/SerializedMmlVisitor.js');

RegisterHTMLHandler(liteAdaptor());

const tex = new TeX({
	// bussproofs needs an output jax that measures what it lays out, which converting to MathML doesn't have, and
	// noundefined shows unknown macros in red rather than reporting them
	packages: AllPackages.filter((name) => name !== 'bussproofs' && name !== 'noundefined'),
	// every package is already loaded, so \require{...} has nothing left to load
	macros: { require: ['', 1] },
	formatError: (jax, error) => {
		throw error;
	},
});
const document = mathjax.document('', { InputJax: tex });
const visitor = new SerializedMmlVisitor();

const escapeXML = (text) => text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function convert({ tex: source, display }) {
	const node = document.convert(source, { display: Boolean(display) });
	const mathml = visitor.visitTree(node);
	const error = mathml.match(/data-mjx-error="([^"]*)"/);
	if (error) {
		throw new Error(error[1]);
	}
	// <math ...>children</math> -> <math ...><semantics><mrow>children</mrow><annotation>TeX</annotation></semantics></math>
	const match = mathml.match(/^(<math\b[^>]*>)([\s\S]*)(<\/math>)\s*$/);
	if (!match) {
		throw new Error('unexpected MathML from MathJax');
	}
	return (
		match[1] +
		'<semantics><mrow>' +
		match[2] +
		'</mrow><annotation encoding="application/x-tex">' +
		escapeXML(source) +
		'</annotation></semantics>' +
		match[3]
	);
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => (input += chunk));
process.stdin.on('end', () => {
	const results = JSON.parse(input || '[]').map((item) => {
		try {
			return { mathml: convert(item) };
		} catch (e) {
			return { error: String((e && e.message) || e) };
		}
	});
	process.stdout.write(JSON.stringify(results));
});
