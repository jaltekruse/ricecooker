#!/usr/bin/env node
/*
 * Finds the files the WeBWorK problems in a book need, for chef_pretext.py to bundle them with the in-browser PG
 * engine (https://github.com/jaltekruse/webwork-wasm), so learners can work on the problems offline in Kolibri.
 *
 *   node webwork_bundle.js <engine dir> <request json> <output dir>
 *
 * <engine dir> is a build of the engine (pg-engine.js, emperl.*, pg.data, ...). The request is
 *   { "problems": [ { "path": "Library/Rochester/setDerivatives1/s2_1_3.pg", "seed": 22 }, ... ],
 *     "templates": [ "<dir or URL>", { "prefix": "Library/", "location": "<dir or URL>" }, ... ] }
 * where each template location is laid out like a WeBWorK course's templates directory (with Library/ for the Open
 * Problem Library, and a course's own problems), or, with a prefix, like the part of it under the prefix (e.g. the
 * Open Problem Library's OpenProblemLibrary directory for Library/). They are searched in order. A location can be a
 * local directory or a URL.
 *
 * Each problem is rendered with the engine in node, which loads the problem, the problems and macros it includes,
 * and its images, from the template locations as PG asks for them. Those files are written to <output dir>, laid out
 * the same way, and <output dir>/webwork-problems.json says which problems rendered without errors.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

const [engineDir, requestFile, outDir] = process.argv.slice(2).map((p) => path.resolve(p));
if (!outDir) {
	console.error('usage: node webwork_bundle.js <engine dir> <request json> <output dir>');
	process.exit(2);
}
const request = JSON.parse(fs.readFileSync(requestFile, 'utf8'));
const dist = engineDir + '/';
globalThis.require = require; // used by Emscripten's generated code in node
globalThis.__dirname = dist;
const PGEngine = require(dist + 'pg-engine.js');

// The files found in the template locations, by path in the templates directory
const found = new Map();
const missing = new Set();
const isURL = (location) => /^https?:\/\//.test(location);

function download(url) {
	try {
		// curl, as it's synchronous, which PG needs, and takes the proxy settings from the environment
		return execFileSync('curl', ['-sSfL', '--retry', '3', url], { maxBuffer: 1 << 30, stdio: ['ignore', 'pipe', 'ignore'] });
	} catch (e) {
		return null;
	}
}

// Find a file in the templates directory, in the first template location that has it
function findTemplate(rel) {
	if (found.has(rel)) return found.get(rel);
	if (missing.has(rel)) return null;
	for (const template of request.templates) {
		const { prefix = '', location } = typeof template === 'string' ? { location: template } : template;
		if (!rel.startsWith(prefix)) continue;
		const relative = rel.slice(prefix.length);
		let data = null;
		if (isURL(location)) {
			data = download(location.replace(/\/*$/, '/') + relative.split('/').map(encodeURIComponent).join('/'));
		} else {
			try {
				data = fs.readFileSync(path.join(location, relative));
			} catch (e) {
				data = null;
			}
		}
		if (data) {
			found.set(rel, data);
			return data;
		}
	}
	missing.add(rel);
	return null;
}

// The engine loads mounted files from "URLs", here template:<path in the templates directory>
const TEMPLATE = 'template:';
const fetchSync = (url) => {
	if (url.startsWith(TEMPLATE)) return findTemplate(decodeURIComponent(url.slice(TEMPLATE.length)));
	try {
		return fs.readFileSync(url);
	} catch (e) {
		return null;
	}
};
const loadScript = (file) => vm.runInThisContext(fs.readFileSync(file, 'utf8'), { filename: file });

// Mount each directory the problems are in (Library/, a course's own directories), and the course's macros
const topDirs = new Set(['macros']);
for (const problem of request.problems) topDirs.add(problem.path.split('/')[0]);
const mounts = {};
for (const dir of topDirs) mounts[dir + '/'] = TEMPLATE + dir + '/';

const firstLines = (text) => text.split('\n').filter((l) => /\S/.test(l) && !/^ERRORS from evaluating/.test(l)).slice(0, 3).join(' | ');

(async () => {
	const engine = new PGEngine({ baseURL: dist, loadScript, fetchSync, mounts });
	await engine.init();
	const results = {};
	for (const problem of request.problems) {
		if (results[problem.path]) continue;
		const result = { ok: false };
		if (!findTemplate(problem.path)) {
			result.error = 'not found in the template locations';
		} else {
			try {
				const rendered = engine.render({ sourceFilePath: problem.path, problemSeed: problem.seed ?? 1 });
				result.ok = !rendered.errors && Object.keys(rendered.answers ?? {}).length > 0;
				if (rendered.errors) result.error = firstLines(rendered.errors);
				else if (!result.ok) result.error = 'no answer blanks';
				if (rendered.warnings) result.warnings = firstLines(rendered.warnings);
			} catch (e) {
				result.error = String(e && e.message ? e.message : e).slice(0, 300);
			}
		}
		results[problem.path] = result;
		console.log(`${result.ok ? 'ok    ' : 'FAILED'} ${problem.path}${result.error ? ': ' + result.error : ''}`);
	}
	for (const [rel, data] of found) {
		const file = path.join(outDir, rel);
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.writeFileSync(file, data);
	}
	fs.writeFileSync(path.join(outDir, 'webwork-problems.json'), JSON.stringify(results, null, 1));
	const ok = Object.values(results).filter((r) => r.ok).length;
	console.log(`${ok} of ${Object.keys(results).length} problems work, ${found.size} files in ${outDir}`);
	process.exit(0);
})().catch((e) => {
	console.error(e);
	process.exit(1);
});
