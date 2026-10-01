"""Domain tests for Recordatorio desde el panel (ADR-0006)."""

from __future__ import annotations

from datetime import datetime

import pytest

from confirmacion import ConfirmError
from recordatorio_panel import (
    assert_remindable_row,
    can_recordatorio_panel,
    outside_quiet_hours,
    row_already_reminded,
    validate_recordatorio_payload,
)


def test_validate_requires_nombre_medico_and_dia():
    with pytest.raises(ConfirmError) as ei:
        validate_recordatorio_payload({"nombre": "", "medico": "Dr", "appointment_at": "2026-10-02T10:00"})
    assert ei.value.code == "missing_nombre"
    with pytest.raises(ConfirmError) as ei:
        validate_recordatorio_payload({"nombre": "Ana", "medico": "", "appointment_at": "2026-10-02T10:00"})
    assert ei.value.code == "missing_medico"
    with pytest.raises(ConfirmError) as ei:
        validate_recordatorio_payload({"nombre": "Ana", "medico": "Dr"})
    assert ei.value.code == "missing_dia_hora"


def test_validate_accepts_appointment_or_display():
    a = validate_recordatorio_payload(
        {
            "nombre": "Ana",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-02T10:30",
        }
    )
    assert a["nombre"] == "Ana"
    assert a["appointment_at"].hour == 10
    assert a["dia_hora_display"] == ""
    b = validate_recordatorio_payload(
        {
            "nombre": "Ana",
            "medico": "Adrian Artigas",
            "dia_hora_display": "02/10/2026 10:30",
        }
    )
    assert b["appointment_at"] is None
    assert b["dia_hora_display"] == "02/10/2026 10:30"


def test_assert_remindable_confirmed_turno_only():
    ok = {
        "id": 1,
        "tipo": "turno",
        "status": "confirmed",
        "reminder_sent_at": None,
    }
    assert assert_remindable_row(ok) is ok
    assert can_recordatorio_panel(ok) is True
    with pytest.raises(ConfirmError) as ei:
        assert_remindable_row({"id": 2, "tipo": "turno", "status": "pending"})
    assert ei.value.code == "ineligible_recordatorio"
    assert can_recordatorio_panel({"id": 3, "tipo": "estudio", "status": "pending"}) is False


def test_outside_quiet_hours_and_already_reminded():
    assert outside_quiet_hours(datetime(2026, 10, 1, 7, 59)) is True
    assert outside_quiet_hours(datetime(2026, 10, 1, 8, 0)) is False
    assert outside_quiet_hours(datetime(2026, 10, 1, 19, 59)) is False
    assert outside_quiet_hours(datetime(2026, 10, 1, 20, 0)) is True
    assert row_already_reminded({"reminder_sent_at": None}) is False
    assert row_already_reminded({"reminder_sent_at": datetime(2026, 10, 1, 9, 0)}) is True
