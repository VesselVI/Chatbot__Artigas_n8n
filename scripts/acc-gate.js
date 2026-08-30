'use strict';

/**
 * Accumulation gate for workflow 01 (Phase 2 / ADR-0002).
 * Free-text in booking-related states is buffered; buttons/media bypass.
 */

const ACC_STATES = new Set([
  'idle',
  'menu_shown',
  'awaiting_pedido_datos',
  'awaiting_correccion_datos',
]);

function cleanFragment(texto) {
  return String(texto || '')
    .replace(/\n?__cw_in_reply_to__:\S+/g, '')
    .trim();
}

function phoneKey(telefono) {
  return String(telefono || '').replace(/[^0-9]/g, '') || 'unknown';
}

/**
 * @param {{ estado?: string, boton_id?: string, tipo?: string, texto?: string, telefono?: string }} m
 * @returns {{ accumulate: boolean, acc_fragment: string, acc_list_key: string, acc_ver_key: string }}
 */
function decideAccumulate(m) {
  const estado = m.estado || 'idle';
  const boton = String(m.boton_id || '').trim();
  const tipo = String(m.tipo || '');
  const fragment = cleanFragment(m.texto);
  const phone = phoneKey(m.telefono);

  const accumulate =
    ACC_STATES.has(estado) &&
    !boton &&
    tipo !== 'media' &&
    tipo !== 'interactive' &&
    fragment.length > 0;

  return {
    accumulate,
    acc_fragment: fragment,
    acc_list_key: `acc:frags:${phone}`,
    acc_ver_key: `acc:ver:${phone}`,
  };
}

/**
 * Space-join Redis list fragments into one texto.
 * @param {unknown} frags
 */
function joinFragments(frags) {
  const arr = Array.isArray(frags) ? frags : frags == null ? [] : [frags];
  return arr
    .map((s) => String(s || '').trim())
    .filter(Boolean)
    .join(' ');
}

module.exports = {
  ACC_STATES,
  cleanFragment,
  phoneKey,
  decideAccumulate,
  joinFragments,
};
