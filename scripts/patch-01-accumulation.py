#!/usr/bin/env python3
"""Patch 01-entry-router.json with Phase 2 Redis accumulation (ADR-0002)."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF_PATH = ROOT / "n8n" / "workflows" / "01-entry-router.json"
ACC_GATE_PATH = ROOT / "scripts" / "acc-gate.js"

REDIS_CRED = {"redis": {"id": "BotRedisPlaceholder", "name": "Bot Redis"}}

# Stable-ish ids so re-runs replace rather than duplicate by name
NODE_IDS = {
    "Acc Gate": "a1000001-acc0-4001-8001-000000000001",
    "Acc Switch": "a1000001-acc0-4001-8001-000000000002",
    "Acc Push": "a1000001-acc0-4001-8001-000000000003",
    "Acc After push": "a1000001-acc0-4001-8001-000000000004",
    "Acc Incr": "a1000001-acc0-4001-8001-000000000005",
    "Acc After incr": "a1000001-acc0-4001-8001-000000000006",
    "Acc Wait 7s": "a1000001-acc0-4001-8001-000000000007",
    "Acc Get version": "a1000001-acc0-4001-8001-000000000008",
    "Acc Is latest": "a1000001-acc0-4001-8001-000000000009",
    "Acc Get frags": "a1000001-acc0-4001-8001-00000000000a",
    "Acc Merge texto": "a1000001-acc0-4001-8001-00000000000b",
    "Acc Del frags": "a1000001-acc0-4001-8001-00000000000c",
    "Acc Del ver": "a1000001-acc0-4001-8001-00000000000d",
    "Acc Continue": "a1000001-acc0-4001-8001-00000000000e",
}


def uid(name: str) -> str:
    return NODE_IDS.get(name) or str(uuid.uuid4())


def load_gate_helpers() -> str:
    text = ACC_GATE_PATH.read_text(encoding="utf-8")
    # Drop module.exports for n8n embed
    text = text.split("module.exports")[0].rstrip()
    return text


GATE_JS = load_gate_helpers() + r"""

const m = $input.first().json;
const acc = decideAccumulate(m);
return [{ json: { ...m, ...acc } }];
"""

AFTER_PUSH_JS = r"""
return [$('Acc Gate').first()];
"""

AFTER_INCR_JS = r"""
const g = $('Acc Gate').first().json;
const incr = $input.first().json;
const verRaw = incr[g.acc_ver_key];
const ver = Number(verRaw != null ? verRaw : Object.values(incr)[0]);
return [{ json: { ...g, acc_version: ver } }];
"""

IS_LATEST_JS = r"""
const waited = $('Acc After incr').first().json;
const got = $input.first().json;
const now = got.acc_ver_now;
if (String(now) !== String(waited.acc_version)) {
  return [];
}
return [{ json: waited }];
"""

MERGE_JS = load_gate_helpers() + r"""

const base = $('Acc Is latest').first().json;
const frags = $input.first().json.acc_frags;
const merged = joinFragments(frags);
const lines = merged.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
const last = lines.length ? lines[lines.length - 1] : merged;
return [{
  json: {
    ...base,
    texto: merged,
    tipo: 'text',
    boton_id: '',
    last_line: last,
    accumulate: false,
  }
}];
"""

CONTINUE_JS = r"""
const m = $('Acc Merge texto').first().json;
const {
  acc_fragment, acc_list_key, acc_ver_key, acc_version, accumulate, acc_frags, acc_ver_now,
  ...rest
} = m;
return [{ json: rest }];
"""


def code_node(name: str, js: str, x: int, y: int) -> dict:
    return {
        "parameters": {"jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, y],
        "id": uid(name),
        "name": name,
    }


def if_accumulate(x: int, y: int) -> dict:
    return {
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
                        "id": "acc-true",
                        "leftValue": "={{ $json.accumulate }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                            "singleValue": True,
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [x, y],
        "id": uid("Acc Switch"),
        "name": "Acc Switch",
    }


def redis_push(x: int, y: int) -> dict:
    return {
        "parameters": {
            "operation": "push",
            "list": "={{ $json.acc_list_key }}",
            "messageData": "={{ $json.acc_fragment }}",
            "tail": True,
        },
        "type": "n8n-nodes-base.redis",
        "typeVersion": 1,
        "position": [x, y],
        "id": uid("Acc Push"),
        "name": "Acc Push",
        "credentials": deepcopy(REDIS_CRED),
    }


def redis_incr(x: int, y: int) -> dict:
    return {
        "parameters": {
            "operation": "incr",
            "key": "={{ $json.acc_ver_key }}",
            "expire": True,
            "ttl": 60,
        },
        "type": "n8n-nodes-base.redis",
        "typeVersion": 1,
        "position": [x, y],
        "id": uid("Acc Incr"),
        "name": "Acc Incr",
        "credentials": deepcopy(REDIS_CRED),
    }


def wait_7s(x: int, y: int) -> dict:
    return {
        "parameters": {
            "resume": "timeInterval",
            "amount": 7,
            "unit": "seconds",
        },
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [x, y],
        "id": uid("Acc Wait 7s"),
        "name": "Acc Wait 7s",
        "webhookId": "acc-wait-7s",
    }


def redis_get_version(x: int, y: int) -> dict:
    return {
        "parameters": {
            "operation": "get",
            "propertyName": "acc_ver_now",
            "key": "={{ $('Acc After incr').item.json.acc_ver_key }}",
            "keyType": "string",
            "options": {"dotNotation": False},
        },
        "type": "n8n-nodes-base.redis",
        "typeVersion": 1,
        "position": [x, y],
        "id": uid("Acc Get version"),
        "name": "Acc Get version",
        "credentials": deepcopy(REDIS_CRED),
    }


def redis_get_frags(x: int, y: int) -> dict:
    return {
        "parameters": {
            "operation": "get",
            "propertyName": "acc_frags",
            "key": "={{ $('Acc Is latest').item.json.acc_list_key }}",
            "keyType": "list",
            "options": {"dotNotation": False},
        },
        "type": "n8n-nodes-base.redis",
        "typeVersion": 1,
        "position": [x, y],
        "id": uid("Acc Get frags"),
        "name": "Acc Get frags",
        "credentials": deepcopy(REDIS_CRED),
    }


def redis_del(name: str, key_expr: str, x: int, y: int) -> dict:
    return {
        "parameters": {
            "operation": "delete",
            "key": key_expr,
        },
        "type": "n8n-nodes-base.redis",
        "typeVersion": 1,
        "position": [x, y],
        "id": uid(name),
        "name": name,
        "credentials": deepcopy(REDIS_CRED),
    }


def wire(conns: dict, src: str, dst: str, src_out: int = 0) -> None:
    conns.setdefault(src, {"main": []})
    while len(conns[src]["main"]) <= src_out:
        conns[src]["main"].append([])
    edge = {"node": dst, "type": "main", "index": 0}
    if edge not in conns[src]["main"][src_out]:
        conns[src]["main"][src_out].append(edge)


def remove_nodes_by_name(wf: dict, names: set[str]) -> None:
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in names]
    conns = wf["connections"]
    for name in names:
        conns.pop(name, None)
    for src, data in list(conns.items()):
        for i, outs in enumerate(data.get("main") or []):
            data["main"][i] = [e for e in outs if e.get("node") not in names]


def main() -> None:
    wf = json.loads(WF_PATH.read_text(encoding="utf-8"))
    acc_names = set(NODE_IDS.keys())
    remove_nodes_by_name(wf, acc_names)

    # Webhook: respond immediately so Chatwoot does not time out during Wait
    for n in wf["nodes"]:
        if n["name"] == "Chatwoot Webhook":
            opts = n["parameters"].setdefault("options", {})
            opts["responseMode"] = "onReceived"

    # Layout: insert between Merge Context and Build AI intent prompt
    y = 1632
    x0 = -64  # Merge Context x
    nodes = [
        code_node("Acc Gate", GATE_JS, x0 + 180, y),
        if_accumulate(x0 + 360, y),
        redis_push(x0 + 560, y - 200),
        code_node("Acc After push", AFTER_PUSH_JS, x0 + 760, y - 200),
        redis_incr(x0 + 960, y - 200),
        code_node("Acc After incr", AFTER_INCR_JS, x0 + 1160, y - 200),
        wait_7s(x0 + 1360, y - 200),
        redis_get_version(x0 + 1560, y - 200),
        code_node("Acc Is latest", IS_LATEST_JS, x0 + 1760, y - 200),
        redis_get_frags(x0 + 1960, y - 200),
        code_node("Acc Merge texto", MERGE_JS, x0 + 2160, y - 200),
        redis_del(
            "Acc Del frags",
            "={{ $('Acc Merge texto').item.json.acc_list_key }}",
            x0 + 2360,
            y - 200,
        ),
        redis_del(
            "Acc Del ver",
            "={{ $('Acc Merge texto').item.json.acc_ver_key }}",
            x0 + 2560,
            y - 200,
        ),
        code_node("Acc Continue", CONTINUE_JS, x0 + 2760, y - 200),
    ]
    wf["nodes"].extend(nodes)

    conns = wf["connections"]
    # Merge Context → Acc Gate (was → Build AI)
    conns["Merge Context"] = {
        "main": [[{"node": "Acc Gate", "type": "main", "index": 0}]]
    }
    wire(conns, "Acc Gate", "Acc Switch")
    # true → accumulate path; false → bypass to AI
    wire(conns, "Acc Switch", "Acc Push", 0)
    wire(conns, "Acc Switch", "Build AI intent prompt", 1)
    wire(conns, "Acc Push", "Acc After push")
    wire(conns, "Acc After push", "Acc Incr")
    wire(conns, "Acc Incr", "Acc After incr")
    wire(conns, "Acc After incr", "Acc Wait 7s")
    wire(conns, "Acc Wait 7s", "Acc Get version")
    wire(conns, "Acc Get version", "Acc Is latest")
    wire(conns, "Acc Is latest", "Acc Get frags")
    wire(conns, "Acc Get frags", "Acc Merge texto")
    wire(conns, "Acc Merge texto", "Acc Del frags")
    wire(conns, "Acc Del frags", "Acc Del ver")
    wire(conns, "Acc Del ver", "Acc Continue")
    wire(conns, "Acc Continue", "Build AI intent prompt")

    # Downstream must use accumulated texto, not stale Merge Context
    for n in wf["nodes"]:
        if n["name"] == "Build AI intent prompt":
            n["parameters"]["jsCode"] = (
                "const m = $input.first().json;\n"
                "const text = String(m.last_line || m.texto || '').replace(/\\n?__cw_in_reply_to__:\\S+/g, '').trim();\n"
                "const pre = `Estado actual: ${m.estado || 'idle'}\\nBoton: ${m.boton_id || 'none'}\\nTexto: ${text}`;\n"
                "return [{ json: { ...m, classify_input: pre } }];"
            )
        if n["name"] == "Parse AI intent":
            n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(
                "const base = $('Merge Context').first().json;",
                "const base = $('Build AI intent prompt').first().json;",
            )
        if n.get("type") == "n8n-nodes-base.executeWorkflow":
            val = (n.get("parameters") or {}).get("workflowInputs", {}).get("value") or {}
            for key in ("texto", "boton_id", "estado", "datos_json"):
                if isinstance(val.get(key), str) and "$('Merge Context')" in val[key]:
                    val[key] = val[key].replace("$('Merge Context')", "$('Decide Route')")

    WF_PATH.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Patched {WF_PATH}")
    print("Webhook responseMode=onReceived")
    print(f"Added {len(nodes)} accumulation nodes")
    print("Build AI / Parse AI / Call Booking use accumulated texto")
    print("Attach n8n credential 'Bot Redis' → host bot-redis, port 6379")


if __name__ == "__main__":
    main()
