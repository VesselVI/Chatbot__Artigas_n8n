"""Reprogramación desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from typing import Any

from confirmacion import (
    CONFIRMED_STATUS,
    ConfirmError,
    PENDING_STATUS,
    is_por_orden_de_llegada,
    normalize_tipo,
    parse_appointment_at,
    parse_appointment_date,
)

# Pending patient reprogram requests + confirmed turnos (ADR-0005 / #9).
REPROGRAM_TEMPLATE = "confirmacion_reprogramacion"


def validate_reprogram_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize body for Reprogramación desde el panel. No Nota al paciente."""
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
    return {
        "appointment_at": appointment_at,
        "nombre": nombre,
        "medico": medico,
        "por_orden_de_llegada": por_orden,
    }


def assert_reprogramable(row: dict[str, Any] | None) -> dict[str, Any]:
    """
    Row may be reprogrammed when:
    - pending tipo=reprogramar, or
    - confirmed tipo=turno or reprogramar (after Turno confirmado / prior reprogram).
    """
    if not row:
        raise ConfirmError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status == PENDING_STATUS and tipo == "reprogramar":
        return row
    if status == CONFIRMED_STATUS and tipo in ("turno", "reprogramar"):
        return row
    if status == PENDING_STATUS and tipo == "turno":
        raise ConfirmError(
            "Usá Confirmar para un turno pendiente.",
            code="use_confirm",
        )
    raise ConfirmError(
        f"No se puede reprogramar una solicitud «{tipo}» en estado «{status}».",
        code="ineligible_reprogram",
    )


def can_reprogram(row: dict[str, Any]) -> bool:
    try:
        assert_reprogramable(row)
        return True
    except ConfirmError:
        return False
