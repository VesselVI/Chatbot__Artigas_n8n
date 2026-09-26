"""Recordatorio automatico (~24h) — domain rules (no I/O)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from confirmacion import CONFIRMED_STATUS, normalize_tipo
from mensajes import format_dia_hora_display

REMINDER_TEMPLATE = "recordatorio_turno"
# Quiet hours: do not send outside clinic-ish daytime (local wall time).
SEND_HOUR_START = 8
SEND_HOUR_END = 20  # exclusive upper bound for "during day"
# Timed turnos: due when appointment is ~24h away.
WINDOW_HOURS_MIN = 20
WINDOW_HOURS_MAX = 28
# Por orden de llegada (midnight appointment_at): send morning of the day before.
POR_ORDEN_MORNING_END = 12


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    s = str(value).strip().replace("Z", "").replace("T", " ")[:19]
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "si", "sí", "on"}


def is_send_window(now: datetime) -> bool:
    return SEND_HOUR_START <= now.hour < SEND_HOUR_END


def is_due_for_reminder(row: dict[str, Any], *, now: datetime) -> bool:
    """Whether a solicitud row should receive a Recordatorio automatico at `now`."""
    if not is_send_window(now):
        return False
    if str(row.get("status") or "").strip().lower() != CONFIRMED_STATUS:
        return False
    if _as_dt(row.get("reminder_sent_at")) is not None:
        return False
    if not str(row.get("conversation_id") or "").strip():
        return False
    appointment_at = _as_dt(row.get("appointment_at"))
    if appointment_at is None or appointment_at <= now:
        return False

    if _truthy(row.get("por_orden_de_llegada")):
        tomorrow = (now.date() + timedelta(days=1))
        return (
            appointment_at.date() == tomorrow
            and SEND_HOUR_START <= now.hour < POR_ORDEN_MORNING_END
        )

    delta = appointment_at - now
    hours = delta.total_seconds() / 3600.0
    return WINDOW_HOURS_MIN <= hours <= WINDOW_HOURS_MAX


def select_due(
    rows: list[dict[str, Any]], *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Filter solicitudes that are due for a reminder at `now` (default: wall clock)."""
    clock = now if now is not None else datetime.now()
    return [r for r in rows if is_due_for_reminder(r, now=clock)]


def body_params_for_row(row: dict[str, Any]) -> list[str]:
    """Numbered Meta body vars: {{1}} nombre, {{2}} día/hora, {{3}} médico."""
    nombre = str(row.get("nombre") or "").strip() or "Paciente"
    medico = str(row.get("medico") or "").strip() or "la clínica"
    por_orden = _truthy(row.get("por_orden_de_llegada"))
    dia = format_dia_hora_display(
        row.get("appointment_at"), por_orden_de_llegada=por_orden
    )
    return [nombre, dia, medico]


def reminder_eligible_tipos() -> frozenset[str]:
    # Confirmed turnos and reprogramaciones both have a future appointment_at.
    return frozenset({"turno", "reprogramar"})


def assert_reminder_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Light guard for send path (already filtered by select_due in the job)."""
    if not row:
        raise ValueError("Solicitud no encontrada")
    if normalize_tipo(row.get("tipo")) not in reminder_eligible_tipos():
        raise ValueError("Tipo no admite recordatorio")
    return row
