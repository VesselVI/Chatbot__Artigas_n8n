"""Confirmación desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

CONFIRMABLE_TIPOS = frozenset({"turno", "reprogramar"})
CONFIRMED_STATUS = "confirmed"
PENDING_STATUS = "pending"


class ConfirmError(ValueError):
    """Invalid confirm payload or solicitud state."""

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def normalize_tipo(value: Any) -> str:
    tipo = str(value or "turno").strip().lower()
    if tipo not in ("turno", "cancelar", "estudio", "reprogramar", "solicitud"):
        return "turno"
    return tipo


def status_badge_label(status: Any, tipo: Any) -> str | None:
    """UI badge for a confirmed solicitud; None if still pending / other."""
    if str(status or "").strip().lower() != CONFIRMED_STATUS:
        return None
    if normalize_tipo(tipo) == "reprogramar":
        return "Reprogramado"
    return "Confirmado"


def parse_appointment_at(value: Any) -> datetime:
    """Accept ISO datetime from the panel (local wall time, no tz required)."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value or "").strip()
    if not s:
        raise ConfirmError("Falta Día/hora del turno.", code="missing_appointment_at")
    s = s.replace("Z", "").replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ConfirmError("Día/hora del turno inválido.", code="invalid_appointment_at")


def validate_confirm_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize body for Confirmación desde el panel. Raises ConfirmError."""
    if not isinstance(body, dict):
        raise ConfirmError("Cuerpo inválido.", code="invalid_body")
    appointment_at = parse_appointment_at(body.get("appointment_at") or body.get("dia_hora"))
    nombre = str(body.get("nombre") or "").strip()
    medico = str(body.get("medico") or "").strip()
    if not nombre:
        raise ConfirmError("Falta el nombre del paciente.", code="missing_nombre")
    if not medico:
        raise ConfirmError("Falta el médico.", code="missing_medico")
    nota = str(body.get("nota_paciente") or body.get("nota") or "").strip()
    return {
        "appointment_at": appointment_at,
        "nombre": nombre,
        "medico": medico,
        "nota_paciente": nota,
    }


def assert_confirmable(row: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure the solicitud row may be confirmed. Returns the row."""
    if not row:
        raise ConfirmError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    if tipo not in CONFIRMABLE_TIPOS:
        raise ConfirmError(
            f"No se puede confirmar una solicitud de tipo «{tipo}».",
            code="ineligible_tipo",
        )
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status == CONFIRMED_STATUS:
        # Ticket #2: first confirm only; edit path is a later ticket.
        raise ConfirmError("La solicitud ya está confirmada.", code="already_confirmed")
    return row
