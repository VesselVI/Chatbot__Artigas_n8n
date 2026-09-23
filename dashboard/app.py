import json
import os
from datetime import date, datetime, timedelta, time
from functools import wraps
from typing import Any

import mysql.connector
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from confirmacion import (
    CONFIRMABLE_TIPOS,
    CONFIRMED_STATUS,
    ConfirmError,
    assert_confirmable,
    normalize_tipo,
    status_badge_label,
    validate_confirm_payload,
)
from chatwoot_send import ChatwootSendError, send_confirmacion
from mensajes import build_outbound_message, format_dia_hora_display

DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

ALL_TIMES = [
    f"{h:02d}:{m:02d}"
    for h in range(7, 22)
    for m in (0, 30)
] + ["22:00"]


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def get_db():
    return mysql.connector.connect(
        host=env("MYSQL_HOST", "mysql"),
        port=int(env("MYSQL_PORT", "3306")),
        database=env("MYSQL_DATABASE", "artigas_bot"),
        user=env("MYSQL_USER", "artigas"),
        password=env("MYSQL_PASSWORD", ""),
        charset="utf8mb4",
    )


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_week_start(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return monday_of(date.today())


def parse_hhmm(value: Any) -> str | None:
    s = str(value or "").strip()
    if s in ALL_TIMES:
        return s
    return None


def shift_range(body: dict, key: str) -> tuple[str, str] | None:
    enabled = body.get(key)
    if isinstance(enabled, dict):
        if not enabled:
            return None
        start = parse_hhmm(enabled.get("start_time") or enabled.get("start"))
        end = parse_hhmm(enabled.get("end_time") or enabled.get("end"))
    else:
        if not enabled:
            return None
        start = parse_hhmm(body.get(f"{key}_start") or body.get(f"{key}_start_time"))
        end = parse_hhmm(body.get(f"{key}_end") or body.get(f"{key}_end_time"))
    if not start or not end:
        return None
    if start >= end:
        return None
    return start, end


def format_time(t: Any) -> str:
    if t is None:
        return ""
    if isinstance(t, timedelta):
        total = int(t.total_seconds())
        h, rem = divmod(total, 3600)
        m, _ = divmod(rem, 60)
        return f"{h:02d}:{m:02d}"
    if isinstance(t, time):
        return t.strftime("%H:%M")
    s = str(t)
    return s[:5] if len(s) >= 5 else s


def login_required(handler):
    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user"):
            return RedirectResponse("/login", status_code=303)
        return await handler(request, *args, **kwargs)

    return wrapper


app = FastAPI(title="Clínica Artigas Dashboard")
app.add_middleware(
    SessionMiddleware,
    secret_key=env("DASHBOARD_SECRET_KEY", "dev-secret-change-me"),
    session_cookie="artigas_dash",
    same_site="lax",
    https_only=False,
)
templates = Jinja2Templates(directory="templates")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/privacidad", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """Public page for Meta App Dashboard Privacy Policy URL (no login)."""
    return templates.TemplateResponse(
        "privacidad.html",
        {"request": request},
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == env("DASHBOARD_USERNAME") and password == env("DASHBOARD_PASSWORD"):
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Usuario o contraseña incorrectos."},
        status_code=401,
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
@login_required
async def index(request: Request):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name"
        )
        doctors = cur.fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "doctors": doctors,
            "days_of_week": list(range(7)),
            "day_names": DAY_NAMES,
            "all_times": ALL_TIMES,
            "all_times_json": json.dumps(ALL_TIMES),
            "week_start": monday_of(date.today()).isoformat(),
        },
    )


@app.get("/api/doctors")
@login_required
async def api_doctors(request: Request):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name FROM doctors WHERE active = 1 ORDER BY sort_order, name"
        )
        return cur.fetchall()
    finally:
        conn.close()


@app.get("/api/availability")
@login_required
async def api_get_availability(
    request: Request,
    doctor_id: int,
    week_start: str | None = None,
):
    ws = parse_week_start(week_start)
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT day, shift, is_unavailable, start_time, end_time
            FROM doctor_availability
            WHERE doctor_id = %s AND week_start = %s
            ORDER BY day, start_time
            """,
            (doctor_id, ws),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    by_day: dict[int, list] = {d: [] for d in range(7)}
    for r in rows:
        by_day[int(r["day"])].append(r)

    result = []
    for d in range(7):
        day_rows = by_day[d]
        manana = None
        noche = None
        unavailable = False
        for r in day_rows:
            if r["is_unavailable"]:
                unavailable = True
                continue
            slot = {
                "shift": r["shift"],
                "start_time": format_time(r["start_time"]),
                "end_time": format_time(r["end_time"]),
            }
            if r["shift"] == "noche":
                noche = slot
            else:
                manana = slot
        result.append(
            {
                "day": d,
                "day_name": DAY_NAMES[d],
                "is_unavailable": unavailable and not manana and not noche,
                "configured": bool(day_rows),
                "manana": manana,
                "noche": noche,
            }
        )
    return {
        "week_start": ws.isoformat(),
        "week_label": ws.strftime("%d/%m/%Y"),
        "availability": result,
    }


@app.post("/api/availability")
@login_required
async def api_save_availability(request: Request):
    body = await request.json()
    doctor_id = int(body["doctor_id"])
    ws = parse_week_start(body.get("week_start"))
    days = [int(d) for d in body.get("days", [])]
    want_manana = bool(body.get("manana"))
    want_noche = bool(body.get("noche"))
    manana = shift_range(body, "manana")
    noche = shift_range(body, "noche")

    if not days:
        return JSONResponse({"error": "Seleccioná al menos un día."}, status_code=400)
    if not want_manana and not want_noche:
        return JSONResponse(
            {"error": "Seleccioná turno mañana y/o turno noche."},
            status_code=400,
        )
    if want_manana and not manana:
        return JSONResponse(
            {"error": "Completá inicio y fin del turno mañana. El fin debe ser después del inicio."},
            status_code=400,
        )
    if want_noche and not noche:
        return JSONResponse(
            {"error": "Completá inicio y fin del turno noche. El fin debe ser después del inicio."},
            status_code=400,
        )

    conn = get_db()
    try:
        cur = conn.cursor()
        for d in days:
            cur.execute(
                """
                DELETE FROM doctor_availability
                WHERE doctor_id = %s AND week_start = %s AND day = %s
                """,
                (doctor_id, ws, d),
            )
            if want_manana and manana:
                start, end = manana
                cur.execute(
                    """
                    INSERT INTO doctor_availability
                      (doctor_id, week_start, day, shift, is_unavailable, start_time, end_time)
                    VALUES (%s, %s, %s, 'manana', 0, %s, %s)
                    """,
                    (doctor_id, ws, d, start, end),
                )
            if want_noche and noche:
                start, end = noche
                cur.execute(
                    """
                    INSERT INTO doctor_availability
                      (doctor_id, week_start, day, shift, is_unavailable, start_time, end_time)
                    VALUES (%s, %s, %s, 'noche', 0, %s, %s)
                    """,
                    (doctor_id, ws, d, start, end),
                )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "message": "Horarios guardados."}


@app.post("/api/availability/unavailable")
@login_required
async def api_mark_unavailable(request: Request):
    body = await request.json()
    doctor_id = int(body["doctor_id"])
    ws = parse_week_start(body.get("week_start"))
    days = [int(d) for d in body.get("days", [])]

    if not days:
        return JSONResponse({"error": "Seleccioná al menos un día."}, status_code=400)

    conn = get_db()
    try:
        cur = conn.cursor()
        for d in days:
            cur.execute(
                """
                DELETE FROM doctor_availability
                WHERE doctor_id = %s AND week_start = %s AND day = %s
                """,
                (doctor_id, ws, d),
            )
            cur.execute(
                """
                INSERT INTO doctor_availability
                  (doctor_id, week_start, day, shift, is_unavailable, start_time, end_time)
                VALUES (%s, %s, %s, 'manana', 1, NULL, NULL)
                """,
                (doctor_id, ws, d),
            )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "message": "Días marcados como no disponible."}


def parse_solicitud_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    s = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    return int((cur.fetchone() or {}).get("n") or 0) > 0


def fetch_solicitud(solicitud_id: int) -> dict[str, Any] | None:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        has_tipo = _column_exists(cur, "turno_solicitudes", "tipo")
        has_appointment = _column_exists(cur, "turno_solicitudes", "appointment_at")
        has_nota = _column_exists(cur, "turno_solicitudes", "nota_paciente")
        has_orden = _column_exists(cur, "turno_solicitudes", "por_orden_de_llegada")
        has_send = _column_exists(cur, "turno_solicitudes", "whatsapp_send_status")
        tipo_sql = "tipo" if has_tipo else "'turno' AS tipo"
        appointment_sql = "appointment_at" if has_appointment else "NULL AS appointment_at"
        nota_sql = "nota_paciente" if has_nota else "NULL AS nota_paciente"
        orden_sql = (
            "por_orden_de_llegada"
            if has_orden
            else "0 AS por_orden_de_llegada"
        )
        if has_send:
            send_sql = (
                "whatsapp_send_status, whatsapp_send_channel, whatsapp_nota_omitted"
            )
        else:
            send_sql = (
                "NULL AS whatsapp_send_status, NULL AS whatsapp_send_channel, "
                "0 AS whatsapp_nota_omitted"
            )
        cur.execute(
            f"""
            SELECT id, created_at, phone, nombre, dni, obra_social,
                   telefono_contacto, medico, horario_preferido, status,
                   conversation_id, {tipo_sql}, {appointment_sql}, {orden_sql},
                   {nota_sql}, {send_sql}
            FROM turno_solicitudes
            WHERE id = %s
            """,
            (solicitud_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def list_solicitudes_rows() -> list[dict[str, Any]]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        has_tipo = _column_exists(cur, "turno_solicitudes", "tipo")
        has_appointment = _column_exists(cur, "turno_solicitudes", "appointment_at")
        has_nota = _column_exists(cur, "turno_solicitudes", "nota_paciente")
        has_orden = _column_exists(cur, "turno_solicitudes", "por_orden_de_llegada")
        has_send = _column_exists(cur, "turno_solicitudes", "whatsapp_send_status")
        tipo_sql = "tipo" if has_tipo else "'turno' AS tipo"
        appointment_sql = "appointment_at" if has_appointment else "NULL AS appointment_at"
        nota_sql = "nota_paciente" if has_nota else "NULL AS nota_paciente"
        orden_sql = (
            "por_orden_de_llegada"
            if has_orden
            else "0 AS por_orden_de_llegada"
        )
        if has_send:
            send_sql = (
                "whatsapp_send_status, whatsapp_send_channel, whatsapp_nota_omitted"
            )
        else:
            send_sql = (
                "NULL AS whatsapp_send_status, NULL AS whatsapp_send_channel, "
                "0 AS whatsapp_nota_omitted"
            )
        cur.execute(
            f"""
            SELECT id, created_at, phone, nombre, dni, obra_social,
                   telefono_contacto, medico, horario_preferido, status,
                   conversation_id, {tipo_sql}, {appointment_sql}, {orden_sql},
                   {nota_sql}, {send_sql}
            FROM turno_solicitudes
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
        return list(cur.fetchall() or [])
    finally:
        conn.close()


def save_solicitud_confirmacion(solicitud_id: int, fields: dict[str, Any]) -> None:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        has_appointment = _column_exists(cur, "turno_solicitudes", "appointment_at")
        has_nota = _column_exists(cur, "turno_solicitudes", "nota_paciente")
        has_orden = _column_exists(cur, "turno_solicitudes", "por_orden_de_llegada")
        has_send = _column_exists(cur, "turno_solicitudes", "whatsapp_send_status")
        sets = [
            "nombre = %s",
            "medico = %s",
            "status = %s",
        ]
        params: list[Any] = [
            fields["nombre"],
            fields["medico"],
            fields["status"],
        ]
        if has_appointment and "appointment_at" in fields:
            sets.append("appointment_at = %s")
            params.append(fields["appointment_at"])
        if has_orden and "por_orden_de_llegada" in fields:
            sets.append("por_orden_de_llegada = %s")
            params.append(1 if fields["por_orden_de_llegada"] else 0)
        if has_nota and "nota_paciente" in fields:
            sets.append("nota_paciente = %s")
            params.append(fields["nota_paciente"])
        if has_send:
            if "whatsapp_send_status" in fields:
                sets.append("whatsapp_send_status = %s")
                params.append(fields["whatsapp_send_status"])
            if "whatsapp_send_channel" in fields:
                sets.append("whatsapp_send_channel = %s")
                params.append(fields["whatsapp_send_channel"])
            if "whatsapp_nota_omitted" in fields:
                sets.append("whatsapp_nota_omitted = %s")
                params.append(1 if fields["whatsapp_nota_omitted"] else 0)
        params.append(solicitud_id)
        cur.execute(
            f"UPDATE turno_solicitudes SET {', '.join(sets)} WHERE id = %s",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def _format_appointment_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    s = str(value).strip()
    if not s:
        return None
    dt = parse_solicitud_dt(value)
    if dt:
        return dt.strftime("%Y-%m-%dT%H:%M")
    return s


def serialize_solicitud(r: dict[str, Any]) -> dict[str, Any]:
    created = parse_solicitud_dt(r.get("created_at"))
    if created:
        created_s = created.strftime("%d/%m/%Y %H:%M")
        hora = created.strftime("%H:%M")
        dia = created.date().isoformat()
        dia_label = f"{DAY_NAMES[created.weekday()]} {created.strftime('%d/%m/%Y')}"
    else:
        created_s = str(r.get("created_at") or "-")
        hora = "-"
        dia = ""
        dia_label = "Sin fecha"
    tipo = normalize_tipo(r.get("tipo"))
    status = str(r.get("status") or "pending")
    appointment_at = _format_appointment_at(r.get("appointment_at"))
    por_orden = bool(int(r.get("por_orden_de_llegada") or 0))
    nota = r.get("nota_paciente")
    if nota is None:
        nota = ""
    else:
        nota = str(nota)
    if appointment_at:
        detalle = format_dia_hora_display(
            r.get("appointment_at"), por_orden_de_llegada=por_orden
        )
    else:
        detalle = r.get("horario_preferido") or "-"
    send_status = str(r.get("whatsapp_send_status") or "").strip().lower() or None
    send_channel = str(r.get("whatsapp_send_channel") or "").strip().lower() or None
    nota_omitted = bool(int(r.get("whatsapp_nota_omitted") or 0))
    is_confirmed = status.lower() == CONFIRMED_STATUS
    can_confirm = status.lower() == "pending" and tipo in CONFIRMABLE_TIPOS
    appointment_date = appointment_at[:10] if appointment_at and len(appointment_at) >= 10 else None
    return {
        "id": r["id"],
        "tipo": tipo,
        "created_at": created_s,
        "hora": hora,
        "dia": dia,
        "dia_label": dia_label,
        "phone": r["phone"],
        "nombre": r.get("nombre") or "-",
        "dni": r.get("dni") or "-",
        "obra_social": r.get("obra_social") or "-",
        "telefono_contacto": r.get("telefono_contacto") or "-",
        "medico": r.get("medico") or "-",
        "horario_preferido": r.get("horario_preferido") or "-",
        "appointment_at": appointment_at,
        "appointment_date": appointment_date,
        "por_orden_de_llegada": por_orden,
        "nota_paciente": nota,
        "status": status,
        "status_badge": status_badge_label(status, tipo),
        "can_confirm": can_confirm,
        "can_edit_resend": is_confirmed and send_status == "sent",
        "can_reenviar": is_confirmed and send_status == "failed",
        "whatsapp_send_status": send_status,
        "whatsapp_send_channel": send_channel,
        "whatsapp_nota_omitted": nota_omitted,
        "fallo_al_enviar": send_status == "failed",
        "conversation_id": r.get("conversation_id") or None,
        "chat_url": chatwoot_conversation_url(r.get("conversation_id")),
        "detalle": detalle if isinstance(detalle, str) else str(detalle),
    }


def chatwoot_conversation_url(conversation_id: Any) -> str | None:
    cid = str(conversation_id or "").strip()
    if not cid:
        return None
    host = (env("CHATWOOT_HOST") or env("DOMAIN") or "").strip().lstrip(".")
    if not host:
        return None
    account_id = (env("CHATWOOT_ACCOUNT_ID") or "2").strip() or "2"
    return f"https://chat.{host}/app/accounts/{account_id}/conversations/{cid}"


@app.get("/api/solicitudes")
@login_required
async def api_solicitudes(request: Request):
    rows = list_solicitudes_rows()
    out = [serialize_solicitud(r) for r in rows]

    dias = []
    by_day: dict[str, dict] = {}
    for item in out:
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

    return JSONResponse(
        {"solicitudes": out, "dias": dias},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/solicitudes/{solicitud_id}/confirm")
@login_required
async def api_confirm_solicitud(request: Request, solicitud_id: int):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Cuerpo inválido.", "code": "invalid_body"},
            status_code=400,
        )
    try:
        payload = validate_confirm_payload(body if isinstance(body, dict) else {})
        existing = fetch_solicitud(solicitud_id)
        was_confirmed = str((existing or {}).get("status") or "").lower() == CONFIRMED_STATUS
        row = assert_confirmable(existing, allow_confirmed=was_confirmed)
        tipo = normalize_tipo(row.get("tipo"))
        fields = {
            "nombre": payload["nombre"],
            "medico": payload["medico"],
            "appointment_at": payload["appointment_at"],
            "por_orden_de_llegada": payload["por_orden_de_llegada"],
            "nota_paciente": payload["nota_paciente"],
            "status": CONFIRMED_STATUS,
        }
        # Persist first (even if WhatsApp later fails).
        save_solicitud_confirmacion(solicitud_id, fields)

        message = build_outbound_message(
            tipo,
            nombre=payload["nombre"],
            medico=payload["medico"],
            appointment_at=payload["appointment_at"],
            nota_paciente=payload["nota_paciente"],
            include_nota=True,
            por_orden_de_llegada=payload["por_orden_de_llegada"],
        )
        send_outcome = _attempt_whatsapp_send(
            row.get("conversation_id"),
            tipo=tipo,
            message=message,
            nombre=payload["nombre"],
            medico=payload["medico"],
            appointment_at=payload["appointment_at"],
            nota_paciente=payload["nota_paciente"],
            por_orden_de_llegada=payload["por_orden_de_llegada"],
        )
        save_solicitud_confirmacion(
            solicitud_id,
            {
                **fields,
                "whatsapp_send_status": send_outcome["whatsapp_send_status"],
                "whatsapp_send_channel": send_outcome["whatsapp_send_channel"],
                "whatsapp_nota_omitted": send_outcome["whatsapp_nota_omitted"],
            },
        )
        return {
            "ok": True,
            "id": solicitud_id,
            "status": CONFIRMED_STATUS,
            "status_badge": status_badge_label(CONFIRMED_STATUS, tipo),
            "appointment_at": payload["appointment_at"].strftime("%Y-%m-%dT%H:%M"),
            "por_orden_de_llegada": payload["por_orden_de_llegada"],
            "nota_paciente": payload["nota_paciente"],
            "nombre": payload["nombre"],
            "medico": payload["medico"],
            "whatsapp_sent": send_outcome["whatsapp_send_status"] == "sent",
            "whatsapp_send_status": send_outcome["whatsapp_send_status"],
            "whatsapp_send_channel": send_outcome["whatsapp_send_channel"],
            "whatsapp_nota_omitted": send_outcome["whatsapp_nota_omitted"],
            "whatsapp_warning": send_outcome.get("whatsapp_warning"),
            "message_preview": message,
            "edited": was_confirmed,
        }
    except ConfirmError as e:
        status = 404 if e.code == "not_found" else 400
        return JSONResponse(
            {"ok": False, "error": str(e), "code": e.code},
            status_code=status,
        )


@app.post("/api/solicitudes/{solicitud_id}/reenviar")
@login_required
async def api_reenviar_solicitud(request: Request, solicitud_id: int):
    """Reenviar same stored payload after Fallo al enviar (no field edit)."""
    row = fetch_solicitud(solicitud_id)
    if not row:
        return JSONResponse(
            {"ok": False, "error": "Solicitud no encontrada.", "code": "not_found"},
            status_code=404,
        )
    if str(row.get("status") or "").lower() != CONFIRMED_STATUS:
        return JSONResponse(
            {
                "ok": False,
                "error": "Solo se reenvía un turno confirmado.",
                "code": "not_confirmed",
            },
            status_code=400,
        )
    if str(row.get("whatsapp_send_status") or "").lower() != "failed":
        return JSONResponse(
            {
                "ok": False,
                "error": "Reenviar solo aplica tras Fallo al enviar.",
                "code": "not_failed",
            },
            status_code=400,
        )
    tipo = normalize_tipo(row.get("tipo"))
    appointment_at = row.get("appointment_at")
    if not appointment_at:
        return JSONResponse(
            {
                "ok": False,
                "error": "Falta Día/hora del turno.",
                "code": "missing_appointment_at",
            },
            status_code=400,
        )
    nombre = str(row.get("nombre") or "").strip()
    medico = str(row.get("medico") or "").strip()
    nota = str(row.get("nota_paciente") or "").strip()
    por_orden = bool(int(row.get("por_orden_de_llegada") or 0))
    message = build_outbound_message(
        tipo,
        nombre=nombre,
        medico=medico,
        appointment_at=appointment_at,
        nota_paciente=nota,
        include_nota=True,
        por_orden_de_llegada=por_orden,
    )
    send_outcome = _attempt_whatsapp_send(
        row.get("conversation_id"),
        tipo=tipo,
        message=message,
        nombre=nombre,
        medico=medico,
        appointment_at=appointment_at,
        nota_paciente=nota,
        por_orden_de_llegada=por_orden,
    )
    save_solicitud_confirmacion(
        solicitud_id,
        {
            "nombre": nombre,
            "medico": medico,
            "status": CONFIRMED_STATUS,
            "appointment_at": appointment_at,
            "por_orden_de_llegada": por_orden,
            "nota_paciente": nota,
            "whatsapp_send_status": send_outcome["whatsapp_send_status"],
            "whatsapp_send_channel": send_outcome["whatsapp_send_channel"],
            "whatsapp_nota_omitted": send_outcome["whatsapp_nota_omitted"],
        },
    )
    return {
        "ok": True,
        "id": solicitud_id,
        "whatsapp_sent": send_outcome["whatsapp_send_status"] == "sent",
        "whatsapp_send_status": send_outcome["whatsapp_send_status"],
        "whatsapp_send_channel": send_outcome["whatsapp_send_channel"],
        "whatsapp_nota_omitted": send_outcome["whatsapp_nota_omitted"],
        "whatsapp_warning": send_outcome.get("whatsapp_warning"),
        "message_preview": message,
    }


def _attempt_whatsapp_send(
    conversation_id: Any,
    *,
    tipo: str,
    message: str,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str,
    por_orden_de_llegada: bool = False,
) -> dict[str, Any]:
    """Persist-independent send attempt. Never raises — returns status fields."""
    warning = None
    try:
        result = send_confirmacion(
            conversation_id,
            freeform_content=message,
            tipo=tipo,
            nombre=nombre,
            medico=medico,
            dia_hora_display=format_dia_hora_display(
                appointment_at, por_orden_de_llegada=por_orden_de_llegada
            ),
            nota_paciente=nota_paciente,
        )
        if result.nota_omitted and (nota_paciente or "").strip():
            warning = (
                "Ventana cerrada: se envió plantilla utility sin la Nota al paciente."
            )
        return {
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": result.channel,
            "whatsapp_nota_omitted": result.nota_omitted,
            "whatsapp_warning": warning,
        }
    except ChatwootSendError as e:
        return {
            "whatsapp_send_status": "failed",
            "whatsapp_send_channel": None,
            "whatsapp_nota_omitted": False,
            "whatsapp_warning": str(e),
        }


@app.get("/api/clinic-settings")
@login_required
async def api_clinic_settings(request: Request):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT address, clinic_hours, obras_sociales, welcome_text FROM clinic_settings WHERE id = 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    obras = row["obras_sociales"]
    if isinstance(obras, str):
        obras = json.loads(obras)
    row["obras_sociales"] = obras
    return row


@app.post("/api/clinic-settings")
@login_required
async def api_save_clinic_settings(request: Request):
    body = await request.json()
    address = body.get("address", "").strip()
    clinic_hours = body.get("clinic_hours", "").strip()
    welcome_text = body.get("welcome_text", "").strip()
    obras = body.get("obras_sociales", [])
    if isinstance(obras, str):
        obras = [x.strip() for x in obras.split("\n") if x.strip()]

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE clinic_settings
            SET address = %s,
                clinic_hours = %s,
                welcome_text = %s,
                obras_sociales = CAST(%s AS JSON)
            WHERE id = 1
            """,
            (address, clinic_hours, welcome_text, json.dumps(obras, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
