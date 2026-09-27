#!/usr/bin/env node
/**
 * Feedback loop: after a prior solicitud (confirm/cancel/etc), starting a NEW
 * "Sacar un turno" must INSERT a pending turno row — not UPDATE the old one.
 *
 * Symptom: patient gets "Recibimos tu solicitud de turno" but dashboard shows
 * no new pendiente (old Cancelado/Confirmado row was quietly patched).
 *
 * Run: node scripts/test-recepcion-rebook.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const workflow = JSON.parse(
  fs.readFileSync(path.join(root, 'n8n', 'workflows', '03-booking-flow.json'), 'utf8')
);
const builder = fs.readFileSync(
  path.join(root, 'scripts', 'build-lean-03-workflow.py'),
  'utf8'
);

function node(name) {
  const n = workflow.nodes.find((x) => x.name === name);
  if (!n) throw new Error(`missing node ${name}`);
  return n;
}

function decideIsUpdate(datos) {
  // Mirror of Build recepcion + sql decision (must stay in sync after fix).
  const isUpdate = !!(datos.solicitud_id) && !!datos.is_correction;
  return isUpdate;
}

let failed = 0;
function check(name, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failed += 1;
}

const startPedido = node('Start awaiting_pedido_datos').parameters.query || '';
const recepcion = node('Build recepcion + sql').parameters.jsCode || '';
const parseBlob = node('Parse blob').parameters.jsCode || '';
const startCorr = (workflow.nodes.find((x) => x.name === 'Start awaiting_correccion') || {})
  .parameters?.query || '';

// --- Behavioral decision (what recepción should do) ---
check(
  'new booking with leftover solicitud_id (no is_correction) → INSERT',
  decideIsUpdate({ solicitud_id: 42, is_correction: false }) === false,
  'must not UPDATE cancelled/confirmed row'
);
check(
  'explicit Corregir datos (is_correction + solicitud_id) → UPDATE',
  decideIsUpdate({ solicitud_id: 42, is_correction: true }) === true
);

// --- Source contracts (go red until wiring matches) ---
check(
  'Start awaiting_pedido_datos clears solicitud_id (fresh context)',
  /JSON_REMOVE[\s\S]*solicitud_id|context\s*=\s*JSON_OBJECT\s*\(/.test(startPedido),
  startPedido.slice(0, 120).replace(/\s+/g, ' ')
);

check(
  'Build recepcion isUpdate requires is_correction (not bare solicitud_id)',
  /isUpdate\s*=\s*!!\s*\(\s*datos\.solicitud_id\s*\)\s*&&/.test(recepcion) ||
    /isUpdate\s*=\s*!!\s*\(\s*datos\.solicitud_id\s*&&\s*datos\.is_correction/.test(
      recepcion
    ),
  'bare !!(datos.solicitud_id) rebooks into the old row'
);

check(
  'Parse blob is_correction is not bare !!ctx.solicitud_id',
  /is_correction:\s*correcting/.test(parseBlob) &&
    /awaiting_correccion_datos/.test(parseBlob) &&
    !/\|\|\s*!!ctx\.solicitud_id/.test(parseBlob),
  'leftover id must not mark a new Pedido as Corrección'
);

check(
  'builder source matches recepción is_correction guard',
  /isUpdate = !!\(datos\.solicitud_id\) and !!datos\.is_correction|isUpdate = !!\(datos\.solicitud_id && datos\.is_correction\)|isUpdate = !!\(datos\.solicitud_id\) && !!datos\.is_correction/.test(
    builder.replace(/\s+/g, ' ')
  ) ||
    /isUpdate = !!\(datos\.solicitud_id\) && !!datos\.is_correction/.test(builder)
);

check(
  'Start awaiting_correccion keeps/marks correction (solicitud_id stays usable)',
  /awaiting_correccion_datos/.test(startCorr)
);

if (failed) {
  console.error(`\n${failed} failed — recepción rebook still unsafe`);
  process.exit(1);
}
console.log(`\nAll checks passed`);
