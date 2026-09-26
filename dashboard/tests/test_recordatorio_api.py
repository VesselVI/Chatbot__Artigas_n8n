"""HTTP seam: POST /api/internal/recordatorios (n8n cron → dashboard)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DASHBOARD_USERNAME", "testuser")
os.environ.setdefault("DASHBOARD_PASSWORD", "testpass")
os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret")
os.environ.setdefault("DASHBOARD_CRON_SECRET", "cron-secret-test")

import app as dash_app  # noqa: E402
from chatwoot_send import SendResult  # noqa: E402


def _row(**overrides):
    now = datetime(2026, 9, 25, 10, 0)
    base = {
        "id": 1,
        "created_at": now,
        "phone": "5491112345678",
        "nombre": "Ana Pérez",
        "dni": "30111222",
        "obra_social": "OSDE",
        "telefono_contacto": "5491112345678",
        "medico": "Adrian Artigas",
        "horario_preferido": "-",
        "status": "confirmed",
        "conversation_id": "42",
        "tipo": "turno",
        "appointment_at": now + timedelta(hours=24),
        "por_orden_de_llegada": 0,
        "nota_paciente": "",
        "whatsapp_send_status": "ok",
        "whatsapp_send_channel": "utility",
        "whatsapp_nota_omitted": 0,
        "reminder_sent_at": None,
    }
    base.update(overrides)
    return base


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = {r["id"]: dict(r) for r in rows}

    def list_candidates(self) -> list[dict[str, Any]]:
        return list(self.rows.values())

    def mark_reminder(self, sid: int, sent_at: datetime) -> None:
        self.rows[sid]["reminder_sent_at"] = sent_at


@pytest.fixture
def store():
    base = datetime(2026, 9, 25, 10, 0)
    return FakeStore(
        [
            _row(id=1, appointment_at=base + timedelta(hours=24)),
            _row(id=2, appointment_at=base + timedelta(hours=12)),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CRON_SECRET", "cron-secret-test")
    monkeypatch.setattr(dash_app, "list_reminder_candidates", store.list_candidates)
    monkeypatch.setattr(dash_app, "mark_reminder_sent", store.mark_reminder)
    return TestClient(dash_app.app)


def test_recordatorios_rejects_missing_secret(client):
    r = client.post("/api/internal/recordatorios")
    assert r.status_code == 401


def test_recordatorios_sends_due_and_marks_sent(client, store, monkeypatch):
    fixed_now = datetime(2026, 9, 25, 10, 0)
    sent: list[dict[str, Any]] = []

    def fake_send(conversation_id, *, nombre, medico, dia_hora_display, opener=None, **_):
        sent.append({"conversation_id": str(conversation_id), "nombre": nombre})
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_recordatorio", fake_send)

    original = dash_app.run_recordatorios_job

    def wrapped():
        return original(now=fixed_now)

    monkeypatch.setattr(dash_app, "run_recordatorios_job", wrapped)

    r = client.post(
        "/api/internal/recordatorios",
        headers={"X-Cron-Secret": "cron-secret-test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] == 1
    assert body["failed"] == 0
    assert sent == [{"conversation_id": "42", "nombre": "Ana Pérez"}]
    assert store.rows[1]["reminder_sent_at"] == fixed_now
    assert store.rows[2]["reminder_sent_at"] is None


def test_recordatorios_idempotent_second_run(client, store, monkeypatch):
    fixed_now = datetime(2026, 9, 25, 10, 0)
    store.rows[1]["reminder_sent_at"] = fixed_now
    sent: list[Any] = []

    def fake_send(*_a, **_k):
        sent.append(1)
        return SendResult(channel="utility")

    monkeypatch.setattr(dash_app, "send_recordatorio", fake_send)

    original = dash_app.run_recordatorios_job

    def wrapped():
        return original(now=fixed_now)

    monkeypatch.setattr(dash_app, "run_recordatorios_job", wrapped)

    r = client.post(
        "/api/internal/recordatorios",
        headers={"X-Cron-Secret": "cron-secret-test"},
    )
    assert r.status_code == 200
    assert r.json()["sent"] == 0
    assert sent == []
