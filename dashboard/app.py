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


def normalize_tipo(value: Any) -> str:
    tipo = str(value or "turno").strip().lower()
    if tipo not in ("turno", "cancelar", "estudio"):
        return "turno"
    return tipo


@app.get("/api/solicitudes")
@login_required
async def api_solicitudes(request: Request):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'turno_solicitudes'
              AND COLUMN_NAME = 'tipo'
            """
        )
        has_tipo = int((cur.fetchone() or {}).get("n") or 0) > 0
        tipo_sql = "tipo" if has_tipo else "'turno' AS tipo"
        cur.execute(
            f"""
            SELECT id, created_at, phone, nombre, dni, obra_social,
                   telefono_contacto, medico, horario_preferido, status,
                   {tipo_sql}
            FROM turno_solicitudes
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        created = parse_solicitud_dt(r["created_at"])
        if created:
            created_s = created.strftime("%d/%m/%Y %H:%M")
            hora = created.strftime("%H:%M")
            dia = created.date().isoformat()
            dia_label = f"{DAY_NAMES[created.weekday()]} {created.strftime('%d/%m/%Y')}"
        else:
            created_s = str(r["created_at"] or "-")
            hora = "-"
            dia = ""
            dia_label = "Sin fecha"
        out.append(
            {
                "id": r["id"],
                "tipo": normalize_tipo(r.get("tipo")),
                "created_at": created_s,
                "hora": hora,
                "dia": dia,
                "dia_label": dia_label,
                "phone": r["phone"],
                "nombre": r["nombre"] or "-",
                "dni": r["dni"] or "-",
                "obra_social": r["obra_social"] or "-",
                "telefono_contacto": r["telefono_contacto"] or "-",
                "medico": r["medico"] or "-",
                "horario_preferido": r["horario_preferido"] or "-",
                "status": r["status"],
            }
        )

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

    return {"solicitudes": out, "dias": dias}


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
