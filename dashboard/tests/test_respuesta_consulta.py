"""Unit tests for Respuesta a consulta desde el panel domain rules."""

from confirmacion import status_badge_label
from respuesta_consulta import (
    RespuestaConsultaError,
    assert_responder_consulta,
    can_mark_contactado,
    can_responder_consulta,
    mensaje_respuesta_consulta,
)


def test_status_badge_contactado():
    assert status_badge_label("contactado", "estudio") == "Contactado"
    assert status_badge_label("contactado", "solicitud") == "Contactado"
    assert status_badge_label("contactado", "turno") == "Contactado"


def test_mensaje_respuesta_consulta_copy():
    assert mensaje_respuesta_consulta("Ana Pérez") == (
        "Hola Ana Pérez, recibimos tu consulta. "
        "Te respondemos por este chat en breve."
    )


def test_mensaje_respuesta_consulta_fallback_nombre():
    assert "Hola" in mensaje_respuesta_consulta("")
    assert "recibimos tu consulta" in mensaje_respuesta_consulta("  ")


def test_can_responder_estudio_and_solicitud_pending():
    assert can_responder_consulta(
        {"id": 1, "tipo": "estudio", "status": "pending", "conversation_id": "42"}
    )
    assert can_responder_consulta(
        {"id": 2, "tipo": "solicitud", "status": "pending", "conversation_id": "42"}
    )


def test_can_responder_when_already_contactado():
    assert can_responder_consulta(
        {"id": 1, "tipo": "estudio", "status": "contactado", "conversation_id": "42"}
    )


def test_cannot_responder_turno_or_without_conversation():
    assert not can_responder_consulta(
        {"id": 1, "tipo": "turno", "status": "pending", "conversation_id": "42"}
    )
    assert not can_responder_consulta(
        {"id": 2, "tipo": "estudio", "status": "pending", "conversation_id": None}
    )
    assert not can_responder_consulta(
        {"id": 3, "tipo": "estudio", "status": "confirmed", "conversation_id": "42"}
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
        assert_responder_consulta(
            {"id": 1, "tipo": "turno", "status": "pending", "conversation_id": "1"}
        )
        assert False, "expected RespuestaConsultaError"
    except RespuestaConsultaError as e:
        assert e.code == "ineligible_tipo"
