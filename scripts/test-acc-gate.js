#!/usr/bin/env node
'use strict';

const { decideAccumulate, joinFragments } = require('./acc-gate');

let failed = 0;
function check(name, ok) {
  if (!ok) {
    failed++;
    console.error('FAIL:', name);
  } else {
    console.log('OK:', name);
  }
}

check(
  'pedido free-text accumulates',
  decideAccumulate({
    estado: 'awaiting_pedido_datos',
    texto: 'Juan',
    telefono: '543811112222',
    tipo: 'text',
    boton_id: '',
  }).accumulate === true
);

check(
  'button tap bypasses',
  decideAccumulate({
    estado: 'awaiting_pedido_datos',
    texto: 'Sacar un turno',
    telefono: '543811112222',
    tipo: 'interactive',
    boton_id: 'quiero_turno',
  }).accumulate === false
);

check(
  'boton_id alone bypasses',
  decideAccumulate({
    estado: 'idle',
    texto: 'Sacar un turno',
    telefono: '543811112222',
    tipo: 'text',
    boton_id: 'quiero_turno',
  }).accumulate === false
);

check(
  'media bypasses',
  decideAccumulate({
    estado: 'idle',
    texto: '',
    telefono: '543811112222',
    tipo: 'media',
    boton_id: '',
  }).accumulate === false
);

check(
  'obra list state does not accumulate',
  decideAccumulate({
    estado: 'awaiting_obra_social',
    texto: 'OSDE',
    telefono: '543811112222',
    tipo: 'text',
    boton_id: '',
  }).accumulate === false
);

check(
  'idle greeting accumulates (ADR scope)',
  decideAccumulate({
    estado: 'idle',
    texto: 'hola',
    telefono: '543811112222',
    tipo: 'text',
    boton_id: '',
  }).accumulate === true
);

check(
  'join space-separates',
  joinFragments(['Juan', 'Pérez', '30111222 OSDE Artigas']) ===
    'Juan Pérez 30111222 OSDE Artigas'
);

check(
  'keys use phone digits',
  decideAccumulate({
    estado: 'idle',
    texto: 'hola',
    telefono: '+54 381 111-2222',
    tipo: 'text',
  }).acc_list_key === 'acc:frags:543811112222'
);

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
