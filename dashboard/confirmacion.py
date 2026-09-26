"""Confirmación desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Confirmación desde el panel: first-time turno only (ADR-0005 / #8).
# Reprogramación uses Reprogramación desde el panel, not Confirmar.
CONFIRMABLE_TIPOS = frozenset({"turno"})
CONFIRMED_STATUS = "confirmed"
PENDING_STATUS = "pending"
CANCELLED_STATUS = "cancelled"
CONTACTADO_STATUS = "contactado"


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
    """UI badge for confirmed / cancelled / contactado; None if still pending / other."""
    st = str(status or "").strip().lower()
    if st == CANCELLED_STATUS:
        return "Cancelado"
    if st == CONTACTADO_STATUS:
        return "Contactado"
    if st != CONFIRMED_STATUS:
        return None
    if normalize_tipo(tipo) == "reprogramar":
        return "Reprogramado"
    return "Confirmado"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "si", "sí", "on"}


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


def parse_appointment_date(value: Any) -> datetime:
    """Accept YYYY-MM-DD (or datetime) and store as midnight local wall time."""
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    s = str(value or "").strip()
    if not s:
        raise ConfirmError("Falta el día del turno.", code="missing_appointment_date")
    s = s.replace("Z", "").replace("T", " ")[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError as exc:
        raise ConfirmError(
            "Día del turno inválido.", code="invalid_appointment_date"
        ) from exc


def is_por_orden_de_llegada(body: dict[str, Any]) -> bool:
    mode = str(body.get("scheduling_mode") or "").strip().lower()
    if mode in ("por_orden_de_llegada", "orden"):
        return True
    if mode in ("hora_especifica", "hora"):
        return False
    return _truthy(body.get("por_orden_de_llegada"))


def validate_confirm_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize body for Confirmación desde el panel. Raises ConfirmError."""
    if not isinstance(body, dict):
        raise ConfirmError("Cuerpo inválido.", code="invalid_body")
    por_orden = is_por_orden_de_llegada(body)
    if por_orden:
        raw = (
            body.get("appointment_date")
            or body.get("appointment_at")
            or body.get("dia_hora")
        )
        appointment_at = parse_appointment_date(raw)
    else:
        appointment_at = parse_appointment_at(
            body.get("appointment_at") or body.get("dia_hora")
        )
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
        "por_orden_de_llegada": por_orden,
    }


def assert_confirmable(
    row: dict[str, Any] | None, *, allow_confirmed: bool = False
) -> dict[str, Any]:
    """Ensure the solicitud row may be confirmed (or edited if allow_confirmed)."""
    if not row:
        raise ConfirmError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    if tipo not in CONFIRMABLE_TIPOS:
        raise ConfirmError(
            f"No se puede confirmar una solicitud de tipo «{tipo}».",
            code="ineligible_tipo",
        )
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status == CONFIRMED_STATUS and not allow_confirmed:
        raise ConfirmError("La solicitud ya está confirmada.", code="already_confirmed")
    if status not in (PENDING_STATUS, CONFIRMED_STATUS):
        raise ConfirmError(
            f"Estado «{status}» no admite confirmación.",
            code="invalid_status",
        )
    return row


def can_mark_confirmed(row: dict[str, Any]) -> bool:
    """Pending turno may be marked Confirmado without sending WhatsApp."""
    try:
        assert_confirmable(row, allow_confirmed=False)
        return True
    except ConfirmError:
        return False
