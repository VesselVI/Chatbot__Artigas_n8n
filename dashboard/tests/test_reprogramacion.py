"""Unit tests for Reprogramación desde el panel domain rules (#9)."""

from datetime import datetime

import pytest

from confirmacion import ConfirmError
from reprogramacion import (
    assert_reprogramable,
    can_reprogram,
    validate_reprogram_payload,
)


def test_validate_reprogram_payload_ok_no_nota_field():
    out = validate_reprogram_payload(
        {
            "appointment_at": "2026-09-25T16:00",
            "nombre": "Luis Gómez",
            "medico": "Adrian Artigas",
            "nota_paciente": "should be ignored",
        }
    )
    assert out["nombre"] == "Luis Gómez"
    assert out["medico"] == "Adrian Artigas"
    assert out["appointment_at"] == datetime(2026, 9, 25, 16, 0)
    assert out["por_orden_de_llegada"] is False
    assert "nota_paciente" not in out


def test_validate_reprogram_payload_por_orden():
    out = validate_reprogram_payload(
        {
            "scheduling_mode": "por_orden_de_llegada",
            "appointment_date": "2026-09-26",
            "nombre": "Ana",
            "medico": "Adrian Artigas",
        }
    )
    assert out["por_orden_de_llegada"] is True
    assert out["appointment_at"] == datetime(2026, 9, 26, 0, 0)


def test_assert_reprogramable_pending_reprogramar():
    row = assert_reprogramable({"id": 1, "tipo": "reprogramar", "status": "pending"})
    assert row["id"] == 1


def test_assert_reprogramable_confirmed_turno():
    row = assert_reprogramable({"id": 2, "tipo": "turno", "status": "confirmed"})
    assert row["id"] == 2


def test_assert_reprogramable_confirmed_reprogramar():
    row = assert_reprogramable({"id": 3, "tipo": "reprogramar", "status": "confirmed"})
    assert row["id"] == 3


def test_assert_reprogramable_rejects_pending_turno():
    with pytest.raises(ConfirmError) as ei:
        assert_reprogramable({"id": 1, "tipo": "turno", "status": "pending"})
    assert ei.value.code == "use_confirm"


def test_assert_reprogramable_rejects_cancelar():
    with pytest.raises(ConfirmError) as ei:
        assert_reprogramable({"id": 1, "tipo": "cancelar", "status": "pending"})
    assert ei.value.code == "ineligible_reprogram"


def test_can_reprogram_flags():
    assert can_reprogram({"tipo": "reprogramar", "status": "pending"}) is True
    assert can_reprogram({"tipo": "turno", "status": "confirmed"}) is True
    assert can_reprogram({"tipo": "turno", "status": "pending"}) is False
