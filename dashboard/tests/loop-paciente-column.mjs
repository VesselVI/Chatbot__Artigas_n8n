#!/usr/bin/env node
/**
 * RED if Paciente column can be crushed to zero under fixed table layout.
 * Usage: node dashboard/tests/loop-paciente-column.mjs
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const html = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../templates/index.html'),
  'utf8'
);

const pacienteCol = html.match(
  /\.solicitudes-table col\.c-paciente\s*\{([^}]*)\}/
);
const rule = pacienteCol ? pacienteCol[1] : '';
const widthAuto = /width:\s*auto/.test(rule);
const widthRem = rule.match(/width:\s*([\d.]+)rem/);
const tableMin = html.match(/\.solicitudes-table\s*\{[^}]*min-width:\s*([\d.]+)rem/);
const hasHeader = /<th[^>]*col-paciente[^>]*>Paciente<\/th>/.test(html);
const hasCell = /col-paciente cell-paciente/.test(html);

const report = {
  hasHeader,
  hasCell,
  widthAuto,
  widthRem: widthRem ? Number(widthRem[1]) : null,
  tableMinRem: tableMin ? Number(tableMin[1]) : null,
};

const fail =
  !hasHeader ||
  !hasCell ||
  widthAuto ||
  report.widthRem == null ||
  report.widthRem < 7 ||
  report.tableMinRem == null ||
  report.tableMinRem < 60;

console.log(JSON.stringify(report, null, 2));
console.log('---');
console.log(
  fail
    ? 'RED: Paciente column can collapse / missing'
    : `GREEN: Paciente width ${report.widthRem}rem, table min-width ${report.tableMinRem}rem`
);
process.exit(fail ? 1 : 0);
