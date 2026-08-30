#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const workflowPath = path.join(__dirname, '..', 'n8n', 'workflows', '01-entry-router.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const conns = workflow.connections;

let failed = 0;
function check(name, ok) {
  if (!ok) {
    failed++;
    console.error('FAIL:', name);
  } else {
    console.log('OK:', name);
  }
}

const wh = workflow.nodes.find((n) => n.name === 'Chatwoot Webhook');
check(
  'Webhook responds onReceived (before Wait)',
  wh && wh.parameters.options && wh.parameters.options.responseMode === 'onReceived'
);

const accNames = [
  'Acc Gate',
  'Acc Switch',
  'Acc Push',
  'Acc Wait 7s',
  'Acc Is latest',
  'Acc Merge texto',
  'Acc Continue',
];
for (const name of accNames) {
  check(`node ${name}`, workflow.nodes.some((n) => n.name === name));
}

check(
  'Merge Context → Acc Gate',
  conns['Merge Context'].main[0][0].node === 'Acc Gate'
);
check(
  'Acc Switch true → Acc Push',
  conns['Acc Switch'].main[0][0].node === 'Acc Push'
);
check(
  'Acc Switch false → Build AI',
  conns['Acc Switch'].main[1][0].node === 'Build AI intent prompt'
);
check(
  'Acc Continue → Build AI',
  conns['Acc Continue'].main[0][0].node === 'Build AI intent prompt'
);

const buildAi = workflow.nodes.find((n) => n.name === 'Build AI intent prompt');
check(
  'Build AI uses $input (not Merge Context)',
  buildAi.parameters.jsCode.includes('$input.first()') &&
    !buildAi.parameters.jsCode.includes("$('Merge Context')")
);

const parseAi = workflow.nodes.find((n) => n.name === 'Parse AI intent');
check(
  'Parse AI bases on Build AI intent prompt',
  parseAi.parameters.jsCode.includes("$('Build AI intent prompt')")
);

const booking = workflow.nodes.find((n) => n.name === 'Call Booking 03');
const bookingTexto = booking.parameters.workflowInputs.value.texto || '';
check(
  'Call Booking 03 texto from Decide Route',
  bookingTexto.includes("$('Decide Route')")
);

const gate = workflow.nodes.find((n) => n.name === 'Acc Gate');
check('Acc Gate embeds decideAccumulate', gate.parameters.jsCode.includes('decideAccumulate'));
check('Acc Gate embeds ACC_STATES', gate.parameters.jsCode.includes('awaiting_pedido_datos'));

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
