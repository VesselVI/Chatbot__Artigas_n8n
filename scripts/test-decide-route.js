#!/usr/bin/env node
/**
 * Unit tests for Decide Route logic extracted from 01-entry-router.json.
 * Run: node scripts/test-decide-route.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const workflowPath = path.join(__dirname, '..', 'n8n', 'workflows', '01-entry-router.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const decideNode = workflow.nodes.find((n) => n.name === 'Decide Route');
if (!decideNode) {
  console.error('Decide Route node not found');
  process.exit(1);
}

function makeRunner(jsCode) {
  const fn = new Function('$input', jsCode);
  return (item) => {
    const $input = {
      first: () => ({ json: item }),
    };
    return fn($input)[0].json;
  };
}

const runRoute = makeRunner(decideNode.parameters.jsCode);

function base(overrides = {}) {
  return {
    telefono: '543816224165',
    tipo: 'text',
    texto: '',
    boton_id: '',
    conversation_id: 24,
    account_id: 2,
    estado: 'idle',
    context: {},
    ai_intent: '',
    ai_confidence: 0,
    ...overrides,
  };
}

const tests = [
  {
    name: 'cancel intent from idle routes to cancelar_prompt',
    input: base({ texto: 'quiero cancelar un turno', estado: 'idle' }),
    expect: (r) => r.route === 'cancelar_prompt',
  },
  {
    name: 'cancel intent does not route to booking',
    input: base({ texto: 'Quiero cancelar un turno', estado: 'menu_shown' }),
    expect: (r) => r.route !== 'booking',
  },
  {
    name: 'si_generico in confirmacion solicitud routes to cancelar_collect',
    input: base({
      estado: 'confirmando_cancelacion_solicitud',
      boton_id: 'si_generico',
      texto: 'Sí',
    }),
    expect: (r) => r.route === 'cancelar_collect',
  },
  {
    name: 'typed si in confirmacion solicitud routes to cancelar_collect',
    input: base({
      estado: 'confirmando_cancelacion_solicitud',
      texto: 'si',
    }),
    expect: (r) => r.route === 'cancelar_collect',
  },
  {
    name: 'no_generico in confirmacion solicitud routes to cancelar_abort',
    input: base({
      estado: 'confirmando_cancelacion_solicitud',
      boton_id: 'no_generico',
      texto: 'No',
    }),
    expect: (r) => r.route === 'cancelar_abort',
  },
  {
    name: 're-send cancel phrase while waiting yes/no re-prompts',
    input: base({
      estado: 'confirmando_cancelacion_solicitud',
      texto: 'quiero cancelar un turno',
    }),
    expect: (r) => r.route === 'cancelar_prompt',
  },
  {
    name: 'nombre+dni in awaiting_cancelar_datos finalizes',
    input: base({
      estado: 'awaiting_cancelar_datos',
      texto: 'Juan Pérez 30111222',
    }),
    expect: (r) =>
      r.route === 'cancelar_finalize' &&
      r.captured_nombre.includes('Juan') &&
      r.captured_dni === '30111222',
  },
  {
    name: 'single given name + 8-digit DNI finalizes',
    input: base({
      estado: 'awaiting_cancelar_datos',
      texto: 'Ignacio 30111222',
    }),
    expect: (r) => r.route === 'cancelar_finalize' && r.captured_dni === '30111222',
  },
  {
    name: 'short DNI retries collect (not finalize)',
    input: base({
      estado: 'awaiting_cancelar_datos',
      texto: 'Ignacio 20202',
    }),
    expect: (r) => r.route === 'cancelar_collect',
  },
  {
    name: 'name without DNI retries collect',
    input: base({
      estado: 'awaiting_cancelar_datos',
      texto: 'Ignacio zottola caram',
    }),
    expect: (r) => r.route === 'cancelar_collect',
  },
  {
    name: 'reprogramar intent routes to reprogramar_prompt',
    input: base({ texto: 'necesito reprogramar mi turno', estado: 'idle' }),
    expect: (r) => r.route === 'reprogramar_prompt',
  },
  {
    name: 'horario text mid-booking stays on booking (not reprogramar)',
    input: base({
      estado: 'awaiting_dia_hora',
      texto: '¿Qué horario preferís?\nmar 18',
      context: { medico: 'Paulina Artigas' },
    }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'AI reprogramar mid-booking still stays on booking',
    input: base({
      estado: 'awaiting_dia_hora',
      texto: 'mar 18',
      ai_intent: 'reprogramar',
      ai_confidence: 0.95,
    }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'estudio precio mid-booking still handoffs',
    input: base({
      estado: 'awaiting_dia_hora',
      texto: 'cuanto sale un OCT?',
    }),
    expect: (r) => r.route === 'estudio_handoff',
  },
  {
    name: 'turno without cancel routes to booking',
    input: base({ texto: 'sacar un turno', estado: 'menu_shown' }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'estudio precio routes to estudio_handoff',
    input: base({ texto: 'cuanto sale un OCT?', estado: 'menu_shown' }),
    expect: (r) => r.route === 'estudio_handoff',
  },
  {
    name: 'hablar con doctor routes to estudio_handoff not faq',
    input: base({ texto: 'kiero hablar con el doctor artigas', estado: 'menu_shown' }),
    expect: (r) =>
      r.route === 'estudio_handoff' && r.handoff_reason === 'solicitud_secretaria',
  },
  {
    name: 'ser viviente routes to estudio_handoff',
    input: base({ texto: 'quiero hablar con un ser viviente', estado: 'menu_shown' }),
    expect: (r) =>
      r.route === 'estudio_handoff' && r.handoff_reason === 'solicitud_secretaria',
  },
  {
    name: 'turno with doctor still routes to booking',
    input: base({ texto: 'quiero un turno con el dr artigas', estado: 'menu_shown' }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'DNI blob on menu skips welcome',
    input: base({
      texto: 'quiero turno Juan Pérez 30111222 OSDE Artigas',
      estado: 'menu_shown',
    }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'post_solicitud first corregir routes booking',
    input: base({
      estado: 'post_solicitud',
      boton_id: 'corregir_datos',
      context: { correction_count: 0 },
    }),
    expect: (r) => r.route === 'booking',
  },
  {
    name: 'post_solicitud second corregir routes handoff',
    input: base({
      estado: 'post_solicitud',
      boton_id: 'corregir_datos',
      context: { correction_count: 1 },
    }),
    expect: (r) => r.route === 'hablar_secretaria',
  },
];

let failed = 0;
for (const t of tests) {
  try {
    const result = runRoute(t.input);
    if (!t.expect(result)) {
      failed++;
      console.error(`FAIL: ${t.name}`);
      console.error('  route:', result.route, 'boton:', result.boton_id);
    } else {
      console.log(`OK: ${t.name} -> ${result.route}`);
    }
  } catch (err) {
    failed++;
    console.error(`ERROR: ${t.name}:`, err.message);
  }
}

// Wiring / payload checks from workflow JSON
const conns = workflow.connections;
const wiringOk =
  conns['Route Switch'].main[11][0].node === 'Set awaiting cancelar datos' &&
  conns['Set awaiting cancelar datos'].main[0][0].node === 'Build cancelar collect' &&
  conns['Build cancelar collect'].main[0][0].node === 'Send cancelar collect' &&
  conns['Route Switch'].main[15][0].node === 'Set awaiting reprogramar datos';

if (!wiringOk) {
  failed++;
  console.error('FAIL: cancelar/reprogramar collect wiring');
} else {
  console.log('OK: cancelar/reprogramar collect wiring (MySQL -> Build -> Send)');
}

const buildCancel = workflow.nodes.find((n) => n.name === 'Build cancelar collect');
if (buildCancel.parameters.jsCode.includes('sql_state')) {
  failed++;
  console.error('FAIL: Build cancelar collect still emits sql_state');
} else {
  console.log('OK: Build cancelar collect has no sql_state');
}

if (
  !workflow.nodes
    .find((n) => n.name === 'Set awaiting cancelar datos')
    .parameters.query.startsWith('UPDATE conversation_state')
) {
  failed++;
  console.error('FAIL: Set awaiting cancelar datos missing inline SQL');
} else {
  console.log('OK: Set awaiting cancelar datos uses inline SQL');
}

const insertCancel = workflow.nodes.find((n) => n.name === 'Insert cancelar solicitud ext');
const sendPrivate = workflow.nodes.find((n) => n.name === 'Send cancelar private note');
const insertReprog = workflow.nodes.find((n) => n.name === 'Insert reprogramar solicitud');
const restoreCancel = workflow.nodes.find((n) => n.name === 'Restore cancelar finalize item');
const restoreReprog = workflow.nodes.find((n) => n.name === 'Restore reprogramar finalize item');
const workingUrl =
  "={{ 'https://chat.' + ($env.CHATWOOT_HOST || $env.DOMAIN) + '/api/v1/accounts/' + String($json.account_id) + '/conversations/' + String($json.conversation_id) + '/messages' }}";
const finalizeRefsOk =
  insertCancel.parameters.query.includes("$('Prep cancelar finalize')") &&
  insertReprog.parameters.query.includes("$('Prep reprogramar finalize')") &&
  sendPrivate.parameters.url === workingUrl &&
  sendPrivate.parameters.jsonBody === '={{ $json.cw_private }}' &&
  restoreCancel &&
  restoreReprog &&
  conns['Insert cancelar solicitud ext'].main[0][0].node === 'Restore cancelar finalize item' &&
  conns['Restore cancelar finalize item'].main[0][0].node === 'Send cancelar private note';

if (!finalizeRefsOk) {
  failed++;
  console.error('FAIL: finalize private note must Restore Prep then use $json URL');
} else {
  console.log('OK: private note uses $json URL (n8n 2.34) after Restore from Prep');
}

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
