"""Recordatorio desde el panel — domain rules (no I/O). ADR-0006."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from confirmacion import (
    CANCELLED_STATUS,
    CONFIRMED_STATUS,
    ConfirmError,
    PENDING_STATUS,
    normalize_tipo,
    parse_appointment_at,
)
from recordatorio import (
    REMINDER_TEMPLATE,
    SEND_HOUR_END,
    SEND_HOUR_START,
    reminder_eligible_tipos,
)

# Distinct from generic "utility" so Reenviar knows to resend recordatorio_turno.
REMINDER_PANEL_CHANNEL = "recordatorio"


def outside_quiet_hours(now: datetime | None = None) -> bool:
    """True when wall clock is outside Recordatorio automatico quiet hours (8–20)."""
    clock = now if now is not None else datetime.now()
    return not (SEND_HOUR_START <= clock.hour < SEND_HOUR_END)


def validate_recordatorio_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize body for Recordatorio desde el panel. Always requires template slots."""
    if not isinstance(body, dict):
        raise ConfirmError("Cuerpo inválido.", code="invalid_body")
    nombre = str(body.get("nombre") or "").strip()
    medico = str(body.get("medico") or "").strip()
    if not nombre:
        raise ConfirmError("Falta el nombre del paciente.", code="missing_nombre")
    if not medico:
        raise ConfirmError("Falta el médico.", code="missing_medico")
    # Prefer structured appointment_at; allow preformatted dia_hora_display for cold edits.
    raw_display = str(body.get("dia_hora_display") or body.get("dia_hora") or "").strip()
    appointment_at = None
    raw_appt = body.get("appointment_at")
    if raw_appt not in (None, ""):
        appointment_at = parse_appointment_at(raw_appt)
    if not raw_display and appointment_at is None:
        raise ConfirmError(
            "Falta el día y hora del turno para la plantilla.",
            code="missing_dia_hora",
        )
    return {
        "nombre": nombre,
        "medico": medico,
        "appointment_at": appointment_at,
        "dia_hora_display": raw_display,
        "confirm_resend": bool(body.get("confirm_resend")),
    }


def assert_remindable_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """
    Row may receive Recordatorio desde el panel when confirmed turno/reprogramar.
    (Pending turnos use Confirmar; other tipos are ineligible for row update.)
    """
    if not row:
        raise ConfirmError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status == CANCELLED_STATUS:
        raise ConfirmError(
            "No se puede recordar una solicitud cancelada.",
            code="ineligible_recordatorio",
        )
    if status == CONFIRMED_STATUS and tipo in reminder_eligible_tipos():
        return row
    raise ConfirmError(
        f"No se puede recordar una solicitud «{tipo}» en estado «{status}».",
        code="ineligible_recordatorio",
    )


def can_recordatorio_panel(row: dict[str, Any]) -> bool:
    try:
        assert_remindable_row(row)
        return True
    except ConfirmError:
        return False


def row_already_reminded(row: dict[str, Any]) -> bool:
    val = row.get("reminder_sent_at")
    if val is None:
        return False
    if isinstance(val, datetime):
        return True
    return bool(str(val).strip())


__all__ = [
    "REMINDER_PANEL_CHANNEL",
    "REMINDER_TEMPLATE",
    "assert_remindable_row",
    "can_recordatorio_panel",
    "outside_quiet_hours",
    "row_already_reminded",
    "validate_recordatorio_payload",
]
