#!/usr/bin/env python3
"""Build lean Phase 1 booking workflow (03-booking-flow.json)."""

from __future__ import annotations

import json
import re
import sys
import uuid
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSER_PATH = ROOT / "scripts" / "parse-pedido-datos.js"
OLD_WORKFLOW_PATH = ROOT / "n8n" / "workflows" / "03-booking-flow.json"
OUT_PATH = OLD_WORKFLOW_PATH

CW_URL = (
    "={{ 'https://chat.' + ($env.CHATWOOT_HOST || $env.DOMAIN) "
    "+ '/api/v1/accounts/' + String($json.account_id) "
    "+ '/conversations/' + String($json.conversation_id) + '/messages' }}"
)

REUSE_NODE_NAMES = (
    "Handle obra social",
    "Ask obra list",
    "Handle medico",
    "Ask medico list",
)

COMMON_HELPERS = r"""
function navItems(){
  return [
    { title: 'Repetir pregunta', value: 'repetir_pregunta' },
    { title: 'Cancelar turno', value: 'cancelar_turno_pedido' }
  ];
}
function cwSelect(content, items, m){
  items = items || [];
  let body = content;
  let buttons = items;
  if (items.length > 3) {
    const navIds = new Set(['repetir_pregunta', 'cancelar_turno_pedido']);
    const choices = items.filter(i => !navIds.has(i.value));
    const nav = items.filter(i => navIds.has(i.value));
    if (choices.length) {
      body += '\n\nEscribí una opción:\n' + choices.map(c => '• ' + c.title).join('\n');
    }
    buttons = (nav.length ? nav : items.slice(0, 3)).slice(0, 3);
  }
  return {
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    cw_body: {
      content: body,
      message_type: 'outgoing',
      private: false,
      content_type: 'input_select',
      content_attributes: { items: buttons.slice(0, 3) }
    }
  };
}
function parseCtx(raw){
  if (raw == null) return {};
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch(e){ return {}; }
}
function fold(s) {
  return String(s || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}
function compact(s) {
  return fold(s).replace(/[\/]+/g, ' ').replace(/\s+/g, ' ').trim();
}
function isParticular(s) {
  const f = compact(String(s || '').replace(/^[•\-\*]\s*/, ''));
  if (!f) return false;
  if (f === 'obra_particular') return true;
  const exact = new Set([
    'particular', 'sin obra', 'sin obras', 'sin obra social', 'sin obras sociales',
    'particular sin obra', 'particular sin obra social', 'sin obra particular',
    'no tengo obra', 'no tengo obra social', 'como particular', 'soy particular',
    'voy particular', 'pago particular', 'paciente particular', 'consulta particular',
    'obra particular', 'sin cobertura', 'no tengo cobertura', 'ninguna obra',
    'ninguna obra social', 'no tengo', 'particular por favor'
  ]);
  if (exact.has(f)) return true;
  if (/\b(soy|como|voy|pago|paciente|consulta|obra)\s+particular\b/.test(f)) return true;
  if (/\bparticular\s+(sin|no|pago|por|por favor)\b/.test(f)) return true;
  if (/^sin obras?( sociales?)?$/.test(f)) return true;
  if (/\bno (tengo|tiene|cuento con)\s+obras?( sociales?)?\b/.test(f)) return true;
  return false;
}
function consultaPriceLine(datos) {
  if (!isParticular(datos.obra_social)) return '';
  const medico = String(datos.medico || '');
  const fm = fold(medico);
  if (datos.medico_cualquiera || !datos.doctor_id || fm.includes('medico de cabecera') || !medico || medico === '-') return '';
  const price = fm === 'adrian artigas' ? '70 mil pesos' : '40 mil pesos';
  return 'Precio de consulta: ' + price;
}
function esc(s) {
  return String(s ?? '').replace(/\\/g, '\\\\').replace(/'/g, "''");
}
""".strip()


def new_id() -> str:
    return str(uuid.uuid4())


def load_parser_embed() -> str:
    text = PARSER_PATH.read_text(encoding="utf-8")
    text = re.sub(r"^['\"]use strict['\"];\s*", "", text)
    text = re.sub(r"/\*\*[\s\S]*?\*/\s*", "", text, count=1)
    text = re.sub(r"\nmodule\.exports\s*=\s*\{[\s\S]*\}\s*;?\s*$", "\n", text)
    return text.strip()


def node_by_name(old: dict, name: str) -> dict:
    for n in old["nodes"]:
        if n.get("name") == name:
            return n
    raise KeyError(f"Node not found in old workflow: {name}")


class WorkflowBuilder:
    def __init__(self, old: dict, mysql_cred: dict, http_cred: dict) -> None:
        self.old = old
        self.mysql_cred = mysql_cred
        self.http_cred = http_cred
        self.nodes: list[dict] = []
        self.connections: dict = {}
        self.parser = load_parser_embed()
        self._y = 0

    def y(self, step: int = 240) -> int:
        self._y += step
        return self._y

    def add(self, node: dict) -> str:
        self.nodes.append(node)
        return node["name"]

    def wire(self, src: str, dst: str, output: int = 0, input_index: int = 0) -> None:
        self.connections.setdefault(src, {"main": []})
        mains = self.connections[src]["main"]
        while len(mains) <= output:
            mains.append([])
        mains[output].append({"node": dst, "type": "main", "index": input_index})

    def code(self, name: str, js: str, x: int, y: int, node_id: str | None = None) -> str:
        body = js if js.startswith("\n") else "\n" + js
        return self.add(
            {
                "parameters": {"jsCode": body + "\n"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [x, y],
                "id": node_id or new_id(),
                "name": name,
            }
        )

    def mysql(
        self,
        name: str,
        query: str,
        x: int,
        y: int,
        always: bool = True,
        node_id: str | None = None,
    ) -> str:
        return self.add(
            {
                "parameters": {"operation": "executeQuery", "query": query, "options": {}},
                "type": "n8n-nodes-base.mySql",
                "typeVersion": 2.5,
                "position": [x, y],
                "id": node_id or new_id(),
                "name": name,
                "alwaysOutputData": always,
                "credentials": {"mySql": deepcopy(self.mysql_cred)},
            }
        )

    def http(self, name: str, x: int, y: int, node_id: str | None = None) -> str:
        return self.add(
            {
                "parameters": {
                    "method": "POST",
                    "url": CW_URL,
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ $json.cw_body }}",
                    "options": {},
                },
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [x, y],
                "id": node_id or new_id(),
                "name": name,
                "credentials": {"httpHeaderAuth": deepcopy(self.http_cred)},
            }
        )

    def switch(self, name: str, rules: list[tuple[str, str, str]], x: int, y: int) -> str:
        values = []
        for rule_id, field, value in rules:
            values.append(
                {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "strict",
                            "version": 2,
                        },
                        "conditions": [
                            {
                                "id": rule_id,
                                "leftValue": f"={{{{ $json.{field} }}}}",
                                "rightValue": value,
                                "operator": {
                                    "type": "string",
                                    "operation": "equals",
                                    "name": "filter.operator.equals",
                                },
                            }
                        ],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": value,
                }
            )
        return self.add(
            {
                "parameters": {
                    "rules": {"values": values},
                    "options": {"fallbackOutput": "extra"},
                },
                "type": "n8n-nodes-base.switch",
                "typeVersion": 3.2,
                "position": [x, y],
                "id": new_id(),
                "name": name,
            }
        )

    def if_node(self, name: str, expression: str, x: int, y: int) -> str:
        return self.add(
            {
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "strict",
                            "version": 2,
                        },
                        "conditions": [
                            {
                                "id": new_id(),
                                "leftValue": expression,
                                "rightValue": True,
                                "operator": {"type": "boolean", "operation": "true"},
                            }
                        ],
                        "combinator": "and",
                    },
                    "options": {},
                },
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [x, y],
                "id": new_id(),
                "name": name,
            }
        )

    def reuse_code(
        self, old_node: dict, x: int, y: int, name: str | None = None, node_id: str | None = None
    ) -> str:
        return self.code(
            name or old_node["name"],
            old_node["parameters"]["jsCode"],
            x,
            y,
            node_id=node_id or old_node.get("id"),
        )

    def build(self) -> dict:
        old = self.old
        trigger = node_by_name(old, "When Executed by Another Workflow")

        x0, y0 = 26656, 37776
        self.add(deepcopy(trigger))

        prepare_js = r"""
function parseCtx(raw){
  if (raw == null) return {};
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch(e){ return {}; }
}
function fold(s) {
  return String(s || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

const j = $input.first().json;
const estado = j.estado || 'idle';
const boton = String(j.boton_id || '').trim();
let texto = String(j.texto || '').trim();
texto = texto.replace(/\n?__cw_in_reply_to__:\S+/g, '').trim();
const lines = texto.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
const last = lines.length ? lines[lines.length - 1] : texto;
const isNavLine = (l) => /^(repetir|repetir pregunta)$/i.test(fold(l));
const isRepetir = boton === 'repetir_pregunta' || isNavLine(last) || lines.some(isNavLine);
const ctx = parseCtx(j.datos_json);

let step = estado;
if (/^(idle|menu_shown)$/.test(estado)) {
  if (/\b\d{7,10}\b/.test(texto) && fold(texto).length > 12) step = 'awaiting_pedido_datos';
  else step = 'Empezar';
}
if (estado === 'post_solicitud' && boton === 'corregir_datos') step = 'post_solicitud';

return [{
  json: {
    telefono: j.telefono,
    texto,
    boton_id: boton,
    estado,
    datos_json: ctx,
    conversation_id: j.conversation_id,
    account_id: j.account_id,
    is_repetir: isRepetir,
    step,
    correction_count: Number(ctx.correction_count || 0),
    solicitud_id: ctx.solicitud_id || null,
  }
}];
"""
        prep = node_by_name(old, "Prepare Input")
        self.code("Prepare Input", prepare_js, x0 + 224, y0, node_id=prep["id"])

        sync = node_by_name(old, "Sync step")
        sync_query = (
            "UPDATE conversation_state\nSET state = '{{ $json.step }}'\n"
            "WHERE phone = '{{ $json.telefono }}'\n"
            "  AND '{{ $json.step }}' IN (\n"
            "    'awaiting_pedido_datos','awaiting_correccion_datos','awaiting_obra_social',\n"
            "    'awaiting_obra_social_otra','awaiting_medico','post_solicitud'\n"
            "  );"
        )
        self.mysql("Sync step", sync_query, x0 + 336, y0, node_id=sync["id"])

        after = node_by_name(old, "After sync")
        self.code(
            "After sync",
            "return [$('Prepare Input').first()];",
            x0 + 400,
            y0,
            node_id=after["id"],
        )

        state_rules = [
            ("sw-Empezar", "step", "Empezar"),
            ("sw-pedido", "step", "awaiting_pedido_datos"),
            ("sw-correccion", "step", "awaiting_correccion_datos"),
            ("sw-obra", "step", "awaiting_obra_social"),
            ("sw-obra-otra", "step", "awaiting_obra_social_otra"),
            ("sw-medico", "step", "awaiting_medico"),
            ("sw-post", "step", "post_solicitud"),
        ]
        sw = node_by_name(old, "State Switch")
        self.switch("State Switch", state_rules, x0 + 560, y0)
        self.nodes[-1]["id"] = sw["id"]

        # --- Empezar: pedido de datos ---
        x1 = x0 + 800
        y = y0 - 800
        self.mysql(
            "Start awaiting_pedido_datos",
            "UPDATE conversation_state SET state = 'awaiting_pedido_datos', "
            "context = COALESCE(context, JSON_OBJECT()) "
            "WHERE phone = '{{ $('Prepare Input').item.json.telefono }}';",
            x1,
            y,
        )
        self.mysql(
            "Load doctors for pedido",
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name;",
            x1 + 224,
            y,
        )
        pedido_js = COMMON_HELPERS + r"""

const m = $('Prepare Input').first().json;
const docs = $input.all().map(i => i.json).filter(d => d && d.name);
const medLines = docs.length
  ? docs.map(d => '• ' + d.name).join('\n')
  : '• (sin médicos activos)';
const body = [
  'Para solicitar el turno, enviá en un solo mensaje:',
  '1. Nombre completo',
  '2. DNI',
  '3. Obra social (o Particular)',
  '4. Médico de preferencia',
  '',
  'Ejemplo: Juan Pérez 30111222 OSDE Dr. Adrian Artigas',
  '',
  'Médicos:',
  medLines,
  '• Mi médico de cabecera',
  '',
  'La secretaria confirmará día y hora.'
].join('\n');
return [cwSelect(body, navItems(), m)];
"""
        self.code("Build Pedido de datos", pedido_js, x1 + 448, y)
        self.http("Send Pedido de datos", x1 + 672, y)

        # --- Parse path (pedido + correccion) ---
        y_parse = y0 - 400
        self.mysql(
            "Load obras for parse",
            "SELECT obras_sociales FROM clinic_settings WHERE id = 1 LIMIT 1;",
            x1,
            y_parse,
        )
        self.mysql(
            "Load doctors for parse",
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name;",
            x1 + 224,
            y_parse,
        )
        parse_js = COMMON_HELPERS + "\n" + self.parser + r"""

function missingLabels(missing) {
  const map = {
    nombre: 'nombre completo',
    dni: 'DNI',
    obra_social: 'obra social',
    medico: 'médico',
  };
  return (missing || []).map((k) => map[k] || k);
}

const m = $('Prepare Input').first().json;
const ctx = parseCtx(m.datos_json);
let obras = $('Load obras for parse').first().json.obras_sociales;
if (typeof obras === 'string') { try { obras = JSON.parse(obras); } catch(e) { obras = []; } }
if (!Array.isArray(obras)) obras = [];
const doctors = $input.all().map(i => i.json).filter(d => d && d.id && d.name);
const parsed = parsePedidoDatos(m.texto, { doctors, obras });
const merged = {
  ...m,
  ...parsed,
  nombre: parsed.nombre || ctx.nombre || '',
  dni: parsed.dni || ctx.dni || '',
  obra_social: parsed.obra_social || ctx.obra_social || '',
  medico: parsed.medico || ctx.medico || '',
  doctor_id: parsed.doctor_id != null ? parsed.doctor_id : (ctx.doctor_id ?? null),
  medico_cualquiera: parsed.medico_cualquiera || !!ctx.medico_cualquiera,
  telefono_contacto: m.telefono,
  solicitud_id: ctx.solicitud_id || null,
  correction_count: Number(ctx.correction_count || 0),
  is_correction: m.step === 'awaiting_correccion_datos' || !!ctx.solicitud_id,
};
return [{ json: merged }];
"""
        self.code("Parse blob", parse_js, x1 + 448, y_parse)
        self.switch(
            "Parse action",
            [
                ("pa-complete", "parse_action", "complete"),
                ("pa-obra", "parse_action", "need_obra"),
                ("pa-med", "parse_action", "need_medico"),
                ("pa-inc", "parse_action", "incomplete"),
                ("pa-dni", "parse_action", "invalid_dni"),
            ],
            x1 + 672,
            y_parse,
        )

        save_partial_obra_js = COMMON_HELPERS + r"""
const j = $input.first().json;
const phone = esc(j.telefono);
const sql = `UPDATE conversation_state SET
  context = JSON_SET(
    COALESCE(context, JSON_OBJECT()),
    '$.nombre', '${esc(j.nombre)}',
    '$.dni', '${esc(j.dni)}',
    '$.obra_social', '${esc(j.obra_social || '')}',
    '$.medico', '${esc(j.medico || '')}',
    '$.doctor_id', ${j.doctor_id ? Number(j.doctor_id) : 'null'},
    '$.medico_cualquiera', ${j.medico_cualquiera ? 'true' : 'false'},
    '$.telefono_contacto', '${esc(j.telefono)}',
    '$.solicitud_id', ${j.solicitud_id ? Number(j.solicitud_id) : 'null'},
    '$.correction_count', ${Number(j.correction_count || 0)}
  ),
  state = 'awaiting_obra_social'
WHERE phone = '${phone}';`;
return [{ json: { ...j, sql_partial: sql } }];
"""
        save_partial_med_js = COMMON_HELPERS + r"""
const j = $input.first().json;
const phone = esc(j.telefono);
const sql = `UPDATE conversation_state SET
  context = JSON_SET(
    COALESCE(context, JSON_OBJECT()),
    '$.nombre', '${esc(j.nombre)}',
    '$.dni', '${esc(j.dni)}',
    '$.obra_social', '${esc(j.obra_social || '')}',
    '$.medico', '${esc(j.medico || '')}',
    '$.doctor_id', ${j.doctor_id ? Number(j.doctor_id) : 'null'},
    '$.medico_cualquiera', ${j.medico_cualquiera ? 'true' : 'false'},
    '$.telefono_contacto', '${esc(j.telefono)}',
    '$.solicitud_id', ${j.solicitud_id ? Number(j.solicitud_id) : 'null'},
    '$.correction_count', ${Number(j.correction_count || 0)}
  ),
  state = 'awaiting_medico'
WHERE phone = '${phone}';`;
return [{ json: { ...j, sql_partial: sql } }];
"""
        self.code("Prep save partial obra", save_partial_obra_js, x1 + 896, y_parse - 160)
        self.mysql("Save partial obra", "{{ $json.sql_partial }}", x1 + 1120, y_parse - 160)
        self.code("Prep save partial medico", save_partial_med_js, x1 + 896, y_parse + 160)
        self.mysql("Save partial medico", "{{ $json.sql_partial }}", x1 + 1120, y_parse + 160)

        need_medico_js = COMMON_HELPERS + r"""
const m = $('Prep save partial').first().json;
const body = 'Falta indicar el médico.\n\nApretá el botón de abajo para ver la lista y elegir.';
return [{
  json: {
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    cw_body: {
      content: body,
      message_type: 'outgoing',
      private: false,
      content_type: 'text'
    }
  }
}];
"""
        self.code("Build need medico msg", need_medico_js, x1 + 896, y_parse + 160)
        self.http("Send need medico msg", x1 + 1120, y_parse + 160)

        incomplete_js = COMMON_HELPERS + r"""
const j = $input.first().json;
let msg;
if (j.parse_action === 'invalid_dni') {
  msg = 'No pudimos leer el DNI. Enviá nombre completo y DNI (7 a 10 dígitos) en un solo mensaje.';
} else {
  const labels = (j.missing || []).map(k => ({
    nombre: 'nombre completo', dni: 'DNI', obra_social: 'obra social', medico: 'médico'
  }[k] || k));
  msg = labels.length
    ? 'Falta: ' + labels.join(' y ') + '. Enviá todos los datos en un solo mensaje.'
    : 'Faltan datos. Enviá nombre, DNI, obra social y médico en un solo mensaje.';
}
const m = $('Prepare Input').first().json;
return [{
  json: {
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    cw_body: { content: msg, message_type: 'outgoing', private: false, content_type: 'text' }
  }
}];
"""
        self.code("Build incomplete reply", incomplete_js, x1 + 896, y_parse + 400)
        self.http("Send incomplete reply", x1 + 1120, y_parse + 400)

        save_complete_js = COMMON_HELPERS + r"""
const j = $input.first().json;
const phone = esc(j.telefono);
const sql = `UPDATE conversation_state SET
  context = JSON_SET(
    COALESCE(context, JSON_OBJECT()),
    '$.nombre', '${esc(j.nombre)}',
    '$.dni', '${esc(j.dni)}',
    '$.obra_social', '${esc(j.obra_social)}',
    '$.medico', '${esc(j.medico)}',
    '$.doctor_id', ${j.doctor_id ? Number(j.doctor_id) : 'null'},
    '$.medico_cualquiera', ${j.medico_cualquiera ? 'true' : 'false'},
    '$.telefono_contacto', '${esc(j.telefono)}',
    '$.solicitud_id', ${j.solicitud_id ? Number(j.solicitud_id) : 'null'},
    '$.correction_count', ${Number(j.correction_count || 0)}
  )
WHERE phone = '${phone}';`;
return [{ json: { ...j, sql_ctx: sql } }];
"""
        self.code("Prep save complete ctx", save_complete_js, x1 + 896, y_parse - 400)
        self.mysql("Save complete context", "{{ $json.sql_ctx }}", x1 + 1120, y_parse - 400)

        # --- Finalize (recepcion + insert/update) ---
        y_fin = y0 + 400
        load_ctx = node_by_name(old, "Load ctx final")
        self.mysql(
            "Load ctx final",
            "SELECT context FROM conversation_state WHERE phone = '{{ $('Prepare Input').item.json.telefono }}' LIMIT 1;",
            x1,
            y_fin,
            node_id=load_ctx["id"],
        )

        recepcion_js = COMMON_HELPERS + r"""
function isOutsideClinicHours(now) {
  const h = now.getHours();
  const inMorning = h >= 8 && h < 12;
  const inAfternoon = h >= 16 && h < 20;
  return !(inMorning || inAfternoon);
}

const m = $('Prepare Input').first().json;
const datos = parseCtx($input.first().json.context);
datos.telefono_contacto = datos.telefono_contacto || m.telefono;
const horarioFijo = 'A confirmar por secretaría';
const phone = esc(m.telefono);
const priceLine = consultaPriceLine(datos);
const isUpdate = !!(datos.solicitud_id);
let sql;
if (isUpdate) {
  sql = `UPDATE turno_solicitudes SET
    nombre='${esc(datos.nombre)}', dni='${esc(datos.dni)}', obra_social='${esc(datos.obra_social)}',
    telefono_contacto='${esc(datos.telefono_contacto)}', medico='${esc(datos.medico)}',
    horario_preferido='${esc(horarioFijo)}'
    WHERE id=${Number(datos.solicitud_id)};`;
} else {
  sql = `INSERT INTO turno_solicitudes (phone, nombre, dni, obra_social, telefono_contacto, medico, horario_preferido, status, conversation_id)
VALUES ('${phone}', '${esc(datos.nombre)}', '${esc(datos.dni)}', '${esc(datos.obra_social)}', '${esc(datos.telefono_contacto)}', '${esc(datos.medico)}', '${esc(horarioFijo)}', 'pending', '${esc(m.conversation_id)}');`;
}
const ficha = `🗒️ ${isUpdate ? 'Corrección' : 'Nueva'} solicitud de turno
Nombre: ${datos.nombre || '-'}
DNI: ${datos.dni || '-'}
Obra social: ${datos.obra_social || '-'}
Teléfono: ${datos.telefono_contacto || '-'}
Médico: ${datos.medico || '-'}
Día/hora: ${horarioFijo}${priceLine ? '\n' + priceLine : ''}`;
let patientBody = [
  'Recibimos tu solicitud de turno.',
  '',
  `👤 ${datos.nombre || '-'}`,
  `🪪 ${datos.dni || '-'}`,
  `🏥 ${datos.obra_social || '-'}`,
  `🩺 ${datos.medico || '-'}`,
];
if (priceLine) patientBody.push(priceLine);
patientBody.push('', 'Espere a que la secretaria le indique el día y hora.');
try {
  const now = ($now && typeof $now.toDate === 'function')
    ? $now.setZone('America/Argentina/Buenos_Aires').toJSDate()
    : new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Argentina/Buenos_Aires' }));
  if (isOutsideClinicHours(now)) {
    patientBody.push('', 'Su solicitud fue enviada fuera del horario de atención de la clínica (8 a 12 hs y 16 a 20 hs). Una secretaria la confirmará dentro de ese horario.');
  }
} catch (e) {}
const recepcion = cwSelect(patientBody.join('\n'), [{ title: 'Corregir datos', value: 'corregir_datos' }], m);
const newCorrection = isUpdate ? Number(datos.correction_count || 0) + 1 : Number(datos.correction_count || 0);
const sqlState = isUpdate
  ? `UPDATE conversation_state SET state='post_solicitud', context=JSON_SET(COALESCE(context, JSON_OBJECT()), '$.correction_count', ${newCorrection}) WHERE phone='${phone}';`
  : `UPDATE conversation_state SET state='post_solicitud', context=JSON_SET(COALESCE(context, JSON_OBJECT()), '$.solicitud_id', LAST_INSERT_ID(), '$.correction_count', ${newCorrection}) WHERE phone='${phone}';`;
return [{
  json: {
    telefono: m.telefono,
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    sql_solicitud: sql,
    sql_state: sqlState,
    is_update: isUpdate,
    cw_private: { content: ficha, message_type: 'outgoing', private: true },
    recepcion,
  }
}];
"""
        self.code("Build recepcion + sql", recepcion_js, x1 + 224, y_fin)
        self.mysql("Run solicitud sql", "{{ $json.sql_solicitud }}", x1 + 448, y_fin)
        self.code(
            "Prep private note",
            "const j = $('Build recepcion + sql').first().json;\n"
            "return [{ json: { conversation_id: j.conversation_id, account_id: j.account_id, cw_body: j.cw_private } }];",
            x1 + 672,
            y_fin,
        )
        self.http("Send private note", x1 + 896, y_fin)
        self.code(
            "Prep recepcion",
            "const j = $('Build recepcion + sql').first().json;\n"
            "return [{ json: j.recepcion }];",
            x1 + 1120,
            y_fin,
        )
        self.http("Send recepcion", x1 + 1344, y_fin)
        self.mysql("Set post_solicitud", "{{ $('Build recepcion + sql').first().json.sql_state }}", x1 + 1568, y_fin)

        # --- Obra social flow (reuse handlers) ---
        y_obra = y0
        self.reuse_code(node_by_name(old, "Handle obra social"), x1, y_obra)
        obra_sw = node_by_name(old, "Obra action")
        obra_rules = [
            ("oa-r", "obra_action", "repetir"),
            ("oa-o", "obra_action", "otra"),
            ("oa-s", "obra_action", "save"),
        ]
        self.switch("Obra action", obra_rules, x1 + 224, y_obra)
        self.nodes[-1]["id"] = obra_sw["id"]

        self.mysql(
            "Reload obras repetir",
            "SELECT obras_sociales FROM clinic_settings WHERE id = 1 LIMIT 1;",
            x1 + 448,
            y_obra - 160,
        )
        self.reuse_code(node_by_name(old, "Ask obra list"), x1 + 672, y_obra - 160, name="Re-ask obra list")
        self.http("Send obra repetir", x1 + 896, y_obra - 160)

        self.mysql(
            "Set awaiting_obra_otra",
            "UPDATE conversation_state SET state = 'awaiting_obra_social_otra' "
            "WHERE phone = '{{ $json.telefono }}';",
            x1 + 448,
            y_obra,
        )
        ask_obra_otra_js = COMMON_HELPERS + r"""
const m = $('Prepare Input').first().json;
return [cwSelect('Escribí el nombre de tu obra social.', navItems(), m)];
"""
        self.code("Ask obra otra", ask_obra_otra_js, x1 + 672, y_obra)
        self.http("Send obra otra", x1 + 896, y_obra)

        self.if_node(
            "Obra otra: repetir?",
            "={{ $json.is_repetir === true || $json.is_repetir === 'true' }}",
            x1,
            y_obra + 240,
        )
        self.code("Re-ask obra otra", ask_obra_otra_js, x1 + 224, y_obra + 160)
        self.http("Send re-ask obra otra", x1 + 448, y_obra + 160)

        prep_obra_otra = node_by_name(old, "Prep save obra otra")
        self.code(
            "Prep save obra otra",
            prep_obra_otra["parameters"]["jsCode"],
            x1 + 224,
            y_obra + 320,
            node_id=prep_obra_otra["id"],
        )
        self.mysql(
            "Save obra otra",
            "UPDATE conversation_state\nSET context = JSON_SET(COALESCE(context, JSON_OBJECT()), "
            "'$.obra_social', '{{ $json.obra_value.replace(/'/g, \"''\") }}', "
            "'$.telefono_contacto', '{{ $json.telefono }}')\n"
            "WHERE phone = '{{ $json.telefono }}';",
            x1 + 448,
            y_obra + 320,
        )

        self.mysql(
            "Save obra listed",
            "UPDATE conversation_state\nSET context = JSON_SET(COALESCE(context, JSON_OBJECT()), "
            "'$.obra_social', '{{ $json.obra_value.replace(/'/g, \"''\") }}', "
            "'$.telefono_contacto', '{{ $json.telefono }}')\n"
            "WHERE phone = '{{ $json.telefono }}';",
            x1 + 448,
            y_obra + 480,
        )

        route_after_obra_js = r"""
function parseCtx(raw){
  if (raw == null) return {};
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch(e){ return {}; }
}
const m = $('Prepare Input').first().json;
const row = $input.first().json;
const ctx = parseCtx(row.context);
const hasMed = !!(ctx.medico && String(ctx.medico).trim());
return [{ json: { ...m, route_after_obra: hasMed ? 'finalize' : 'medico' } }];
"""
        self.code("Route after obra", route_after_obra_js, x1 + 672, y_obra + 400)
        self.switch(
            "After obra route",
            [
                ("aor-fin", "route_after_obra", "finalize"),
                ("aor-med", "route_after_obra", "medico"),
            ],
            x1 + 896,
            y_obra + 400,
        )

        self.mysql(
            "Load ctx after obra",
            "SELECT context FROM conversation_state WHERE phone = '{{ $('Prepare Input').item.json.telefono }}' LIMIT 1;",
            x1 + 672,
            y_obra + 560,
        )

        # need_obra -> obra list
        self.mysql(
            "Load obras list",
            "SELECT obras_sociales FROM clinic_settings WHERE id = 1 LIMIT 1;",
            x1 + 1344,
            y_parse - 160,
        )
        self.reuse_code(node_by_name(old, "Ask obra list"), x1 + 1568, y_parse - 160, name="Ask obra list")
        self.http("Send obra list", x1 + 1792, y_parse - 160)

        # --- Medico flow ---
        y_med = y0 + 800
        load_doc_match = node_by_name(old, "Load doctors match")
        self.mysql(
            "Load doctors match",
            "SELECT COALESCE(JSON_ARRAYAGG(JSON_OBJECT('id', id, 'name', name)), JSON_ARRAY()) AS doctors_json FROM doctors WHERE active = 1;",
            x1,
            y_med,
            node_id=load_doc_match["id"],
        )
        self.reuse_code(node_by_name(old, "Handle medico"), x1 + 224, y_med)
        med_sw = node_by_name(old, "Medico action")
        med_rules = [
            ("ma-r", "med_action", "repetir"),
            ("ma-l", "med_action", "list"),
            ("ma-s", "med_action", "save"),
        ]
        self.switch("Medico action", med_rules, x1 + 448, y_med)
        self.nodes[-1]["id"] = med_sw["id"]

        self.mysql(
            "Reload doctors repetir",
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name;",
            x1 + 672,
            y_med - 160,
        )
        self.reuse_code(node_by_name(old, "Ask medico list"), x1 + 896, y_med - 160, name="Re-ask medico")
        self.http("Send medico repetir", x1 + 1120, y_med - 160)

        build_list = node_by_name(old, "Build medico list reply")
        self.code(
            "Build medico list reply",
            build_list["parameters"]["jsCode"],
            x1 + 672,
            y_med + 80,
            node_id=build_list["id"],
        )
        self.http("Send medico list reply", x1 + 896, y_med + 80)
        self.mysql(
            "Reload doctors for list",
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name;",
            x1 + 1120,
            y_med + 80,
        )
        self.reuse_code(node_by_name(old, "Ask medico list"), x1 + 1344, y_med + 80, name="Re-ask medico after list")

        prep_med_js = r"""
const m = $input.first().json;
const cualquiera = !!m.cualquiera;
const id = m.doctor_id ? Number(m.doctor_id) : 0;
const phone = String(m.telefono).replace(/'/g, "''");
let sql;
if (cualquiera) {
  sql = `UPDATE conversation_state SET context = JSON_SET(COALESCE(context, JSON_OBJECT()), '$.medico', 'Mi médico de cabecera', '$.medico_cualquiera', true, '$.doctor_id', null, '$.telefono_contacto', '${phone}') WHERE phone = '${phone}';`;
} else if (id) {
  sql = `UPDATE conversation_state SET context = JSON_SET(COALESCE(context, JSON_OBJECT()), '$.medico', (SELECT name FROM doctors WHERE id = ${id}), '$.medico_cualquiera', false, '$.doctor_id', ${id}, '$.telefono_contacto', '${phone}') WHERE phone = '${phone}';`;
} else {
  sql = `UPDATE conversation_state SET state = 'awaiting_medico' WHERE phone = '${phone}';`;
}
return [{ json: { ...m, sql_update: sql } }];
"""
        prep_med = node_by_name(old, "Prep save medico")
        self.code("Prep save medico", prep_med_js, x1 + 672, y_med + 240, node_id=prep_med["id"])
        save_med = node_by_name(old, "Save medico state")
        self.mysql("Save medico state", "{{ $json.sql_update }}", x1 + 896, y_med + 240, node_id=save_med["id"])

        self.mysql(
            "Load doctors list",
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name;",
            x1 + 1344,
            y_med + 400,
        )
        self.reuse_code(node_by_name(old, "Ask medico list"), x1 + 1568, y_med + 400, name="Ask medico list")
        self.http("Send medico list", x1 + 1792, y_med + 400)

        # --- post_solicitud / corregir ---
        y_post = y0 + 1200
        post_js = r"""
function parseCtx(raw){
  if (raw == null) return {};
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch(e){ return {}; }
}
const m = $input.first().json;
const ctx = parseCtx(m.datos_json);
const boton = String(m.boton_id || '').trim();
if (boton === 'corregir_datos') {
  const count = Number(ctx.correction_count || m.correction_count || 0);
  return [{ json: { ...m, post_action: count >= 1 ? 'handoff' : 'corregir', correction_count: count } }];
}
return [{ json: { ...m, post_action: 'noop' } }];
"""
        self.code("Handle post solicitud", post_js, x1, y_post)
        self.switch(
            "Post solicitud action",
            [
                ("ps-handoff", "post_action", "handoff"),
                ("ps-corregir", "post_action", "corregir"),
            ],
            x1 + 224,
            y_post,
        )

        handoff_js = r"""
const m = $('Handle post solicitud').first().json;
const teamId = Number($env.CHATWOOT_TEAM_ID);
const teamName = String($env.CHATWOOT_TEAM_NAME || 'Secretaría').trim();
const teamMention = teamId && !Number.isNaN(teamId)
  ? `[@${teamName}](mention://team/${teamId}/${encodeURIComponent(teamName)})`
  : '';
const header = teamMention ? `${teamMention} Derivación a Secretaría` : 'Derivación a Secretaría';
const patientMsg = 'Ya usaste la corrección disponible. Te derivamos con Secretaría para ayudarte.';
const phone = String(m.telefono).replace(/'/g, "''");
const sqlState = `UPDATE conversation_state SET state='idle', context=JSON_SET(COALESCE(context, JSON_OBJECT()), '$.handoff_reason', 'correccion_turno', '$.needs_handoff', true) WHERE phone='${phone}';`;
return [{
  json: {
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    sql_handoff: sqlState,
    cw_private: {
      content: header + '\nMotivo: segunda corrección de solicitud de turno',
      message_type: 'outgoing',
      private: true,
      content_type: 'text'
    },
    cw_body: {
      content: patientMsg,
      message_type: 'outgoing',
      private: false,
      content_type: 'text'
    }
  }
}];
"""
        self.code("Build handoff derivacion", handoff_js, x1 + 448, y_post - 80)
        self.http("Send handoff patient", x1 + 672, y_post - 80)
        self.code(
            "Prep handoff note",
            "const j = $('Build handoff derivacion').first().json;\n"
            "return [{ json: { conversation_id: j.conversation_id, account_id: j.account_id, cw_body: j.cw_private } }];",
            x1 + 896,
            y_post - 80,
        )
        self.http("Send handoff note", x1 + 1120, y_post - 80)
        self.mysql(
            "Save handoff state",
            "{{ $('Build handoff derivacion').first().json.sql_handoff }}",
            x1 + 1344,
            y_post - 80,
        )

        self.mysql(
            "Start awaiting_correccion",
            "UPDATE conversation_state SET state = 'awaiting_correccion_datos' "
            "WHERE phone = '{{ $('Prepare Input').item.json.telefono }}';",
            x1 + 448,
            y_post + 80,
        )

        # --- Connections ---
        self.wire("When Executed by Another Workflow", "Prepare Input")
        self.wire("Prepare Input", "Sync step")
        self.wire("Sync step", "After sync")
        self.wire("After sync", "State Switch")

        # State Switch outputs
        self.wire("State Switch", "Start awaiting_pedido_datos", 0)
        self.wire("State Switch", "Load obras for parse", 1)
        self.wire("State Switch", "Load obras for parse", 2)
        self.wire("State Switch", "Handle obra social", 3)
        self.wire("State Switch", "Obra otra: repetir?", 4)
        self.wire("State Switch", "Load doctors match", 5)
        self.wire("State Switch", "Handle post solicitud", 6)

        # Empezar
        self.wire("Start awaiting_pedido_datos", "Load doctors for pedido")
        self.wire("Load doctors for pedido", "Build Pedido de datos")
        self.wire("Build Pedido de datos", "Send Pedido de datos")

        # Parse
        self.wire("Load obras for parse", "Load doctors for parse")
        self.wire("Load doctors for parse", "Parse blob")
        self.wire("Parse blob", "Parse action")
        self.wire("Parse action", "Prep save complete ctx", 0)
        self.wire("Parse action", "Prep save partial obra", 1)
        self.wire("Parse action", "Prep save partial medico", 2)
        self.wire("Parse action", "Build incomplete reply", 3)
        self.wire("Parse action", "Build incomplete reply", 4)
        self.wire("Prep save complete ctx", "Save complete context")
        self.wire("Save complete context", "Load ctx final")
        self.wire("Prep save partial obra", "Save partial obra")
        self.wire("Save partial obra", "Load obras list")
        self.wire("Load obras list", "Ask obra list")
        self.wire("Ask obra list", "Send obra list")
        self.wire("Prep save partial medico", "Save partial medico")
        self.wire("Save partial medico", "Build need medico msg")
        self.wire("Build need medico msg", "Send need medico msg")
        self.wire("Send need medico msg", "Load doctors list")
        self.wire("Build incomplete reply", "Send incomplete reply")

        # Finalize chain
        self.wire("Load ctx final", "Build recepcion + sql")
        self.wire("Build recepcion + sql", "Run solicitud sql")
        self.wire("Run solicitud sql", "Prep private note")
        self.wire("Prep private note", "Send private note")
        self.wire("Send private note", "Prep recepcion")
        self.wire("Prep recepcion", "Send recepcion")
        self.wire("Send recepcion", "Set post_solicitud")

        # Obra
        self.wire("Handle obra social", "Obra action")
        self.wire("Obra action", "Reload obras repetir", 0)
        self.wire("Obra action", "Set awaiting_obra_otra", 1)
        self.wire("Obra action", "Save obra listed", 2)
        self.wire("Reload obras repetir", "Re-ask obra list")
        self.wire("Re-ask obra list", "Send obra repetir")
        self.wire("Set awaiting_obra_otra", "Ask obra otra")
        self.wire("Ask obra otra", "Send obra otra")
        self.wire("Obra otra: repetir?", "Re-ask obra otra", 0)
        self.wire("Obra otra: repetir?", "Prep save obra otra", 1)
        self.wire("Re-ask obra otra", "Send re-ask obra otra")
        self.wire("Prep save obra otra", "Save obra otra")
        self.wire("Save obra listed", "Load ctx after obra")
        self.wire("Save obra otra", "Load ctx after obra")
        self.wire("Load ctx after obra", "Route after obra")
        self.wire("Route after obra", "After obra route")
        self.wire("After obra route", "Load ctx final", 0)
        self.wire("After obra route", "Load doctors list", 1)
        self.wire("Load doctors list", "Ask medico list")
        self.wire("Ask medico list", "Send medico list")

        # Medico
        self.wire("Load doctors match", "Handle medico")
        self.wire("Handle medico", "Medico action")
        self.wire("Medico action", "Reload doctors repetir", 0)
        self.wire("Medico action", "Build medico list reply", 1)
        self.wire("Medico action", "Prep save medico", 2)
        self.wire("Reload doctors repetir", "Re-ask medico")
        self.wire("Re-ask medico", "Send medico repetir")
        self.wire("Build medico list reply", "Send medico list reply")
        self.wire("Send medico list reply", "Reload doctors for list")
        self.wire("Reload doctors for list", "Re-ask medico after list")
        self.wire("Re-ask medico after list", "Send medico repetir")
        self.wire("Prep save medico", "Save medico state")
        self.wire("Save medico state", "Load ctx final")

        # Post solicitud
        self.wire("Handle post solicitud", "Post solicitud action")
        self.wire("Post solicitud action", "Build handoff derivacion", 0)
        self.wire("Post solicitud action", "Start awaiting_correccion", 1)
        self.wire("Build handoff derivacion", "Send handoff patient")
        self.wire("Send handoff patient", "Prep handoff note")
        self.wire("Prep handoff note", "Send handoff note")
        self.wire("Send handoff note", "Save handoff state")
        self.wire("Start awaiting_correccion", "Load doctors for pedido")

        return {
            "name": old["name"],
            "nodes": self.nodes,
            "connections": self.connections,
            "active": old.get("active", True),
            "settings": old.get("settings", {"executionOrder": "v1"}),
            "versionId": old.get("versionId"),
            "meta": old.get("meta", {}),
            "nodeGroups": old.get("nodeGroups", []),
            "id": old.get("id"),
            "tags": old.get("tags", []),
        }


def extract_credentials(old: dict) -> tuple[dict, dict]:
    mysql_cred = None
    http_cred = None
    for node in old["nodes"]:
        creds = node.get("credentials") or {}
        if "mySql" in creds and mysql_cred is None:
            mysql_cred = creds["mySql"]
        if "httpHeaderAuth" in creds and http_cred is None:
            http_cred = creds["httpHeaderAuth"]
    if not mysql_cred or not http_cred:
        raise RuntimeError("Could not extract MySQL/HTTP credentials from old workflow")
    return mysql_cred, http_cred


def summarize(workflow: dict) -> str:
    nodes = workflow["nodes"]
    conns = workflow["connections"]
    lines = [
        f"Workflow: {workflow['name']} ({len(nodes)} nodes, id={workflow.get('id')})",
        "",
        "Nodes:",
    ]
    for n in nodes:
        lines.append(f"  - {n['name']} ({n['type'].split('.')[-1]})")
    lines.extend(["", "Connection structure (main outputs):"])
    for src, data in sorted(conns.items()):
        mains = data.get("main") or []
        for idx, targets in enumerate(mains):
            if not targets:
                continue
            dsts = ", ".join(t["node"] for t in targets)
            key = src if len(mains) == 1 else f"{src}[{idx}]"
            lines.append(f"  {key} -> {dsts}")
    return "\n".join(lines)


def main() -> int:
    if not PARSER_PATH.is_file():
        print(f"ERROR: parser not found: {PARSER_PATH}", file=sys.stderr)
        return 1
    if not OLD_WORKFLOW_PATH.is_file():
        print(f"ERROR: old workflow not found: {OLD_WORKFLOW_PATH}", file=sys.stderr)
        return 1

    old = json.loads(OLD_WORKFLOW_PATH.read_text(encoding="utf-8"))
    for name in REUSE_NODE_NAMES:
        node_by_name(old, name)

    mysql_cred, http_cred = extract_credentials(old)
    builder = WorkflowBuilder(old, mysql_cred, http_cred)
    workflow = builder.build()

    OUT_PATH.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(summarize(workflow))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
