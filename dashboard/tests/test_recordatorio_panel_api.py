"""HTTP seam tests for Recordatorio desde el panel (ADR-0006)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ["DASHBOARD_USERNAME"] = "testuser"
os.environ["DASHBOARD_PASSWORD"] = "testpass"
os.environ["DASHBOARD_SECRET_KEY"] = "test-secret"
os.environ.setdefault("CHATWOOT_HOST", "example.com")
os.environ.setdefault("CHATWOOT_API_TOKEN", "test-token")
os.environ.setdefault("CHATWOOT_INBOX_ID", "7")

import app as dash_app  # noqa: E402
from chatwoot_send import ChatwootSendError, SendResult
from recordatorio_panel import REMINDER_PANEL_CHANNEL


def _row(**kwargs) -> dict[str, Any]:
    base = {
        "id": 1,
        "created_at": datetime(2026, 9, 20, 12, 0, 0),
        "phone": "5491112345678",
        "nombre": "Ana Pérez",
        "dni": "30111222",
        "obra_social": "OSDE",
        "telefono_contacto": "5491112345678",
        "medico": "Adrian Artigas",
        "horario_preferido": "A confirmar por secretaría",
        "status": "confirmed",
        "conversation_id": "42",
        "tipo": "turno",
        "appointment_at": datetime(2026, 10, 5, 10, 30),
        "nota_paciente": None,
        "por_orden_de_llegada": 0,
        "whatsapp_send_status": "sent",
        "whatsapp_send_channel": "freeform",
        "whatsapp_nota_omitted": 0,
        "reminder_sent_at": None,
    }
    base.update(kwargs)
    return base


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.marked: list[tuple[int, datetime, bool]] = []

    def get(self, sid: int):
        return self.rows.get(sid)

    def list_rows(self):
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)

    def update_confirm(self, sid: int, fields: dict[str, Any]):
        self.rows[sid].update(fields)

    def mark_reminder(self, sid: int, sent_at: datetime, *, force: bool = False):
        self.marked.append((sid, sent_at, force))
        self.rows[sid]["reminder_sent_at"] = sent_at


@pytest.fixture
def store():
    return FakeStore(
        [
            _row(id=1),
            _row(
                id=2,
                reminder_sent_at=datetime(2026, 10, 1, 9, 0),
                nombre="Ya recordada",
            ),
            _row(id=3, tipo="turno", status="pending", appointment_at=None),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
    monkeypatch.setattr(dash_app, "mark_reminder_sent", store.mark_reminder)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())
    monkeypatch.setattr(dash_app, "send_private_note", lambda *a, **k: None)

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_list_can_recordatorio_flags(client):
    listed = client.get("/api/solicitudes")
    assert listed.status_code == 200
    by_id = {s["id"]: s for s in listed.json()["solicitudes"]}
    assert by_id[1]["can_recordatorio"] is True
    assert by_id[2]["can_recordatorio"] is True
    assert by_id[3]["can_recordatorio"] is False


def test_recordar_confirmed_sets_reminder_and_channel(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["cid"] = cid
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_recordatorio", fake_send)
    r = client.post(
        "/api/solicitudes/1/recordar",
        json={
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T10:30",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["whatsapp_send_status"] == "sent"
    assert body["whatsapp_send_channel"] == REMINDER_PANEL_CHANNEL
    assert captured["nombre"] == "Ana Pérez"
    assert store.rows[1]["whatsapp_send_channel"] == REMINDER_PANEL_CHANNEL
    assert store.rows[1]["reminder_sent_at"] is not None
    assert len(store.marked) == 1


def test_recordar_already_reminded_requires_confirm(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "send_recordatorio",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    r = client.post(
        "/api/solicitudes/2/recordar",
        json={
            "nombre": "Ya recordada",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T10:30",
        },
    )
    assert r.status_code == 409
    assert r.json()["code"] == "already_reminded"

    r2 = client.post(
        "/api/solicitudes/2/recordar",
        json={
            "nombre": "Ya recordada",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T10:30",
            "confirm_resend": True,
        },
    )
    assert r2.status_code == 200, r2.text
    assert store.marked[-1][2] is True  # force


def test_recordar_cold_phone_send_only(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "ensure_whatsapp_conversation",
        lambda **k: {"conversation_id": "99"},
    )
    monkeypatch.setattr(
        dash_app,
        "send_recordatorio",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    before = len(store.rows)
    r = client.post(
        "/api/solicitudes/recordar",
        json={
            "phone": "5491199988877",
            "nombre": "Nueva",
            "medico": "Adrian Artigas",
            "dia_hora_display": "06/10/2026 11:00",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cold"] is True
    assert body["id"] is None
    assert len(store.rows) == before
    assert len(store.marked) == 0


def test_recordar_failed_keeps_channel_for_reenviar(client, store, monkeypatch):
    def boom(*a, **k):
        raise ChatwootSendError("fail", code="send_failed")

    monkeypatch.setattr(dash_app, "send_recordatorio", boom)
    r = client.post(
        "/api/solicitudes/1/recordar",
        json={
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T10:30",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["whatsapp_send_status"] == "failed"
    assert store.rows[1]["whatsapp_send_channel"] == REMINDER_PANEL_CHANNEL
    assert store.rows[1]["reminder_sent_at"] is None
    assert len(store.marked) == 0

    monkeypatch.setattr(
        dash_app,
        "send_recordatorio",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    store.rows[1]["whatsapp_send_status"] = "failed"
    r2 = client.post("/api/solicitudes/1/reenviar")
    assert r2.status_code == 200, r2.text
    assert r2.json()["whatsapp_send_channel"] == REMINDER_PANEL_CHANNEL
    assert store.rows[1]["reminder_sent_at"] is not None
