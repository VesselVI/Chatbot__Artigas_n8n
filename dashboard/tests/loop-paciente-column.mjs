#!/usr/bin/env node
/**
 * Layout loop: solicitudes must fit without a forced wide min-width,
 * Paciente must keep a share, Acciones/Chat must keep a share.
 *
 * Usage: node dashboard/tests/loop-paciente-column.mjs
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const html = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../templates/index.html'),
  'utf8'
);

function colWidth(name) {
  const m = html.match(
    new RegExp(`\\.solicitudes-table col\\.c-${name}\\s*\\{([^}]*)\\}`)
  );
  if (!m) return null;
  const pct = m[1].match(/width:\s*([\d.]+)%/);
  const rem = m[1].match(/width:\s*([\d.]+)rem/);
  const auto = /width:\s*auto/.test(m[1]);
  return {
    pct: pct ? Number(pct[1]) : null,
    rem: rem ? Number(rem[1]) : null,
    auto,
  };
}

const tableBlock = html.match(/\.solicitudes-table\s*\{([^}]*)\}/);
const tableMin = tableBlock
  ? tableBlock[1].match(/min-width:\s*([\d.]+)(rem|px)/)
  : null;
const sidebar = html.match(/--sidebar-width:\s*([\d.]+)rem/);
const scrollX = html.match(
  /\.solicitudes-scroll\s*\{[^}]*overflow-x:\s*(\w+)/
);

const paciente = colWidth('paciente');
const acciones = colWidth('acciones');
const chat = colWidth('chat');
const pctSum = [
  'tipo',
  'hora',
  'paciente',
  'dni',
  'tel',
  'medico',
  'detalle',
  'obra',
  'estado',
  'acciones',
  'chat',
].reduce((s, n) => s + (colWidth(n)?.pct || 0), 0);

const report = {
  sidebarRem: sidebar ? Number(sidebar[1]) : null,
  tableMin: tableMin ? `${tableMin[1]}${tableMin[2]}` : 'none/0',
  overflowX: scrollX ? scrollX[1] : null,
  paciente,
  acciones,
  chat,
  pctSum: Math.round(pctSum * 10) / 10,
};

const failWideMin =
  tableMin &&
  ((tableMin[2] === 'rem' && Number(tableMin[1]) >= 50) ||
    (tableMin[2] === 'px' && Number(tableMin[1]) >= 900));
const failSidebar = report.sidebarRem == null || report.sidebarRem > 11;
const failPaciente = !paciente || paciente.auto || (paciente.pct || 0) < 8;
const failActions =
  !acciones || (acciones.pct || 0) < 6 || !chat || (chat.pct || 0) < 4;
const failScroll = report.overflowX === 'auto' || report.overflowX === 'scroll';
const failSum = pctSum < 95 || pctSum > 105;

const fail =
  failWideMin ||
  failSidebar ||
  failPaciente ||
  failActions ||
  failScroll ||
  failSum;

console.log(JSON.stringify(report, null, 2));
console.log('---');
if (fail) {
  console.log(
    'RED layout:',
    [
      failWideMin && 'table min-width forces H-scroll',
      failSidebar && 'sidebar too wide',
      failPaciente && 'paciente share too small',
      failActions && 'acciones/chat share too small',
      failScroll && 'overflow-x allows page scroll',
      failSum && `col % sum ${pctSum}`,
    ]
      .filter(Boolean)
      .join('; ')
  );
  process.exit(1);
}
console.log(
  `GREEN: sidebar ${report.sidebarRem}rem, cols ${report.pctSum}%, no forced H-scroll`
);
process.exit(0);
