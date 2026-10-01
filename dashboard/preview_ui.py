"""Local UI preview for dashboard/templates/index.html — no MySQL, no login.

  cd dashboard && .venv/bin/uvicorn preview_ui:app --host 127.0.0.1 --port 8787 --reload

Open http://127.0.0.1:8787/
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# So serialize_solicitud() builds chat_url links in preview.
os.environ.setdefault("DOMAIN", "localhost")
os.environ.setdefault("CHATWOOT_ACCOUNT_ID", "2")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import ALL_TIMES, DAY_NAMES, monday_of, serialize_solicitud
from busqueda import filter_solicitudes_by_query
from stats import compute_solicitudes_week_stats

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

DOCTORS = [
    {"id": 1, "name": "Dr. Artigas"},
    {"id": 2, "name": "Dra. López"},
    {"id": 3, "name": "Dr. Fernández"},
]

CLINIC = {
    "address": "Av. San Martín 1234, Artigas",
    "clinic_hours": "Lun–Vie 8:00–20:00 · Sáb 9:00–13:00",
    "welcome_text": "¡Hola! Bienvenido/a a Clínica Artigas.",
    "obras_sociales": ["Particular", "OSDE", "Swiss Medical", "Galeno", "IOMA"],
}


def _dt(days: int, hour: int = 10, minute: int = 0) -> datetime:
    base = datetime.combine(date.today(), datetime.min.time()) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def build_raw_rows() -> list[dict[str, Any]]:
    """Diverse rows so every badge / action / overflow edge case shows up."""
    today = date.today()
    mon = monday_of(today)
    # Spread created_at across this week + last week for KPI charts.
    return [
        {
            "id": 101,
            "created_at": _dt(0, 9, 12),
            "phone": "+5491112345678",
            "nombre": "Ana Pérez",
            "dni": "32145678",
            "obra_social": "OSDE",
            "telefono_contacto": "11 2345-5678",
            "medico": "Dr. Artigas",
            "horario_preferido": "Mañana preferentemente",
            "status": "pending",
            "conversation_id": "1001",
            "tipo": "turno",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 102,
            "created_at": _dt(-1, 11, 5),
            "phone": "+5491198765432",
            "nombre": "Carlos Gómez",
            "dni": "28456789",
            "obra_social": "Particular",
            "telefono_contacto": "11 9876-5432",
            "medico": "Dra. López",
            "horario_preferido": "-",
            "status": "confirmed",
            "conversation_id": "1002",
            "tipo": "turno",
            "appointment_at": _dt(2, 15, 30),
            "por_orden_de_llegada": 0,
            "nota_paciente": "Traer estudios previos",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 103,
            "created_at": _dt(-1, 14, 40),
            "phone": "+5491155511122",
            "nombre": "María Elena Rodríguez de la Fuente",
            "dni": "30111222",
            "obra_social": "Swiss Medical",
            "telefono_contacto": "11 5551-1122",
            "medico": "Dr. Fernández",
            "horario_preferido": "-",
            "status": "confirmed",
            "conversation_id": "1003",
            "tipo": "turno",
            "appointment_at": _dt(1, 8, 0),
            "por_orden_de_llegada": 1,
            "nota_paciente": "Por orden de llegada — sala 2",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": _dt(-1, 16, 0),
        },
        {
            "id": 104,
            "created_at": _dt(-2, 10, 0),
            "phone": "+5491144433322",
            "nombre": "Luis Martínez",
            "dni": "25999888",
            "obra_social": "IOMA",
            "telefono_contacto": "11 4443-3322",
            "medico": "Dr. Artigas",
            "horario_preferido": "Cualquier tarde",
            "status": "pending",
            "conversation_id": "1004",
            "tipo": "estudio",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "Campo visual + OCT",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 105,
            "created_at": _dt(-2, 16, 22),
            "phone": "+5491177788899",
            "nombre": "Sofía Álvarez",
            "dni": "41222333",
            "obra_social": "Galeno",
            "telefono_contacto": "11 7778-8899",
            "medico": "-",
            "horario_preferido": "Consulta por precios de cirugía",
            "status": "pending",
            "conversation_id": "1005",
            "tipo": "solicitud",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 106,
            "created_at": _dt(-3, 9, 45),
            "phone": "+5491166677788",
            "nombre": "Pedro Ruiz",
            "dni": "22333444",
            "obra_social": "OSDE",
            "telefono_contacto": "11 6667-7788",
            "medico": "Dra. López",
            "horario_preferido": "Cambia turno del viernes",
            "status": "pending",
            "conversation_id": "1006",
            "tipo": "reprogramar",
            "appointment_at": _dt(4, 11, 0),
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 107,
            "created_at": _dt(-3, 12, 10),
            "phone": "+5491133322211",
            "nombre": "Julia Fernández",
            "dni": "33444555",
            "obra_social": "Particular",
            "telefono_contacto": "11 3332-2211",
            "medico": "Dr. Artigas",
            "horario_preferido": "No puede asistir",
            "status": "pending",
            "conversation_id": "1007",
            "tipo": "cancelar",
            "appointment_at": _dt(3, 10, 30),
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 108,
            "created_at": _dt(-4, 8, 30),
            "phone": "+5491122211100",
            "nombre": "Diego Castro",
            "dni": "27888999",
            "obra_social": "OSDE",
            "telefono_contacto": "11 2221-1100",
            "medico": "Dr. Fernández",
            "horario_preferido": "-",
            "status": "cancelled",
            "conversation_id": "1008",
            "tipo": "turno",
            "appointment_at": _dt(-1, 9, 0),
            "por_orden_de_llegada": 0,
            "nota_paciente": "Cancelado por paciente",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 109,
            "created_at": _dt(-4, 15, 0),
            "phone": "+5491188877766",
            "nombre": "Valentina Torres",
            "dni": "40555666",
            "obra_social": "IOMA",
            "telefono_contacto": "11 8887-7766",
            "medico": "-",
            "horario_preferido": "Pregunta por cobertura de lente",
            "status": "contactado",
            "conversation_id": "1009",
            "tipo": "solicitud",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "freeform",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 110,
            "created_at": _dt(-5, 10, 15),
            "phone": "+5491100011122",
            "nombre": "Hernán Díaz",
            "dni": "29111223",
            "obra_social": "Galeno",
            "telefono_contacto": "11 0001-1122",
            "medico": "Dra. López",
            "horario_preferido": "-",
            "status": "confirmed",
            "conversation_id": "1010",
            "tipo": "turno",
            "appointment_at": _dt(5, 17, 0),
            "por_orden_de_llegada": 0,
            "nota_paciente": "Reenviar: falló el envío de plantilla",
            "whatsapp_send_status": "failed",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 1,
            "reminder_sent_at": None,
        },
        {
            "id": 111,
            "created_at": _dt(-5, 18, 40),
            "phone": "+5491199900011",
            "nombre": "Inés Blanco",
            "dni": "35666777",
            "obra_social": "Particular",
            "telefono_contacto": "11 9990-0011",
            "medico": "Dr. Artigas",
            "horario_preferido": "-",
            "status": "confirmed",
            "conversation_id": None,
            "tipo": "reprogramar",
            "appointment_at": _dt(6, 12, 0),
            "por_orden_de_llegada": 0,
            "nota_paciente": "Sin chat vinculado",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        # Prior week (for WoW trends)
        {
            "id": 201,
            "created_at": datetime.combine(mon - timedelta(days=5), datetime.min.time()).replace(
                hour=11
            ),
            "phone": "+5491100000001",
            "nombre": "Histórico A",
            "dni": "10000001",
            "obra_social": "OSDE",
            "telefono_contacto": "-",
            "medico": "Dr. Artigas",
            "horario_preferido": "-",
            "status": "confirmed",
            "conversation_id": "2001",
            "tipo": "turno",
            "appointment_at": datetime.combine(mon - timedelta(days=3), datetime.min.time()).replace(
                hour=10
            ),
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "template",
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 202,
            "created_at": datetime.combine(mon - timedelta(days=4), datetime.min.time()).replace(
                hour=14
            ),
            "phone": "+5491100000002",
            "nombre": "Histórico B",
            "dni": "10000002",
            "obra_social": "Particular",
            "telefono_contacto": "-",
            "medico": "Dra. López",
            "horario_preferido": "-",
            "status": "pending",
            "conversation_id": "2002",
            "tipo": "cancelar",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
        {
            "id": 203,
            "created_at": datetime.combine(mon - timedelta(days=3), datetime.min.time()).replace(
                hour=9
            ),
            "phone": "+5491100000003",
            "nombre": "Histórico C",
            "dni": "10000003",
            "obra_social": "IOMA",
            "telefono_contacto": "-",
            "medico": "Dr. Fernández",
            "horario_preferido": "-",
            "status": "pending",
            "conversation_id": "2003",
            "tipo": "reprogramar",
            "appointment_at": None,
            "por_orden_de_llegada": 0,
            "nota_paciente": "",
            "whatsapp_send_status": None,
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": 0,
            "reminder_sent_at": None,
        },
    ]


RAW_ROWS = build_raw_rows()
SOLICITUDES = [serialize_solicitud(r) for r in RAW_ROWS]
BY_ID = {s["id"]: s for s in SOLICITUDES}


def group_dias(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dias: list[dict[str, Any]] = []
    by_day: dict[str, dict] = {}
    for item in items:
        key = item["dia"] or item["dia_label"]
        if key not in by_day:
            group = {
                "fecha": item["dia"],
                "label": item["dia_label"],
                "solicitudes": [],
            }
            by_day[key] = group
            dias.append(group)
        by_day[key]["solicitudes"].append(item)
    return dias


AVAILABILITY_STORE: dict[tuple[int, str], list[dict[str, Any]]] = {}


def default_availability() -> list[dict[str, Any]]:
    return [
        {
            "day": d,
            "day_name": DAY_NAMES[d],
            "is_unavailable": d == 6,
            "configured": d < 5 or d == 6,
            "manana": (
                {"shift": "manana", "start_time": "08:00", "end_time": "12:30"}
                if d < 5
                else None
            ),
            "noche": (
                {"shift": "noche", "start_time": "16:00", "end_time": "20:00"}
                if d in (0, 2, 4)
                else None
            ),
        }
        for d in range(7)
    ]


app = FastAPI(title="Dashboard UI Preview (mock data)")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "doctors": DOCTORS,
            "days_of_week": list(range(7)),
            "day_names": DAY_NAMES,
            "all_times": ALL_TIMES,
            "all_times_json": json.dumps(ALL_TIMES),
            "week_start": monday_of(date.today()).isoformat(),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout():
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/", status_code=303)


@app.get("/api/doctors")
async def api_doctors():
    return DOCTORS


@app.get("/api/availability")
async def api_get_availability(doctor_id: int, week_start: str | None = None):
    ws = week_start or monday_of(date.today()).isoformat()
    key = (doctor_id, ws)
    avail = AVAILABILITY_STORE.get(key) or default_availability()
    return {
        "week_start": ws,
        "week_label": date.fromisoformat(ws).strftime("%d/%m/%Y"),
        "availability": avail,
    }


@app.post("/api/availability")
async def api_save_availability(request: Request):
    body = await request.json()
    return {"ok": True, "preview": True, "saved": body}


@app.post("/api/availability/unavailable")
async def api_mark_unavailable(request: Request):
    body = await request.json()
    return {"ok": True, "preview": True, "saved": body}


@app.get("/api/solicitudes")
async def api_solicitudes():
    return JSONResponse(
        {"solicitudes": SOLICITUDES, "dias": group_dias(SOLICITUDES)},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/api/solicitudes/stats")
async def api_solicitudes_stats():
    payload = compute_solicitudes_week_stats(RAW_ROWS)
    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/api/solicitudes/search")
async def api_solicitudes_search(q: str = ""):
    matched = filter_solicitudes_by_query(RAW_ROWS, q, limit=20)
    return JSONResponse(
        {"solicitudes": [serialize_solicitud(r) for r in matched], "q": q},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/api/clinic-settings")
async def api_clinic_settings():
    return CLINIC


@app.post("/api/clinic-settings")
async def api_save_clinic_settings(request: Request):
    body = await request.json()
    CLINIC.update(
        {
            "address": str(body.get("address") or CLINIC["address"]),
            "clinic_hours": str(body.get("clinic_hours") or CLINIC["clinic_hours"]),
            "welcome_text": str(body.get("welcome_text") or CLINIC["welcome_text"]),
        }
    )
    obras = body.get("obras_sociales", CLINIC["obras_sociales"])
    if isinstance(obras, str):
        obras = [x.strip() for x in obras.split("\n") if x.strip()]
    CLINIC["obras_sociales"] = obras
    return {"ok": True, "preview": True}


async def _ok_stub(request: Request, solicitud_id: int | None = None):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return {
        "ok": True,
        "preview": True,
        "solicitud_id": solicitud_id,
        "echo": body,
        "whatsapp_send_status": "sent",
        "whatsapp_send_channel": "template",
        "whatsapp_warning": None,
    }


for path in (
    "/api/solicitudes/{solicitud_id}/confirm",
    "/api/solicitudes/{solicitud_id}/mark-confirmed",
    "/api/solicitudes/{solicitud_id}/responder-consulta",
    "/api/solicitudes/{solicitud_id}/mark-contactado",
    "/api/solicitudes/{solicitud_id}/reprogramar",
    "/api/solicitudes/{solicitud_id}/cancelar",
    "/api/solicitudes/{solicitud_id}/reenviar",
):
    app.add_api_route(path, _ok_stub, methods=["POST"])

app.add_api_route("/api/solicitudes/reprogramar", _ok_stub, methods=["POST"])
app.add_api_route("/api/solicitudes/cancelar", _ok_stub, methods=["POST"])
app.add_api_route("/api/solicitudes/recordar", _ok_stub, methods=["POST"])
app.add_api_route(
    "/api/solicitudes/{solicitud_id}/recordar", _ok_stub, methods=["POST"]
)
app.add_api_route("/api/disponibilidad-enabled", _ok_stub, methods=["POST"])
app.add_api_route("/api/preguntas-frecuentes", _ok_stub, methods=["GET", "PUT"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("preview_ui:app", host="127.0.0.1", port=8787, reload=True)
