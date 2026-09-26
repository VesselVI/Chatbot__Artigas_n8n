"""Respuesta a consulta desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from typing import Any

from confirmacion import (
    CONTACTADO_STATUS,
    PENDING_STATUS,
    ConfirmError,
    normalize_tipo,
)

RESPUESTA_CONSULTA_TIPOS = frozenset({"estudio", "solicitud"})
RESPUESTA_TEMPLATE = "respuesta_consulta"

# Statuses that still allow Responder consulta / Abrir Chat → Contactado.
_OPEN_STATUSES = frozenset({PENDING_STATUS, CONTACTADO_STATUS})


class RespuestaConsultaError(ConfirmError):
    """Invalid Respuesta a consulta payload or solicitud state."""


def mensaje_respuesta_consulta(nombre: Any) -> str:
    """Patient-facing ack (same free-form and utility wording)."""
    name = str(nombre or "").strip() or "paciente"
    return (
        f"Hola {name}, recibimos tu consulta. "
        "Te respondemos por este chat en breve."
    )


def _assert_consulta_row(
    row: dict[str, Any] | None,
    *,
    verb: str,
) -> dict[str, Any]:
    if not row:
        raise RespuestaConsultaError("Solicitud no encontrada.", code="not_found")
    tipo = normalize_tipo(row.get("tipo"))
    if tipo not in RESPUESTA_CONSULTA_TIPOS:
        raise RespuestaConsultaError(
            f"No se puede {verb} una solicitud de tipo «{tipo}».",
            code="ineligible_tipo",
        )
    status = str(row.get("status") or PENDING_STATUS).strip().lower()
    if status not in _OPEN_STATUSES:
        raise RespuestaConsultaError(
            f"Estado «{status}» no admite {verb}.",
            code="invalid_status",
        )
    cid = str(row.get("conversation_id") or "").strip()
    if not cid:
        raise RespuestaConsultaError(
            "Solicitud sin conversation_id.",
            code="missing_conversation",
        )
    return row


def assert_responder_consulta(row: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure the solicitud may receive Respuesta a consulta desde el panel."""
    return _assert_consulta_row(row, verb="responder")


def can_responder_consulta(row: dict[str, Any]) -> bool:
    try:
        assert_responder_consulta(row)
        return True
    except RespuestaConsultaError:
        return False


def assert_mark_contactado(row: dict[str, Any] | None) -> dict[str, Any]:
    """Abrir Chat may set Contactado for estudio/solicitud with a conversation."""
    return _assert_consulta_row(row, verb="marcar Contactado")


def can_mark_contactado(row: dict[str, Any]) -> bool:
    try:
        assert_mark_contactado(row)
        return True
    except RespuestaConsultaError:
        return False
