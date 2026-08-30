'use strict';

/**
 * Parse a single patient blob (Pedido de datos) into booking fields.
 * Used by scripts/tests and embedded in n8n Code nodes (copy body of parsePedidoDatos).
 */

function fold(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function compact(s) {
  return fold(s).replace(/[\/]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function stripTurnoPrefix(texto) {
  return String(texto || '')
    .replace(/\n?__cw_in_reply_to__:\S+/g, '')
    .replace(/^(quiero|necesito|qiero|preciso)\s+(un\s+)?(turno|cita)\b[:\s]*/i, '')
    .replace(/^(sacar|pedir|solicitar)\s+(un\s+)?(turno|cita)\b[:\s]*/i, '')
    .trim();
}

function parseNameDni(t) {
  const raw = String(t || '').replace(/\n?__cw_in_reply_to__:\S+/g, '').trim();
  const stripped = stripTurnoPrefix(raw);
  const m = stripped.match(/^(.*?)\b(\d{7,10})\b([\s\S]*)$/);
  if (!m) return null;
  let nombre = m[1].replace(/[,:;|]+/g, ' ').replace(/\s+/g, ' ').trim();
  nombre = nombre.replace(/^(dni|nombre|soy|me llamo|mi nombre es)\s+/i, '').trim();
  if (!nombre) return null;
  return { nombre: nombre.slice(0, 120), dni: m[2], after: m[3].trim() };
}

function isParticular(s) {
  const f = compact(String(s || '').replace(/^[•\-\*]\s*/, ''));
  if (!f) return false;
  if (f === 'obra_particular') return true;
  const exact = new Set([
    'particular',
    'sin obra',
    'sin obras',
    'sin obra social',
    'sin obras sociales',
    'particular sin obra',
    'particular sin obra social',
    'sin obra particular',
    'no tengo obra',
    'no tengo obra social',
    'como particular',
    'soy particular',
    'voy particular',
    'pago particular',
    'paciente particular',
    'consulta particular',
    'obra particular',
    'sin cobertura',
    'no tengo cobertura',
    'ninguna obra',
    'ninguna obra social',
    'no tengo',
    'particular por favor',
  ]);
  if (exact.has(f)) return true;
  if (/\b(soy|como|voy|pago|paciente|consulta|obra)\s+particular\b/.test(f)) return true;
  if (/\bparticular\s+(sin|no|pago|por|por favor)\b/.test(f)) return true;
  if (/^sin obras?( sociales?)?$/.test(f)) return true;
  if (/\bno (tengo|tiene|cuento con)\s+obras?( sociales?)?\b/.test(f)) return true;
  return false;
}

function remainderAfterNameDni(texto, nombre, dni) {
  let t = stripTurnoPrefix(texto);
  const dniRe = new RegExp('\\b' + dni + '\\b');
  t = t.replace(dniRe, ' ');
  const parts = String(nombre || '').split(/\s+/).filter(Boolean);
  for (const p of parts) {
    t = t.replace(new RegExp('\\b' + p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'i'), ' ');
  }
  return t.replace(/[,:;|]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function matchObra(remainder, obras, doctors) {
  if (!remainder) return null;
  if (isParticular(remainder) || /\bparticular\b/i.test(remainder)) {
    return 'Particular / Sin Obra Social';
  }
  const fRem = compact(remainder);
  const sorted = [...(obras || [])].filter(Boolean).sort((a, b) => b.length - a.length);
  for (const o of sorted) {
    if (isParticular(o)) continue;
    const fo = compact(o);
    if (!fo) continue;
    if (fRem === fo || fRem.includes(fo)) return String(o);
  }
  const medOnly = matchMedico(remainder, doctors);
  if (medOnly && (fRem === fold(medOnly.medico) || fRem === fold(medOnly.medico).split(' ').pop())) {
    return null;
  }
  const tokens = remainder.split(/\s+/).filter(Boolean);
  if (tokens.length >= 1 && tokens.length <= 4 && !/\d/.test(remainder)) {
    return remainder.slice(0, 120);
  }
  return null;
}

function extractObraMedico(remainder, obras, doctors) {
  let rest = String(remainder || '').trim();
  let obra = null;
  if (isParticular(rest) || /\bparticular\b/i.test(rest)) {
    obra = 'Particular / Sin Obra Social';
    rest = rest.replace(/\bparticular\b/gi, ' ').replace(/\s+/g, ' ').trim();
  }
  if (!obra) {
    const sorted = [...(obras || [])].filter(Boolean).sort((a, b) => b.length - a.length);
    for (const o of sorted) {
      if (isParticular(o)) continue;
      const fo = compact(o);
      if (!fo) continue;
      if (compact(rest).includes(fo)) {
        obra = String(o);
        rest = rest.replace(new RegExp(o.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), ' ').replace(/\s+/g, ' ').trim();
        break;
      }
    }
  }
  let medHit = matchMedico(rest, doctors);
  if (!medHit && !obra) medHit = matchMedico(remainder, doctors);
  if (!obra && medHit) {
    const afterMed = remainder.replace(new RegExp(medHit.medico, 'i'), '').trim();
    obra = matchObra(afterMed, obras, doctors);
  }
  return { obra, medHit, rest };
}

function isCabecera(text) {
  const f = compact(text);
  return (
    f === 'medico cabecera' ||
    f === 'mi medico de cabecera' ||
    f === 'cabecera' ||
    f === 'medico_cabecera' ||
    /\b(medico|doctor)\s+de\s+cabecera\b/.test(f) ||
    /\bmi\s+(medico|doctor)\s+de\s+cabecera\b/.test(f)
  );
}

function matchMedico(remainder, doctors) {
  if (!remainder) return null;
  if (isCabecera(remainder)) {
    return { medico: 'Mi médico de cabecera', doctor_id: null, medico_cualquiera: true };
  }
  const docs = [...(doctors || [])].filter((d) => d && d.name).sort((a, b) => b.name.length - a.name.length);
  const fRem = fold(remainder);
  for (const d of docs) {
    const fn = fold(d.name);
    if (!fn) continue;
    if (fRem === fn || fRem.includes(fn) || fn.includes(fRem)) {
      return { medico: d.name, doctor_id: d.id, medico_cualquiera: false };
    }
  }
  for (const d of docs) {
    const fn = fold(d.name);
    const last = fn.split(/\s+/).pop();
    if (last && last.length > 3 && fRem.includes(last)) {
      return { medico: d.name, doctor_id: d.id, medico_cualquiera: false };
    }
  }
  return null;
}

/**
 * @param {string} texto
 * @param {{ doctors?: Array<{id:number,name:string}>, obras?: string[] }} opts
 */
function parsePedidoDatos(texto, opts = {}) {
  const doctors = opts.doctors || [];
  const obras = opts.obras || [];
  const raw = String(texto || '').trim();
  if (!raw) {
    return {
      parse_action: 'incomplete',
      missing: ['nombre', 'dni', 'obra_social', 'medico'],
      nombre: '',
      dni: '',
      obra_social: '',
      medico: '',
      doctor_id: null,
      medico_cualquiera: false,
    };
  }

  const nd = parseNameDni(raw);
  if (!nd) {
    const hasDigit = /\d{5,}/.test(stripTurnoPrefix(raw).replace(/[. -]/g, ''));
    return {
      parse_action: hasDigit ? 'invalid_dni' : 'incomplete',
      missing: ['nombre', 'dni', 'obra_social', 'medico'],
      nombre: '',
      dni: '',
      obra_social: '',
      medico: '',
      doctor_id: null,
      medico_cualquiera: false,
    };
  }

  const remainder = nd.after || remainderAfterNameDni(raw, nd.nombre, nd.dni);
  const extracted = extractObraMedico(remainder, obras, doctors);
  let obra = extracted.obra;
  let medHit = extracted.medHit;

  const missing = [];
  if (!obra) missing.push('obra_social');
  if (!medHit) missing.push('medico');

  const base = {
    nombre: nd.nombre,
    dni: nd.dni,
    obra_social: obra || '',
    medico: medHit ? medHit.medico : '',
    doctor_id: medHit ? medHit.doctor_id : null,
    medico_cualquiera: medHit ? !!medHit.medico_cualquiera : false,
    missing,
  };

  if (missing.length === 0) {
    return { ...base, parse_action: 'complete' };
  }
  if (missing.length === 1 && missing[0] === 'obra_social') {
    return { ...base, parse_action: 'need_obra' };
  }
  if (missing.length === 1 && missing[0] === 'medico') {
    return { ...base, parse_action: 'need_medico' };
  }
  return { ...base, parse_action: 'incomplete' };
}

function missingLabels(missing) {
  const map = {
    nombre: 'nombre completo',
    dni: 'DNI',
    obra_social: 'obra social',
    medico: 'médico',
  };
  return (missing || []).map((k) => map[k] || k);
}

module.exports = {
  fold,
  compact,
  parseNameDni,
  isParticular,
  parsePedidoDatos,
  missingLabels,
  stripTurnoPrefix,
};
