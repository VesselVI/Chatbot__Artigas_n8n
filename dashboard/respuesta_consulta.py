"""Respuesta a consulta desde el panel — domain rules (no I/O)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from confirmacion import (
    CONTACTADO_STATUS,
    PENDING_STATUS,
    ConfirmError,
    normalize_tipo,
)

RESPUESTA_CONSULTA_TIPOS = frozenset({"estudio", "pregunta"})
RESPUESTA_TEMPLATE = "respuesta_consulta"

# Meta customer-service window length used to gate free-form Responder consulta.
CONSULTA_WINDOW = timedelta(hours=24)

# Statuses that still allow Responder consulta / Abrir Chat → Contactado.
_OPEN_STATUSES = frozenset({PENDING_STATUS, CONTACTADO_STATUS})

_MAX_MENSAJE_LEN = 4000


class RespuestaConsultaError(ConfirmError):
    """Invalid Respuesta a consulta payload or solicitud state."""


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def consulta_window_open(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """
    True when Meta’s ~24h customer-service window is still likely open.

    Heuristic: solicitud created_at (patient message that opened the row)
    within CONSULTA_WINDOW of now. No Chatwoot round-trip on list loads.
    """
    created = _as_dt(row.get("created_at"))
    if created is None:
        return False
    clock = now or datetime.now()
    if clock.tzinfo is not None:
        clock = clock.replace(tzinfo=None)
    return (clock - created) <= CONSULTA_WINDOW


def assert_mensaje_respuesta(mensaje: Any) -> str:
    """Require non-empty free-form patient reply."""
    text = str(mensaje or "").strip()
    if not text:
        raise RespuestaConsultaError(
            "Escribí la respuesta al paciente.",
            code="empty_message",
        )
    if len(text) > _MAX_MENSAJE_LEN:
        raise RespuestaConsultaError(
            "La respuesta es demasiado larga.",
            code="message_too_long",
        )
    return text


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


def assert_responder_consulta(
    row: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ensure the solicitud may receive Respuesta a consulta (free-form, window open)."""
    row = _assert_consulta_row(row, verb="responder")
    if not consulta_window_open(row, now=now):
        raise RespuestaConsultaError(
            "La ventana de 24 h está cerrada. Respondé desde Chatwoot con plantilla "
            "o esperá un mensaje del paciente.",
            code="window_closed",
        )
    return row


def can_responder_consulta(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    try:
        assert_responder_consulta(row, now=now)
        return True
    except RespuestaConsultaError:
        return False


def assert_mark_contactado(row: dict[str, Any] | None) -> dict[str, Any]:
    """Abrir Chat may set Contactado for estudio/pregunta with a conversation."""
    return _assert_consulta_row(row, verb="marcar Contactado")


def can_mark_contactado(row: dict[str, Any]) -> bool:
    try:
        assert_mark_contactado(row)
        return True
    except RespuestaConsultaError:
        return False
