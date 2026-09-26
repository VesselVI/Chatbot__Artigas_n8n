#!/usr/bin/env node
/**
 * Feedback loop for Responder modal + Acciones/Chat tip stacking.
 *
 * RED when:
 *  1) Responder consulta has no modal path
 *  2) Row-hover asymmetrically boosts one of Acciones/Chat over the other
 *     (tips bury under the sibling column)
 *  3) Missing equal cell-only :hover/:focus-within boost for both columns
 *
 * Usage: node dashboard/tests/loop-responder-tips-static.mjs
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'templates/index.html'), 'utf8');

const responderBind = html.match(
  /tbody\.querySelectorAll\('\[data-responder-consulta-id\]'\)\.forEach\(btn => \{[\s\S]*?\n      \}\);/
);
const bindBlock = responderBind ? responderBind[0] : '';
const opensModal =
  /openRespuestaConsultaModal/.test(bindBlock) ||
  /respuestaConsultaModal/.test(bindBlock);
const hasModalDom = /id="respuestaConsultaModal"/.test(html);
const postsApi =
  /responder-consulta/.test(html) && /respuesta-consulta-submit/.test(html);

const rowBoostAcciones = /\.solicitud-row:hover\s+\.col-acciones/.test(html);
const rowBoostChat = /\.solicitud-row:hover\s+\.col-chat/.test(html);
const rowBoostStripHigh = /\.solicitud-row:hover\s+\.acciones-strip[\s\S]{0,80}z-index:\s*(4[6-9]|[5-9]\d)/.test(
  html
);

// Shared cell-only rule with equal z for both columns.
const cellOnlyBlock = html.match(
  /\.col-acciones:hover,[\s\S]*?\.col-chat:hover,[\s\S]*?\.col-chat:focus-within\s*\{[\s\S]*?z-index:\s*(\d+)[\s\S]*?\}/
);
const cellOnlyZ = cellOnlyBlock ? Number(cellOnlyBlock[1]) : null;
const equalCellBoost = cellOnlyZ != null && cellOnlyZ >= 40;

const tipsAsymmetric =
  rowBoostAcciones || rowBoostChat || rowBoostStripHigh || !equalCellBoost;

const report = {
  opens_modal: opensModal,
  has_modal_dom: hasModalDom,
  posts_api: postsApi,
  rowBoostAcciones,
  rowBoostChat,
  rowBoostStripHigh,
  cellOnlyZ,
  equalCellBoost,
};

console.log(JSON.stringify(report, null, 2));
console.log('---');

const failModal = !(opensModal && hasModalDom && postsApi);
const failTip = tipsAsymmetric;

console.log(
  failModal
    ? 'RED modal: missing Responder consulta modal wiring'
    : 'GREEN modal: openRespuestaConsultaModal + DOM + submit'
);
console.log(
  failTip
    ? `RED tip: asymmetric/row stacking (rowAcciones=${rowBoostAcciones} rowChat=${rowBoostChat} stripHigh=${rowBoostStripHigh} cellOnlyZ=${cellOnlyZ})`
    : `GREEN tip: equal cell-only boost z=${cellOnlyZ} (no row-hover column race)`
);

process.exit(failModal || failTip ? 1 : 0);
