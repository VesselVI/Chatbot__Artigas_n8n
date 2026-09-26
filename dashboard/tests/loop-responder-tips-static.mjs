#!/usr/bin/env node
/**
 * Feedback loop (no Playwright): static checks against live index.html
 * matching the two user symptoms.
 *
 * RED when:
 *  1) Responder consulta click path does not open a modal
 *  2) CSS stacking predicts acciones tips bury under Chat
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
  /openConfirmModal/.test(bindBlock) ||
  /respuestaConsultaModal/.test(bindBlock) ||
  /confirmModal/.test(bindBlock);
const hasModalDom = /id="respuestaConsultaModal"/.test(html);
const postsApi =
  /responder-consulta/.test(html) && /respuesta-consulta-submit/.test(html);

function zAfter(pattern) {
  const m = html.match(pattern);
  if (!m) return null;
  const z = m[0].match(/z-index:\s*(\d+)/);
  return z ? Number(z[1]) : null;
}

const tipZ = zAfter(/\.btn-action \.btn-tip \{[\s\S]*?z-index:\s*\d+/);
const stripHoverZ = zAfter(
  /\.solicitud-row:hover \.acciones-strip,[\s\S]*?z-index:\s*\d+/
);
// Prefer the Acciones-specific boost if present (must be > col-chat).
const colAccionesHoverZ = zAfter(
  /\.solicitud-row:hover \.col-acciones,[\s\S]*?z-index:\s*\d+/
);
const colChatHoverZ = zAfter(
  /\.solicitud-row:hover \.col-chat,[\s\S]*?z-index:\s*\d+/
);

const tipBuriedByStacking =
  colChatHoverZ != null &&
  (colAccionesHoverZ == null || colAccionesHoverZ <= colChatHoverZ) &&
  (stripHoverZ == null || stripHoverZ < colChatHoverZ);

const report = {
  responder_bind_found: Boolean(bindBlock),
  posts_responder_api: postsApi,
  opens_modal: opensModal,
  has_modal_dom: hasModalDom,
  tipZ,
  stripHoverZ,
  colAccionesHoverZ,
  colChatHoverZ,
  tipBuriedByStacking,
};

console.log(JSON.stringify(report, null, 2));
console.log('---');

const failModal = !(opensModal && hasModalDom);
const failTip = tipBuriedByStacking;

console.log(
  failModal
    ? 'RED modal: Responder consulta has no modal open path / DOM'
    : 'GREEN modal: openRespuestaConsultaModal + #respuestaConsultaModal'
);
console.log(
  failTip
    ? `RED tip: Chat stacking still wins (acciones=${colAccionesHoverZ} chat=${colChatHoverZ} strip=${stripHoverZ})`
    : `GREEN tip: col-acciones z (${colAccionesHoverZ}) > col-chat z (${colChatHoverZ})`
);

process.exit(failModal || failTip ? 1 : 0);
