"""Unit tests for Cancelación desde el panel domain (#12)."""

import pytest

from cancelacion import assert_cancelable, can_cancel, validate_cancel_payload
from confirmacion import ConfirmError, status_badge_label


def test_validate_cancel_requires_nombre():
    with pytest.raises(ConfirmError) as ei:
        validate_cancel_payload({"nombre": "  "})
    assert ei.value.code == "missing_nombre"


def test_validate_cancel_ok():
    assert validate_cancel_payload({"nombre": "Ana Pérez"}) == {"nombre": "Ana Pérez"}


def test_assert_cancelable_confirmed_turno():
    row = assert_cancelable({"id": 1, "tipo": "turno", "status": "confirmed"})
    assert row["id"] == 1


def test_assert_cancelable_confirmed_reprogramar():
    assert_cancelable({"id": 2, "tipo": "reprogramar", "status": "confirmed"})


def test_assert_cancelable_pending_cancelar():
    assert_cancelable({"id": 3, "tipo": "cancelar", "status": "pending"})


def test_assert_cancelable_rejects_pending_turno():
    with pytest.raises(ConfirmError) as ei:
        assert_cancelable({"id": 1, "tipo": "turno", "status": "pending"})
    assert ei.value.code == "ineligible_cancel"


def test_assert_cancelable_rejects_already_cancelled():
    with pytest.raises(ConfirmError) as ei:
        assert_cancelable({"id": 1, "tipo": "turno", "status": "cancelled"})
    assert ei.value.code == "already_cancelled"


def test_can_cancel_flags():
    assert can_cancel({"tipo": "turno", "status": "confirmed"}) is True
    assert can_cancel({"tipo": "turno", "status": "pending"}) is False
    assert can_cancel({"tipo": "turno", "status": "cancelled"}) is False


def test_status_badge_cancelado():
    assert status_badge_label("cancelled", "turno") == "Cancelado"
    assert status_badge_label("cancelled", "reprogramar") == "Cancelado"
