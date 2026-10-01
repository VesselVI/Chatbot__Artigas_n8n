"""Unit tests for Respuesta a consulta desde el panel domain rules."""

from datetime import datetime, timedelta

from confirmacion import status_badge_label
from respuesta_consulta import (
    RespuestaConsultaError,
    assert_mensaje_respuesta,
    assert_responder_consulta,
    can_mark_contactado,
    can_responder_consulta,
    consulta_window_open,
)


NOW = datetime(2026, 10, 1, 15, 0, 0)


def _consulta(**kwargs):
    base = {
        "id": 1,
        "tipo": "estudio",
        "status": "pending",
        "conversation_id": "42",
        "created_at": NOW - timedelta(hours=2),
    }
    base.update(kwargs)
    return base


def test_status_badge_contactado():
    assert status_badge_label("contactado", "estudio") == "Contactado"
    assert status_badge_label("contactado", "pregunta") == "Contactado"
    assert status_badge_label("contactado", "solicitud") == "Contactado"
    assert status_badge_label("contactado", "turno") == "Contactado"


def test_consulta_window_open_within_24h():
    assert consulta_window_open(_consulta(created_at=NOW - timedelta(hours=23)), now=NOW)
    assert not consulta_window_open(
        _consulta(created_at=NOW - timedelta(hours=25)), now=NOW
    )


def test_assert_mensaje_respuesta_requires_text():
    assert assert_mensaje_respuesta("  Sí, el OCT sale 40 mil.  ") == (
        "Sí, el OCT sale 40 mil."
    )
    try:
        assert_mensaje_respuesta("   ")
        assert False, "expected RespuestaConsultaError"
    except RespuestaConsultaError as e:
        assert e.code == "empty_message"


def test_can_responder_estudio_and_pregunta_pending():
    assert can_responder_consulta(_consulta(tipo="estudio"), now=NOW)
    assert can_responder_consulta(_consulta(id=2, tipo="pregunta"), now=NOW)
    # Legacy DB value still maps via normalize_tipo
    assert can_responder_consulta(_consulta(id=3, tipo="solicitud"), now=NOW)


def test_can_responder_when_already_contactado():
    assert can_responder_consulta(
        _consulta(status="contactado"), now=NOW
    )


def test_cannot_responder_when_window_closed():
    assert not can_responder_consulta(
        _consulta(created_at=NOW - timedelta(hours=30)), now=NOW
    )
    try:
        assert_responder_consulta(
            _consulta(created_at=NOW - timedelta(hours=30)), now=NOW
        )
        assert False, "expected RespuestaConsultaError"
    except RespuestaConsultaError as e:
        assert e.code == "window_closed"


def test_cannot_responder_turno_or_without_conversation():
    assert not can_responder_consulta(
        _consulta(tipo="turno"), now=NOW
    )
    assert not can_responder_consulta(
        _consulta(conversation_id=None), now=NOW
    )
    assert not can_responder_consulta(
        _consulta(status="confirmed"), now=NOW
    )


def test_can_mark_contactado_estudio_solicitud_with_chat():
    assert can_mark_contactado(
        {"id": 1, "tipo": "estudio", "status": "pending", "conversation_id": "9"}
    )
    assert can_mark_contactado(
        {"id": 2, "tipo": "solicitud", "status": "contactado", "conversation_id": "9"}
    )
    assert not can_mark_contactado(
        {"id": 3, "tipo": "turno", "status": "pending", "conversation_id": "9"}
    )
    assert not can_mark_contactado(
        {"id": 4, "tipo": "estudio", "status": "pending", "conversation_id": ""}
    )


def test_assert_responder_rejects_turno():
    try:
        assert_responder_consulta(_consulta(tipo="turno"), now=NOW)
        assert False, "expected RespuestaConsultaError"
    except RespuestaConsultaError as e:
        assert e.code == "ineligible_tipo"
