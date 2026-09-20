"""HTTP tests for WhatsApp send paths on Confirmación desde el panel (#3–#6)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DASHBOARD_USERNAME", "testuser")
os.environ.setdefault("DASHBOARD_PASSWORD", "testpass")
os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret")
os.environ.setdefault("CHATWOOT_HOST", "example.com")
os.environ.setdefault("CHATWOOT_API_TOKEN", "test-token")

import app as dash_app  # noqa: E402
from chatwoot_send import ChatwootSendError, SendResult


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
        "status": "pending",
        "conversation_id": "42",
        "tipo": "turno",
        "appointment_at": None,
        "nota_paciente": None,
        "whatsapp_send_status": None,
        "whatsapp_send_channel": None,
        "whatsapp_nota_omitted": 0,
    }
    base.update(kwargs)
    return base


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = {r["id"]: dict(r) for r in rows}

    def get(self, sid: int):
        return self.rows.get(sid)

    def list_rows(self):
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)

    def update_confirm(self, sid: int, fields: dict[str, Any]):
        self.rows[sid].update(fields)


@pytest.fixture
def store():
    return FakeStore(
        [
            _row(id=1),
            _row(id=2, tipo="reprogramar", nombre="Luis"),
            _row(id=3, tipo="cancelar"),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_confirm_sends_freeform_mensaje(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["cid"] = cid
        captured["content"] = kwargs["freeform_content"]
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)

    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "Traiga estudios",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["whatsapp_sent"] is True
    assert body["whatsapp_send_channel"] == "freeform"
    assert "✅ TURNO CONFIRMADO" in captured["content"]
    assert "Nota: Traiga estudios" in captured["content"]
    assert store.get(1)["whatsapp_send_status"] == "sent"
    assert store.get(1)["status"] == "confirmed"


def test_confirm_omits_nota_line_when_empty(client, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["content"] = kwargs["freeform_content"]
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)
    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "",
        },
    )
    assert res.status_code == 200
    assert "Nota:" not in captured["content"]


def test_confirm_reprogramar_badge_and_message(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["content"] = kwargs["freeform_content"]
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)
    res = client.post(
        "/api/solicitudes/2/confirm",
        json={
            "appointment_at": "2026-09-23T16:00",
            "nombre": "Luis",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200
    assert res.json()["status_badge"] == "Reprogramado"
    assert "TURNO REPROGRAMADO" in captured["content"]
    listed = client.get("/api/solicitudes").json()
    item = next(s for s in listed["solicitudes"] if s["id"] == 2)
    assert item["status_badge"] == "Reprogramado"
    assert item["can_confirm"] is False


def test_confirm_persists_when_send_fails(client, store, monkeypatch):
    def boom(*a, **k):
        raise ChatwootSendError("down", code="network")

    monkeypatch.setattr(dash_app, "send_confirmacion", boom)
    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "confirmed"
    assert body["whatsapp_sent"] is False
    assert body["whatsapp_send_status"] == "failed"
    assert store.get(1)["status"] == "confirmed"
    assert store.get(1)["whatsapp_send_status"] == "failed"
    listed = client.get("/api/solicitudes").json()
    item = next(s for s in listed["solicitudes"] if s["id"] == 1)
    assert item["fallo_al_enviar"] is True
    assert item["can_reenviar"] is True


def test_reenviar_same_payload(client, store, monkeypatch):
    store.update_confirm(
        1,
        {
            "status": "confirmed",
            "appointment_at": datetime(2026, 9, 22, 10, 30),
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "X",
            "whatsapp_send_status": "failed",
        },
    )
    calls = []

    def fake_send(cid, **kwargs):
        calls.append(kwargs["freeform_content"])
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)
    res = client.post("/api/solicitudes/1/reenviar")
    assert res.status_code == 200
    assert res.json()["whatsapp_sent"] is True
    assert "Nota: X" in calls[0]
    assert store.get(1)["whatsapp_send_status"] == "sent"


def test_editar_y_reenviar(client, store, monkeypatch):
    store.update_confirm(
        1,
        {
            "status": "confirmed",
            "appointment_at": datetime(2026, 9, 22, 10, 30),
            "whatsapp_send_status": "sent",
            "whatsapp_send_channel": "freeform",
        },
    )
    captured = {}

    def fake_send(cid, **kwargs):
        captured["content"] = kwargs["freeform_content"]
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)
    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T11:00",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "Nueva nota",
        },
    )
    assert res.status_code == 200
    assert res.json()["edited"] is True
    assert "11:00" in captured["content"] or "11:00" in res.json()["message_preview"]
    assert store.get(1)["appointment_at"] == datetime(2026, 9, 22, 11, 0)


def test_utility_omits_nota_and_warns(client, store, monkeypatch):
    def fake_send(cid, **kwargs):
        # Simulate closed window → utility path inside send_confirmacion
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_confirmacion", fake_send)
    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "Secreta",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["whatsapp_send_channel"] == "utility"
    assert body["whatsapp_nota_omitted"] is True
    assert body["whatsapp_warning"]
    assert "Nota" in body["whatsapp_warning"]
    assert store.get(1)["nota_paciente"] == "Secreta"
    assert store.get(1)["whatsapp_nota_omitted"] in (True, 1)
