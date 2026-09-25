#!/usr/bin/env bash
# Red-capable loop for Meta #132000 on confirmacion_reprogramacion.
# Run on the VPS (needs .env with Chatwoot credentials):
#   bash scripts/diag-reprogram-plantilla.sh
#   CONVERSATION_ID=316 bash scripts/diag-reprogram-plantilla.sh
#   SYNC=1 bash scripts/diag-reprogram-plantilla.sh   # force inbox template sync first
#
# Exit 0 = delivered/sent without #132000
# Exit 1 = #132000 (or other send failure)
# Exit 2 = misconfigured / no conversation
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a

export CONVERSATION_ID="${CONVERSATION_ID:-}"
export SYNC="${SYNC:-0}"

python3 - <<'PY'
import os, json, sys, time, re, urllib.request, urllib.error

host = (os.environ.get("CHATWOOT_HOST") or os.environ.get("DOMAIN") or "").lstrip(".")
acct = (os.environ.get("CHATWOOT_ACCOUNT_ID") or "2").strip() or "2"
token = (os.environ.get("CHATWOOT_API_TOKEN") or "").strip()
inbox = (os.environ.get("CHATWOOT_INBOX_ID") or "").strip()
cid = (os.environ.get("CONVERSATION_ID") or "").strip()
do_sync = (os.environ.get("SYNC") or "0").strip() in ("1", "true", "yes")
base = f"https://chat.{host}/api/v1"

if not host or not token or not inbox:
    print("LOOP_VERDICT=MISCONFIG missing CHATWOOT_HOST/DOMAIN, CHATWOOT_API_TOKEN, or CHATWOOT_INBOX_ID")
    sys.exit(2)

def http(method, url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "api-access-token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(body) if body else {}
        except Exception:
            j = {"raw": body[:500]}
        return e.code, j

def find_template(name: str):
    _, j = http("GET", f"{base}/accounts/{acct}/inboxes/{inbox}")
    found = None

    def walk(obj):
        nonlocal found
        if found is not None:
            return
        if isinstance(obj, dict):
            if obj.get("name") == name:
                found = obj
                return
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(j)
    return found

tpl = find_template("confirmacion_reprogramacion")
if not tpl:
    print("LOOP_VERDICT=MISCONFIG template confirmacion_reprogramacion not in inbox cache")
    sys.exit(2)

body = next((c for c in (tpl.get("components") or []) if c.get("type") == "BODY"), {})
vars_ = re.findall(r"\{\{(\w+)\}\}", body.get("text") or "")
print(
    f"TEMPLATE status={tpl.get('status')} lang={tpl.get('language')} "
    f"fmt={tpl.get('parameter_format')} body_vars={vars_}"
)

if do_sync or str(tpl.get("status") or "").upper() != "APPROVED":
    sc, sj = http("POST", f"{base}/accounts/{acct}/inboxes/{inbox}/sync_templates")
    print(f"sync_http={sc} msg={sj.get('message') if isinstance(sj, dict) else sj}")
    for i in range(12):
        time.sleep(2)
        tpl = find_template("confirmacion_reprogramacion") or {}
        print(f"after_sync[{i}] status={tpl.get('status')}")
        if str(tpl.get("status") or "").upper() == "APPROVED":
            break

tpl = find_template("confirmacion_reprogramacion") or {}
status_tpl = str(tpl.get("status") or "").upper()
if status_tpl != "APPROVED":
    print(f"LOOP_VERDICT=RED template_status={status_tpl} (Chatwoot #13805-style: PENDING → misleading #132000)")
    sys.exit(1)

if not cid:
    _, convs = http("GET", f"{base}/accounts/{acct}/conversations?inbox_id={inbox}&status=all&page=1")
    items = []
    data = convs.get("data") or convs.get("payload") or convs
    if isinstance(data, dict):
        items = data.get("payload") or data.get("conversations") or []
    elif isinstance(data, list):
        items = data
    for it in items or []:
        if isinstance(it, dict) and it.get("id"):
            cid = str(it["id"])
            break
    if not cid:
        print("LOOP_VERDICT=MISCONFIG no conversation; set CONVERSATION_ID=")
        sys.exit(2)
    print(f"picked_conversation_id={cid}")

payload = {
    "message_type": "outgoing",
    "private": False,
    "content": " ",
    "template_params": {
        "name": "confirmacion_reprogramacion",
        "category": "UTILITY",
        "language": "es_AR",
        "processed_params": {
            "body": {
                "1": "Diag Loop",
                "2": "Dr. Artigas",
                "3": "25/09/2026 10:30",
            }
        },
    },
}
sc, sj = http("POST", f"{base}/accounts/{acct}/conversations/{cid}/messages", payload)
mid = sj.get("id") if isinstance(sj, dict) else None
print(f"send_http={sc} message_id={mid}")

err = None
status = None
for i in range(8):
    time.sleep(1.5)
    _, gj = http("GET", f"{base}/accounts/{acct}/conversations/{cid}/messages")
    msgs = gj.get("payload") if isinstance(gj, dict) else []
    target = None
    for m in msgs or []:
        if mid and str(m.get("id")) == str(mid):
            target = m
            break
    if not target:
        continue
    status = target.get("status")
    ca = target.get("content_attributes") or {}
    err = ca.get("external_error") if isinstance(ca, dict) else None
    print(f"poll[{i}] status={status} err={err!r}")
    if err or status in ("failed", "delivered", "read"):
        break

if err and "132000" in str(err):
    print("LOOP_VERDICT=RED symptom=#132000")
    print(f"SYMPTOM={err}")
    sys.exit(1)
if err or status == "failed":
    print("LOOP_VERDICT=RED_OTHER")
    print(f"SYMPTOM={err or status}")
    sys.exit(1)
print(f"LOOP_VERDICT=GREEN status={status}")
sys.exit(0)
PY
