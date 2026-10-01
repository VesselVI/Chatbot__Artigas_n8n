#!/usr/bin/env python3
"""Patch 01-entry-router.json for ADR-0007 pregunta_horarios path.

- Get State / Merge Context: pass disponibilidad_enabled
- Decide Route: doctor-hours when toggle off → pregunta_horarios
- Prep estudio: solicitud → pregunta
- Route Switch + new branch (copy + insert + note, no assign)
- Sync pending: clear pregunta_horarios_ack on other routes
"""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_PATH = ROOT / "n8n" / "workflows" / "01-entry-router.json"

FIXED_COPY = (
    "Le comunicaremos con una secretaria para darle a saber "
    "los horarios de los doctores"
)

DECIDE_INSERT_FN = r'''
function isDoctorHoursIntent(t) {
  const f = fold(t);
  if (!f) return false;
  // Clinic opening hours stay on route=horarios (isHorarios), not here.
  if (/^horarios( de (la )?clinica)?$/.test(f)) return false;
  if (/\b(turno|cita|sacar|agendar|reservar|cancelar|reprogramar)\b/.test(f)) return false;
  if (/\b(atiende|atienden|atencion)\b/.test(f) && /\b(dr|dra|doctor|doctora|medico|medica)\b/.test(f)) return true;
  if (/\bhorarios?\b/.test(f) && /\b(dr|dra|doctor|doctora|medico|medica|doctores|medicos)\b/.test(f)) return true;
  if (/\ba que hora\b/.test(f) && /\b(dr|dra|doctor|doctora|medico|medica|atiende|atienden)\b/.test(f)) return true;
  if (/\bcuando (atiende|atienden|trabaja)\b/.test(f)) return true;
  if (/\bdisponibilidad\b/.test(f) && /\b(dr|dra|doctor|medico|semana|hoy|manana)\b/.test(f)) return true;
  return false;
}
'''

DECIDE_ROUTE_BLOCK = r'''
const disponibilidadOn = [1, '1', true, 'true', 'on'].includes(item.disponibilidad_enabled)
  || Number(item.disponibilidad_enabled) === 1;
const doctorHours = isDoctorHoursIntent(last) || isDoctorHoursIntent(handoffProbe) || isDoctorHoursIntent(allFold);
'''


def nid() -> str:
    return str(uuid.uuid4())


def main() -> None:
    wf = json.loads(WF_PATH.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]

    # --- Get State ---
    nodes["Get State"]["parameters"]["query"] = (
        "SELECT\n"
        "  cs.phone,\n"
        "  COALESCE(cs.state, 'idle') AS state,\n"
        "  cs.context,\n"
        "  COALESCE(\n"
        "    (SELECT disponibilidad_enabled FROM clinic_settings WHERE id = 1 LIMIT 1),\n"
        "    0\n"
        "  ) AS disponibilidad_enabled\n"
        "FROM (SELECT '{{ $('Normalize Message').item.json.telefono }}' AS phone) p\n"
        "LEFT JOIN conversation_state cs ON cs.phone = p.phone\n"
        "LIMIT 1;"
    )

    # --- Merge Context: pass flag ---
    mc = nodes["Merge Context"]["parameters"]["jsCode"]
    if "disponibilidad_enabled" not in mc:
        mc = mc.replace(
            "media_kind: n.media_kind || '',\n    last_line: last,\n  }\n}];",
            "media_kind: n.media_kind || '',\n"
            "    last_line: last,\n"
            "    disponibilidad_enabled: Number(row.disponibilidad_enabled || 0) ? 1 : 0,\n"
            "  }\n}];",
        )
        nodes["Merge Context"]["parameters"]["jsCode"] = mc

    # --- Decide Route ---
    dr = nodes["Decide Route"]["parameters"]["jsCode"]
    if "isDoctorHoursIntent" not in dr:
        dr = dr.replace(
            "function wantsHandoffIntent(t) {\n  return isSecretariaIntent(t) || isDoctorTalkIntent(t) || isEstudioIntent(t);\n}",
            "function wantsHandoffIntent(t) {\n  return isSecretariaIntent(t) || isDoctorTalkIntent(t) || isEstudioIntent(t);\n}\n"
            + DECIDE_INSERT_FN,
        )
        # After isHorarios / before dni-on-menu booking: insert doctor hours gate
        # Place after isHorarios block assignment area: after `} else if (isHorarios) {\n  route = 'horarios';\n`
        needle = "} else if (isHorarios) {\n  route = 'horarios';\n\n} else if (onMenu && /\\b\\d{7,10}\\b/.test(texto)"
        # Also need disponibilidadOn/doctorHours vars before routing - insert before `let route = 'welcome';`
        if "const doctorHours" not in dr:
            dr = dr.replace(
                "let route = 'welcome';",
                DECIDE_ROUTE_BLOCK + "\nlet route = 'welcome';",
            )
        replacement = (
            "} else if (isHorarios) {\n"
            "  route = 'horarios';\n\n"
            "} else if (doctorHours && !disponibilidadOn && onMenu) {\n"
            "  route = 'pregunta_horarios';\n\n"
            "} else if (onMenu && /\\b\\d{7,10}\\b/.test(texto)"
        )
        if needle not in dr:
            raise SystemExit("Decide Route needle for isHorarios not found")
        dr = dr.replace(needle, replacement)
        # handoff_reason for pregunta_horarios
        if "route === 'pregunta_horarios'" not in dr:
            dr = dr.replace(
                "} else if (route === 'estudio_handoff') {",
                "} else if (route === 'pregunta_horarios') {\n"
                "  handoff_reason = 'pregunta_horarios';\n"
                "  handoff_quote = String(handoffProbe || texto || '')\n"
                "    .replace(/\\n?__cw_in_reply_to__:\\S+/g, '')\n"
                "    .trim();\n\n"
                "} else if (route === 'estudio_handoff') {",
            )
        nodes["Decide Route"]["parameters"]["jsCode"] = dr

    # --- Prep estudio: solicitud → pregunta ---
    prep = nodes["Prep estudio solicitud"]["parameters"]["jsCode"]
    prep = prep.replace("const tipo = isEstudio ? 'estudio' : 'solicitud';", "const tipo = isEstudio ? 'estudio' : 'pregunta';")
    prep = prep.replace(
        "const fallback = isEstudio ? 'Consulta estudio/precio' : 'Solicitud de secretaria';",
        "const fallback = isEstudio ? 'Consulta estudio/precio' : 'Pregunta / secretaria';",
    )
    nodes["Prep estudio solicitud"]["parameters"]["jsCode"] = prep

    # --- Sync pending prompt ---
    sync_q = nodes["Sync pending prompt"]["parameters"]["query"]
    if "pregunta_horarios" not in sync_q:
        nodes["Sync pending prompt"]["parameters"]["query"] = """UPDATE conversation_state
SET context = CASE
  WHEN '{{ $json.route }}' IN ('media_warn', 'estudio_handoff') THEN
    JSON_SET(
      COALESCE(context, JSON_OBJECT()),
      '$.pending_prompt', '{{ $json.route }}',
      '$.handoff_reason', '{{ $json.handoff_reason }}',
      '$.handoff_quote', '{{ $json.handoff_quote_sql }}'
    )
  WHEN '{{ $json.route }}' = 'pregunta_horarios' THEN
    COALESCE(context, JSON_OBJECT())
  ELSE
    JSON_REMOVE(
      COALESCE(context, JSON_OBJECT()),
      '$.pending_prompt',
      '$.handoff_reason',
      '$.handoff_quote',
      '$.pregunta_horarios_ack'
    )
END
WHERE phone = '{{ $json.telefono }}';"""

    # --- Route Switch: add output ---
    sw = nodes["Route Switch"]
    rules = sw["parameters"]["rules"]["values"]
    if not any(r.get("outputKey") == "pregunta_horarios" for r in rules):
        # Clone faq rule shape
        template = deepcopy(rules[1])  # faq
        template["outputKey"] = "pregunta_horarios"
        # rewrite condition rightValue
        conds = template.get("conditions", {}).get("conditions", [])
        for c in conds:
            if c.get("rightValue") == "faq":
                c["rightValue"] = "pregunta_horarios"
            if "id" in c:
                c["id"] = nid()
        if "conditions" in template and "combinator" in template["conditions"]:
            pass
        # new ids on rule
        if "id" in template.get("conditions", {}):
            template["conditions"]["id"] = nid()
        rules.append(template)

    # --- New branch nodes ---
    mysql_cred = nodes["Insert estudio solicitud"]["credentials"]
    http_cred = nodes["Send estudio handoff"]["credentials"]
    y = 4300
    x0 = 2064

    build_code = f"""const m = $('Decide Route').first().json;
return [{{
  json: {{
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    telefono: m.telefono,
    cw_body: {{
      content: {FIXED_COPY!r},
      message_type: 'outgoing',
      private: false,
      content_type: 'text'
    }}
  }}
}}];"""

    prep_code = r"""function esc(s) {
  return String(s ?? '').replace(/\\/g, '\\\\').replace(/'/g, "''").slice(0, 250);
}
const m = $('Decide Route').first().json;
const merged = $('Merge Context').first().json;
const ctx = (merged.context && typeof merged.context === 'object') ? merged.context : {};
const already = !!ctx.pregunta_horarios_ack;
const quote = String(m.handoff_quote || m.last_line || m.texto || '')
  .replace(/\n?__cw_in_reply_to__:\S+/g, '')
  .trim() || 'Consulta horarios de doctores';
let sql = 'SELECT 1';
if (!already) {
  sql = `INSERT INTO turno_solicitudes (phone, nombre, dni, obra_social, telefono_contacto, medico, horario_preferido, status, conversation_id, tipo)
VALUES ('${esc(m.telefono)}', '${esc(ctx.nombre)}', '${esc(ctx.dni)}', '${esc(ctx.obra_social)}', '${esc(ctx.telefono_contacto || merged.telefono)}', '', '${esc(quote)}', 'pending', '${esc(m.conversation_id)}', 'pregunta');`;
}
return [{ json: { sql_insert: sql, skip_insert: already, telefono: m.telefono, conversation_id: m.conversation_id, account_id: m.account_id, quote } }];"""

    note_code = r"""const m = $('Decide Route').first().json;
const prep = $('Prep pregunta horarios').first().json;
const quote = String(prep.quote || m.handoff_quote || m.last_line || '').trim();
const skip = !!prep.skip_insert;
const content = skip
  ? ('Pregunta horarios (repetida, sin nueva fila) — ' + quote)
  : ('Pregunta horarios de doctores — ' + quote + '\n(Bot sigue activo; sin asignación de equipo.)');
return [{
  json: {
    conversation_id: m.conversation_id,
    account_id: m.account_id,
    telefono: m.telefono,
    cw_body: {
      content,
      message_type: 'outgoing',
      private: true,
      content_type: 'text'
    }
  }
}];"""

    new_nodes = [
        {
            "parameters": {"jsCode": build_code},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [x0, y],
            "id": nid(),
            "name": "Build pregunta horarios",
        },
        {
            "parameters": deepcopy(nodes["Send estudio handoff"]["parameters"]),
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x0 + 224, y],
            "id": nid(),
            "name": "Send pregunta horarios",
            "credentials": http_cred,
            "notesInFlow": True,
            "notes": "Credential 'Chatwoot API' = Header Auth (name: api_access_token).",
        },
        {
            "parameters": {"jsCode": prep_code},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [x0 + 448, y],
            "id": nid(),
            "name": "Prep pregunta horarios",
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": "={{ $json.sql_insert }}",
                "options": {},
            },
            "type": "n8n-nodes-base.mySql",
            "typeVersion": 2.4,
            "position": [x0 + 672, y],
            "id": nid(),
            "name": "Insert pregunta horarios",
            "credentials": mysql_cred,
        },
        {
            "parameters": {"jsCode": note_code},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [x0 + 896, y],
            "id": nid(),
            "name": "Prep pregunta horarios note",
        },
        {
            "parameters": deepcopy(nodes["Send estudio handoff"]["parameters"]),
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x0 + 1120, y],
            "id": nid(),
            "name": "Send pregunta horarios note",
            "credentials": http_cred,
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "UPDATE conversation_state\n"
                    "SET context = JSON_SET(COALESCE(context, JSON_OBJECT()), '$.pregunta_horarios_ack', true)\n"
                    "WHERE phone = '{{ $('Decide Route').item.json.telefono }}';"
                ),
                "options": {},
            },
            "type": "n8n-nodes-base.mySql",
            "typeVersion": 2.4,
            "position": [x0 + 1344, y],
            "id": nid(),
            "name": "Set pregunta horarios ack",
            "credentials": mysql_cred,
        },
    ]

    existing_names = {n["name"] for n in wf["nodes"]}
    for nn in new_nodes:
        if nn["name"] not in existing_names:
            wf["nodes"].append(nn)

    # Wire Route Switch output index = len(rules)-1 after append, but fallback was last
    # Current outputs 0..17 + fallback 18. New rule appends as output 18, fallback becomes 19.
    # Rebuild Route Switch main connections carefully.
    rs_main = conns["Route Switch"]["main"]
    # If pregunta_horarios not already wired:
    targets = []
    for outs in rs_main:
        targets.append(outs[0]["node"] if outs else None)
    if "Build pregunta horarios" not in targets:
        # Insert before fallback (last)
        fallback = rs_main[-1]
        rs_main.insert(-1, [{"node": "Build pregunta horarios", "type": "main", "index": 0}])
        # ensure fallback still last
        if rs_main[-1] is not fallback:
            rs_main[-1] = fallback

    chain = [
        ("Build pregunta horarios", "Send pregunta horarios"),
        ("Send pregunta horarios", "Prep pregunta horarios"),
        ("Prep pregunta horarios", "Insert pregunta horarios"),
        ("Insert pregunta horarios", "Prep pregunta horarios note"),
        ("Prep pregunta horarios note", "Send pregunta horarios note"),
        ("Send pregunta horarios note", "Set pregunta horarios ack"),
    ]
    for src, dst in chain:
        conns[src] = {"main": [[{"node": dst, "type": "main", "index": 0}]]}

    WF_PATH.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Patched", WF_PATH)


if __name__ == "__main__":
    main()
