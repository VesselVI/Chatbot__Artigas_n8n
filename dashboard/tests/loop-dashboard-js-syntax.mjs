#!/usr/bin/env node
/**
 * RED if dashboard inline script has a SyntaxError (kills rows + stats).
 * Usage: node dashboard/tests/loop-dashboard-js-syntax.mjs
 */
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'templates/index.html'), 'utf8');

// Last big inline script block (app logic after bootstrap CDN).
const scripts = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)];
const inline = scripts.map((m) => m[1]).join('\n');
// Jinja placeholders → valid JS literals for syntax check
const js = inline
  .replaceAll('{{ all_times_json | safe }}', '[]')
  .replaceAll("{{ week_start }}", '2026-01-01');

const tmp = join(root, 'tests/_syntax_check_tmp.js');
writeFileSync(tmp, js);
const r = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' });
try {
  unlinkSync(tmp);
} catch (_) {}

const dupCancel = (js.match(/\blet cancelModal\b/g) || []).length;
console.log(
  JSON.stringify(
    {
      exit: r.status,
      stderr: (r.stderr || '').trim().slice(0, 500),
      let_cancelModal_count: dupCancel,
    },
    null,
    2
  )
);
console.log('---');
if (r.status !== 0) {
  console.log('RED: dashboard inline script SyntaxError');
  process.exit(1);
}
if (dupCancel > 1) {
  console.log(`RED: duplicate let cancelModal (${dupCancel}x)`);
  process.exit(1);
}
console.log('GREEN: inline script parses; cancelModal declared once');
process.exit(0);
