#!/usr/bin/env node
'use strict';

const { parsePedidoDatos } = require('./parse-pedido-datos');

const doctors = [
  { id: 1, name: 'Adrian Artigas' },
  { id: 2, name: 'Paulina Artigas' },
  { id: 6, name: 'Esteban Artigas' },
];
const obras = ['OSDE', 'Swiss Medical', 'OSFATUN'];

let failed = 0;
function check(name, ok) {
  if (!ok) {
    failed++;
    console.error('FAIL:', name);
  } else {
    console.log('OK:', name);
  }
}

const full = parsePedidoDatos('Juan Pérez 30111222 OSDE Dr Adrian Artigas', { doctors, obras });
check('complete blob', full.parse_action === 'complete' && full.dni === '30111222');
check('obra OSDE', full.obra_social === 'OSDE');
check('medico Adrian', full.medico.includes('Adrian'));

const turno = parsePedidoDatos('quiero turno Maria Lopez 28999888 particular Artigas', { doctors, obras });
check('turno prefix stripped', turno.parse_action === 'complete');
check('particular', turno.obra_social === 'Particular / Sin Obra Social');

const cab = parsePedidoDatos('Ana Garcia 30111222 OSDE medico de cabecera', { doctors, obras });
check('cabecera', cab.parse_action === 'complete' && cab.medico === 'Mi médico de cabecera');

const needObra = parsePedidoDatos('Pedro Diaz 30111222 Artigas', { doctors, obras });
check('need obra', needObra.parse_action === 'need_obra' && needObra.medico.includes('Artigas'));

const needMed = parsePedidoDatos('Laura Paz 30111222 OSDE', { doctors, obras });
check('need medico', needMed.parse_action === 'need_medico');

const badDni = parsePedidoDatos('Juan 20202 OSDE Artigas', { doctors, obras });
check('invalid/incomplete short dni', badDni.parse_action === 'invalid_dni' || badDni.parse_action === 'incomplete');

const empty = parsePedidoDatos('hola', { doctors, obras });
check('greeting incomplete', empty.parse_action === 'incomplete');

// Live smoke failures (2026-08-29/30 WhatsApp transcript)
const kiero = parsePedidoDatos(
  'kiero turno  ignacio caram 4320202 PAMI Esteban Artigas',
  { doctors, obras: [...obras, 'PAMI'] }
);
check(
  'smoke4: typo kiero turno stripped from nombre',
  kiero.parse_action === 'complete' &&
    !/kiero|turno/i.test(kiero.nombre) &&
    /ignacio/i.test(kiero.nombre)
);

const garbageObra = parsePedidoDatos(
  'Juan ignacio 43030303 sajuafwf Adrian Artigas',
  { doctors, obras }
);
check(
  'smoke8: unknown obra triggers need_obra (not free-text accept)',
  garbageObra.parse_action === 'need_obra' &&
    garbageObra.medico.includes('Adrian') &&
    !garbageObra.obra_social
);

console.log(failed ? `\n${failed} test(s) failed` : '\nAll tests passed');
process.exit(failed ? 1 : 0);
