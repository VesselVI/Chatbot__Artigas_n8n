"""Cancelación desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from typing import Any

from confirmacion import (
    CANCELLED_STATUS,
    CONFIRMED_STATUS,
    ConfirmError,
    PENDING_STATUS,
    normalize_tipo,
)


CANCEL_TEMPLATE = "cancelacion_turno"


def validate_cancel_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize body for Cancelación desde el panel. No Día/hora, no Nota."""
    if not isinstance(body, dict):
        raise ConfirmError("Cuerpo inválido.", code="invalid_body")
    nombre = str(body.get("nombre") or "").strip()
    if not nombre:
        raise ConfirmError("Falta el nombre del paciente.", code="missing_nombre")
    return {"nombre": nombre}


def assert_cancelable(row: dict[str, Any] | None) -> dict[str, Any]:
    """
    Row may be cancelled when:
    - confirmed tipo=turno or reprogramar (after Turno confirmado / reprogram), or
    - pending tipo=cancelar (patient-requested cancel notify).
    """
    if not row:
        raise ConfirmError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status == CANCELLED_STATUS:
        raise ConfirmError(
            "La solicitud ya está cancelada.",
            code="already_cancelled",
        )
    if status == PENDING_STATUS and tipo == "cancelar":
        return row
    if status == CONFIRMED_STATUS and tipo in ("turno", "reprogramar"):
        return row
    raise ConfirmError(
        f"No se puede cancelar una solicitud «{tipo}» en estado «{status}».",
        code="ineligible_cancel",
    )


def can_cancel(row: dict[str, Any]) -> bool:
    try:
        assert_cancelable(row)
        return True
    except ConfirmError:
        return False
