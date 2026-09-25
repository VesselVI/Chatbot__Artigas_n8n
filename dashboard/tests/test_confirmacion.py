"""Unit tests for Confirmación desde el panel domain rules."""

from datetime import datetime

import pytest

from confirmacion import (
    ConfirmError,
    assert_confirmable,
    can_mark_confirmed,
    parse_appointment_at,
    status_badge_label,
    validate_confirm_payload,
)


def test_status_badge_confirmado_for_turno():
    assert status_badge_label("confirmed", "turno") == "Confirmado"


def test_status_badge_reprogramado_for_reprogramar():
    assert status_badge_label("confirmed", "reprogramar") == "Reprogramado"


def test_status_badge_none_when_pending():
    assert status_badge_label("pending", "turno") is None


def test_parse_appointment_at_iso():
    assert parse_appointment_at("2026-09-22T10:30") == datetime(2026, 9, 22, 10, 30)


def test_parse_appointment_at_missing():
    with pytest.raises(ConfirmError) as ei:
        parse_appointment_at("")
    assert ei.value.code == "missing_appointment_at"


def test_validate_confirm_payload_ok_empty_nota():
    out = validate_confirm_payload(
        {
            "appointment_at": "2026-09-22 15:00",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "  ",
        }
    )
    assert out["nombre"] == "Ana Pérez"
    assert out["medico"] == "Adrian Artigas"
    assert out["nota_paciente"] == ""
    assert out["appointment_at"] == datetime(2026, 9, 22, 15, 0)


def test_validate_confirm_payload_requires_nombre():
    with pytest.raises(ConfirmError) as ei:
        validate_confirm_payload(
            {"appointment_at": "2026-09-22 15:00", "nombre": "", "medico": "X"}
        )
    assert ei.value.code == "missing_nombre"


def test_assert_confirmable_rejects_cancelar():
    with pytest.raises(ConfirmError) as ei:
        assert_confirmable({"id": 1, "tipo": "cancelar", "status": "pending"})
    assert ei.value.code == "ineligible_tipo"


def test_assert_confirmable_rejects_reprogramar():
    """#8: Confirmación is turno-only; reprogramar uses Reprogramación desde el panel."""
    with pytest.raises(ConfirmError) as ei:
        assert_confirmable({"id": 1, "tipo": "reprogramar", "status": "pending"})
    assert ei.value.code == "ineligible_tipo"


def test_assert_confirmable_allows_turno_pending():
    row = assert_confirmable({"id": 1, "tipo": "turno", "status": "pending"})
    assert row["id"] == 1


def test_assert_confirmable_rejects_already_confirmed():
    with pytest.raises(ConfirmError) as ei:
        assert_confirmable({"id": 1, "tipo": "turno", "status": "confirmed"})
    assert ei.value.code == "already_confirmed"


def test_can_mark_confirmed_pending_turno_only():
    assert can_mark_confirmed({"id": 1, "tipo": "turno", "status": "pending"}) is True
    assert can_mark_confirmed({"id": 2, "tipo": "turno", "status": "confirmed"}) is False
    assert can_mark_confirmed({"id": 3, "tipo": "reprogramar", "status": "pending"}) is False


def test_validate_confirm_payload_por_orden_de_llegada():
    out = validate_confirm_payload(
        {
            "por_orden_de_llegada": True,
            "appointment_date": "2026-09-23",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
        }
    )
    assert out["por_orden_de_llegada"] is True
    assert out["appointment_at"] == datetime(2026, 9, 23, 0, 0)
    assert out["nota_paciente"] == ""


def test_validate_confirm_payload_orden_requires_date():
    with pytest.raises(ConfirmError) as ei:
        validate_confirm_payload(
            {
                "scheduling_mode": "por_orden_de_llegada",
                "nombre": "Ana",
                "medico": "X",
            }
        )
    assert ei.value.code == "missing_appointment_date"
