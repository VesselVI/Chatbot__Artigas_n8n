"""Seam: which Turnos confirmados are due for Recordatorio automatico (~24h)."""

from __future__ import annotations

from datetime import datetime, timedelta

from recordatorio import is_due_for_reminder, select_due


def _row(**overrides):
    base = {
        "id": 1,
        "status": "confirmed",
        "tipo": "turno",
        "nombre": "Ana Pérez",
        "medico": "Adrian Artigas",
        "appointment_at": datetime(2026, 9, 26, 10, 30),
        "por_orden_de_llegada": 0,
        "reminder_sent_at": None,
        "conversation_id": "42",
    }
    base.update(overrides)
    return base


def test_select_due_includes_confirmed_within_20_to_28h_window():
    now = datetime(2026, 9, 25, 10, 0)
    due = _row(appointment_at=now + timedelta(hours=24))
    early = _row(id=2, appointment_at=now + timedelta(hours=12))
    late = _row(id=3, appointment_at=now + timedelta(hours=36))
    assert select_due([due, early, late], now=now) == [due]


def test_select_due_skips_already_sent_cancelled_pending_and_missing_conversation():
    now = datetime(2026, 9, 25, 10, 0)
    appt = now + timedelta(hours=24)
    rows = [
        _row(id=1, appointment_at=appt, reminder_sent_at=now),
        _row(id=2, appointment_at=appt, status="cancelled"),
        _row(id=3, appointment_at=appt, status="pending"),
        _row(id=4, appointment_at=appt, conversation_id=None),
        _row(id=5, appointment_at=appt, conversation_id=""),
    ]
    assert select_due(rows, now=now) == []


def test_por_orden_due_when_appointment_is_tomorrow_during_morning_hours():
    now = datetime(2026, 9, 25, 9, 30)  # morning ART-style wall time
    tomorrow_midnight = datetime(2026, 9, 26, 0, 0)
    row = _row(
        appointment_at=tomorrow_midnight,
        por_orden_de_llegada=1,
    )
    assert is_due_for_reminder(row, now=now) is True
    night = datetime(2026, 9, 25, 22, 0)
    assert is_due_for_reminder(row, now=night) is False


def test_cron_quiet_hours_skip_all():
    """No madrugada: outside 8–20 local wall time, nothing is due."""
    now = datetime(2026, 9, 25, 3, 0)
    row = _row(appointment_at=now + timedelta(hours=24))
    assert select_due([row], now=now) == []
