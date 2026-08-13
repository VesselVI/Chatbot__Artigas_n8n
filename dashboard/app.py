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
]


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
            SELECT day, is_unavailable, start_time, end_time
            FROM doctor_availability
            WHERE doctor_id = %s AND week_start = %s
            """,
            (doctor_id, ws),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    by_day = {int(r["day"]): r for r in rows}
    result = []
    for d in range(7):
        row = by_day.get(d)
        if not row:
            result.append(
                {
                    "day": d,
                    "day_name": DAY_NAMES[d],
                    "is_unavailable": False,
                    "configured": False,
                    "start_time": None,
                    "end_time": None,
                }
            )
        else:
            result.append(
                {
                    "day": d,
                    "day_name": DAY_NAMES[d],
                    "is_unavailable": bool(row["is_unavailable"]),
                    "configured": True,
                    "start_time": format_time(row["start_time"]),
                    "end_time": format_time(row["end_time"]),
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
    start_time = body.get("start_time")
    end_time = body.get("end_time")

    if not days:
        return JSONResponse({"error": "Seleccioná al menos un día."}, status_code=400)
    if not start_time or not end_time:
        return JSONResponse({"error": "Completá hora inicio y fin."}, status_code=400)
    if start_time >= end_time:
        return JSONResponse(
            {"error": "La hora de fin debe ser posterior al inicio."},
            status_code=400,
        )

    conn = get_db()
    try:
        cur = conn.cursor()
        for d in days:
            cur.execute(
                """
                INSERT INTO doctor_availability
                  (doctor_id, week_start, day, is_unavailable, start_time, end_time)
                VALUES (%s, %s, %s, 0, %s, %s)
                ON DUPLICATE KEY UPDATE
                  is_unavailable = 0,
                  start_time = VALUES(start_time),
                  end_time = VALUES(end_time)
                """,
                (doctor_id, ws, d, start_time, end_time),
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
                INSERT INTO doctor_availability
                  (doctor_id, week_start, day, is_unavailable, start_time, end_time)
                VALUES (%s, %s, %s, 1, NULL, NULL)
                ON DUPLICATE KEY UPDATE
                  is_unavailable = 1,
                  start_time = NULL,
                  end_time = NULL
                """,
                (doctor_id, ws, d),
            )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "message": "Días marcados como no disponible."}


@app.get("/api/solicitudes")
@login_required
async def api_solicitudes(request: Request):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, created_at, phone, nombre, dni, obra_social,
                   telefono_contacto, medico, horario_preferido, status
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
        created = r["created_at"]
        if isinstance(created, datetime):
            created_s = created.strftime("%d/%m/%Y %H:%M")
        else:
            created_s = str(created)
        out.append(
            {
                "id": r["id"],
                "created_at": created_s,
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
    return {"solicitudes": out}


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
