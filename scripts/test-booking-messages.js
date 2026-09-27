#!/usr/bin/env node
/**
 * Unit tests for lean booking workflow (03-booking-flow.json).
 * Run: node scripts/test-booking-messages.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const workflowPath = path.join(__dirname, '..', 'n8n', 'workflows', '03-booking-flow.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const conns = workflow.connections;

const buildRecepcion = workflow.nodes.find((n) => n.name === 'Build recepcion + sql');
const prepareInput = workflow.nodes.find((n) => n.name === 'Prepare Input');
const parseBlob = workflow.nodes.find((n) => n.name === 'Parse blob');
const buildPedido = workflow.nodes.find((n) => n.name === 'Build Pedido de datos');
const handlePost = workflow.nodes.find((n) => n.name === 'Handle post solicitud');
const handleMedico = workflow.nodes.find((n) => n.name === 'Handle medico');

if (!buildRecepcion || !prepareInput || !parseBlob || !buildPedido) {
  console.error('Required lean booking nodes missing');
  process.exit(1);
}

function isOutsideClinicHours(now) {
  const h = now.getHours();
  const inMorning = h >= 9 && h < 12;
  const inAfternoon = h >= 16 && h < 20;
  return !(inMorning || inAfternoon);
}

function atHour(h, m = 0) {
  return new Date(2026, 7, 20, h, m, 0);
}

let failed = 0;
function check(name, ok) {
  if (!ok) {
    failed++;
    console.error('FAIL:', name);
  } else {
    console.log('OK:', name);
  }
}

const br = buildRecepcion.parameters.jsCode;
check('Build recepcion has isOutsideClinicHours', br.includes('isOutsideClinicHours'));
check('Recepcion mentions Recibimos', br.includes('Recibimos tu solicitud'));
check('Recepcion has Corregir datos button', br.includes('corregir_datos'));
check('Recepcion UPDATE only when is_correction + solicitud_id', /isUpdate = !!\(datos\.solicitud_id && datos\.is_correction\)/.test(br));
check('Recepcion supports UPDATE branch', br.includes('UPDATE turno_solicitudes'));
check('Private ficha still has solicitud', br.includes('solicitud de turno'));
check('horario fixed A confirmar', br.includes('A confirmar por secretaría'));
check(
  'After recepcion state returns to idle (not stuck post_solicitud)',
  /state\s*=\s*'idle'/.test(br) &&
    !/state\s*=\s*'post_solicitud'/.test(br)
);
check(
  'Insert persists solicitud_id via LAST_INSERT_ID in same Run query',
  br.includes('LAST_INSERT_ID()') && br.includes('SELECT LAST_INSERT_ID() AS insertId')
);

const runSql = workflow.nodes.find((n) => n.name === 'Run solicitud sql');
check(
  'Run solicitud sql uses independently batching (same MySQL session)',
  !!(runSql && runSql.parameters.options && runSql.parameters.options.queryBatching === 'independently')
);

const bindSid = workflow.nodes.find((n) => n.name === 'Bind solicitud_id');
check('Bind solicitud_id node exists', !!bindSid);
check(
  'Bind solicitud_id scans all MySQL items for insertId',
  !!(bindSid && bindSid.parameters.jsCode.includes('$input.all()') && bindSid.parameters.jsCode.includes('insertId'))
);
check(
  'Run solicitud sql wires to Bind solicitud_id',
  conns['Run solicitud sql'] &&
    conns['Run solicitud sql'].main[0] &&
    conns['Run solicitud sql'].main[0][0].node === 'Bind solicitud_id'
);
check(
  'Set post_solicitud uses Bind solicitud_id sql_state',
  workflow.nodes
    .find((n) => n.name === 'Set post_solicitud')
    .parameters.query.includes('Bind solicitud_id')
);

// Feedback loop: n8n executeQuery INSERT shape drops OkPacket → {success:true}
function pickInsertId(row) {
  if (row == null) return 0;
  if (Array.isArray(row)) return pickInsertId(row[0]);
  const n = Number(row.insertId ?? row.insert_id ?? row.INSERT_ID ?? 0);
  if (n > 0) return n;
  return 0;
}
check('n8n {success:true} yields insertId 0 (OkPacket discarded)', pickInsertId({ success: true }) === 0);
check('SELECT LAST_INSERT_ID row yields insertId', pickInsertId({ insertId: 77 }) === 77);

const pi = prepareInput.parameters.jsCode;
check('Prepare Input uses awaiting_pedido_datos', pi.includes('awaiting_pedido_datos'));
check('Prepare skips pedido when DNI blob on menu', pi.includes('fold(texto).length > 12'));

const pb = parseBlob.parameters.jsCode;
check('Parse blob embeds parsePedidoDatos', pb.includes('function parsePedidoDatos'));
check('Parse blob returns parse_action', pb.includes('parse_action'));

const ped = buildPedido.parameters.jsCode;
check('Pedido asks single message', ped.includes('en un solo mensaje'));
check('Pedido lists medicos in footer', ped.includes('Médicos:'));

check(
  'Parse complete wires to finalize',
  conns['Parse action'] &&
    conns['Parse action'].main[0] &&
    conns['Parse action'].main[0][0].node === 'Prep save complete ctx'
);

check(
  'Empezar wires to pedido',
  conns['State Switch'].main[0][0].node === 'Start awaiting_pedido_datos'
);

check(
  'Post solicitud wires handoff branch',
  conns['Post solicitud action'] &&
    conns['Post solicitud action'].main.some((o) => o[0].node === 'Build handoff derivacion')
);

if (handlePost) {
  check('Handle post checks correction_count', handlePost.parameters.jsCode.includes('correction_count'));
}

if (handleMedico) {
  const runHandle = new Function('$input', '$', handleMedico.parameters.jsCode);
  const docs = [
    { id: 1, name: 'Adrian Artigas' },
    { id: 2, name: 'Paulina Artigas' },
  ];
  const $input = {
    all: () => docs.map((d) => ({ json: d })),
    first: () => ({ json: docs[0] }),
  };
  const $ = (name) => {
    if (name === 'Prepare Input')
      return {
        first: () => ({
          json: {
            telefono: '543811111111',
            conversation_id: 1,
            account_id: 2,
            boton_id: 'medico_1',
            texto: 'Adrian Artigas',
            is_repetir: false,
          },
        }),
      };
    throw new Error('unexpected $ ' + name);
  };
  const saveHit = runHandle($input, $)[0].json;
  check('medico button still saves', saveHit.med_action === 'save' && Number(saveHit.doctor_id) === 1);
}

check('07:59 outside', isOutsideClinicHours(atHour(7, 59)) === true);
check('08:00 outside', isOutsideClinicHours(atHour(8, 0)) === true);
check('08:59 outside', isOutsideClinicHours(atHour(8, 59)) === true);
check('09:00 open', isOutsideClinicHours(atHour(9, 0)) === false);

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
