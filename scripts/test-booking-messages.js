#!/usr/bin/env node
/**
 * Unit tests for booking patient-ack helpers extracted from 03-booking-flow.json.
 * Run: node scripts/test-booking-messages.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const workflowPath = path.join(__dirname, '..', 'n8n', 'workflows', '03-booking-flow.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const buildInsert = workflow.nodes.find((n) => n.name === 'Build insert + notes');
const prepMedico = workflow.nodes.find((n) => n.name === 'Prep save medico');
const buildConfirm = workflow.nodes.find((n) => n.name === 'Build confirmation');
const conns = workflow.connections;

if (!buildInsert || !prepMedico || !buildConfirm) {
  console.error('Required booking nodes missing');
  process.exit(1);
}

function isOutsideClinicHours(now) {
  const h = now.getHours();
  const inMorning = h >= 8 && h < 12;
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

check('07:59 outside', isOutsideClinicHours(atHour(7, 59)) === true);
check('08:00 open', isOutsideClinicHours(atHour(8, 0)) === false);
check('11:59 open', isOutsideClinicHours(atHour(11, 59)) === false);
check('12:00 lunch outside', isOutsideClinicHours(atHour(12, 0)) === true);
check('15:59 lunch outside', isOutsideClinicHours(atHour(15, 59)) === true);
check('16:00 open', isOutsideClinicHours(atHour(16, 0)) === false);
check('19:59 open', isOutsideClinicHours(atHour(19, 59)) === false);
check('20:00 outside', isOutsideClinicHours(atHour(20, 0)) === true);

const bi = buildInsert.parameters.jsCode;
check('Build insert has isOutsideClinicHours', bi.includes('isOutsideClinicHours'));
check('Patient ack is short Turno solicitado', bi.includes('Turno solicitado.'));
check('Patient ack does not embed ficha', !bi.includes("ficha +"));
check('Private ficha still Nueva solicitud', bi.includes('Nueva solicitud de turno'));
check('horario fixed A confirmar', bi.includes('A confirmar por secretaría'));

const pm = prepMedico.parameters.jsCode;
check('Prep medico goes to awaiting_confirmacion', pm.includes("state = 'awaiting_confirmacion'"));
check('Prep medico does not set awaiting_dia_hora', !pm.includes("state = 'awaiting_dia_hora'"));

const bc = buildConfirm.parameters.jsCode;
check('Confirm summary has no calendar dia_hora line', !bc.includes('📅'));
check('Confirm asks for solicitud not turno slot', bc.includes('Confirmás la solicitud'));

check(
  'Save medico state wires to Load ctx confirm',
  conns['Save medico state'].main[0][0].node === 'Load ctx confirm'
);
check(
  'Stale awaiting_dia_hora routes to Load ctx confirm',
  conns['State Switch'].main[7][0].node === 'Load ctx confirm'
);

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
