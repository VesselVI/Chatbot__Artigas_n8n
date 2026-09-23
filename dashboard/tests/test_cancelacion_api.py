"""HTTP seam tests for Cancelación desde el panel (#12)."""

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
os.environ.setdefault("CHATWOOT_INBOX_ID", "7")

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
        "horario_preferido": "A confirmar",
        "status": "confirmed",
        "conversation_id": "42",
        "tipo": "turno",
        "appointment_at": datetime(2026, 9, 22, 10, 30),
        "nota_paciente": None,
        "por_orden_de_llegada": 0,
        "whatsapp_send_status": "sent",
        "whatsapp_send_channel": "freeform",
        "whatsapp_nota_omitted": 0,
    }
    base.update(kwargs)
    return base


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = {r["id"]: dict(r) for r in rows}
        self._next_id = max(self.rows.keys(), default=0) + 1

    def get(self, sid: int):
        return self.rows.get(sid)

    def list_rows(self):
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)

    def update_confirm(self, sid: int, fields: dict[str, Any]):
        assert sid in self.rows
        self.rows[sid].update(fields)

    def insert(self, fields: dict[str, Any]) -> int:
        sid = self._next_id
        self._next_id += 1
        row = _row(id=sid, **fields)
        self.rows[sid] = row
        return sid


@pytest.fixture
def store():
    return FakeStore(
        [
            _row(id=1),
            _row(
                id=2,
                nombre="Luis",
                tipo="reprogramar",
                status="confirmed",
                phone="5491199988877",
            ),
            _row(
                id=3,
                nombre="Pendiente",
                tipo="turno",
                status="pending",
                appointment_at=None,
                whatsapp_send_status=None,
            ),
            _row(
                id=4,
                nombre="Ya cancelada",
                status="cancelled",
                tipo="turno",
            ),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
    monkeypatch.setattr(dash_app, "insert_solicitud_cancelacion", store.insert)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())
    monkeypatch.setattr(
        dash_app,
        "ensure_whatsapp_conversation",
        lambda **k: {"conversation_id": "42", "contact_id": "1", "created": False},
    )
    monkeypatch.setattr(
        dash_app,
        "send_cancelacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    monkeypatch.setattr(dash_app, "send_private_note", lambda *a, **k: None)

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_list_can_cancelar_flags(client):
    listed = client.get("/api/solicitudes").json()
    by_id = {s["id"]: s for s in listed["solicitudes"]}
    assert by_id[1]["can_cancelar"] is True
    assert by_id[2]["can_cancelar"] is True
    assert by_id[3]["can_cancelar"] is False
    assert by_id[4]["can_cancelar"] is False
    assert by_id[4]["status_badge"] == "Cancelado"
    assert by_id[4]["can_confirm"] is False
    assert by_id[4]["can_reprogramar"] is False


def test_cancel_confirmed_turno_sends_plantilla(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["cid"] = cid
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    notes = []
    monkeypatch.setattr(dash_app, "send_cancelacion", fake_send)
    monkeypatch.setattr(
        dash_app, "send_private_note", lambda cid, content, **k: notes.append(content)
    )

    res = client.post(
        "/api/solicitudes/1/cancelar",
        json={"nombre": "Ana Pérez"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["status"] == "cancelled"
    assert body["status_badge"] == "Cancelado"
    assert body["whatsapp_send_channel"] == "utility"
    assert captured.get("template_name") == "cancelacion_turno"
    assert captured.get("nombre") == "Ana Pérez"
    assert store.get(1)["status"] == "cancelled"
    assert notes and "Cancelación desde el panel" in notes[0]

    listed = client.get("/api/solicitudes").json()
    item = next(s for s in listed["solicitudes"] if s["id"] == 1)
    assert item["can_confirm"] is False
    assert item["can_reprogramar"] is False
    assert item["can_cancelar"] is False
    assert item["status_badge"] == "Cancelado"


def test_cancel_rejects_pending_turno(client, store, monkeypatch):
    called = {"n": 0}

    def fake_send(*a, **k):
        called["n"] += 1
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_cancelacion", fake_send)
    res = client.post("/api/solicitudes/3/cancelar", json={"nombre": "Pendiente"})
    assert res.status_code == 400
    assert res.json()["code"] == "ineligible_cancel"
    assert called["n"] == 0


def test_cancel_never_freeform(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "send_confirmacion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no freeform")),
    )
    captured = {}

    def fake_send(cid, **kwargs):
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_cancelacion", fake_send)
    res = client.post("/api/solicitudes/1/cancelar", json={"nombre": "Ana Pérez"})
    assert res.status_code == 200
    assert captured.get("template_name") == "cancelacion_turno"


def test_cancel_persists_when_send_fails(client, store, monkeypatch):
    def boom(*a, **k):
        raise ChatwootSendError("down", code="network")

    monkeypatch.setattr(dash_app, "send_cancelacion", boom)
    res = client.post("/api/solicitudes/1/cancelar", json={"nombre": "Ana Pérez"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "cancelled"
    assert body["whatsapp_sent"] is False
    assert body["whatsapp_send_status"] == "failed"
    assert store.get(1)["status"] == "cancelled"
    item = next(
        s for s in client.get("/api/solicitudes").json()["solicitudes"] if s["id"] == 1
    )
    assert item["fallo_al_enviar"] is True
    assert item["can_reenviar"] is True


def test_cold_open_cancel_creates_solicitud(client, store, monkeypatch):
    ensure_calls = []

    def fake_ensure(*, phone, nombre, **kwargs):
        ensure_calls.append(phone)
        return {"conversation_id": "9002", "contact_id": "8", "created": True}

    monkeypatch.setattr(dash_app, "ensure_whatsapp_conversation", fake_ensure)
    monkeypatch.setattr(
        dash_app,
        "send_cancelacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )

    before = set(store.rows.keys())
    res = client.post(
        "/api/solicitudes/cancelar",
        json={"phone": "11 4444-5555", "nombre": "Nuevo Cancel"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] is True
    assert body["status_badge"] == "Cancelado"
    assert body["id"] not in before
    assert body["id"] in store.rows
    assert store.get(body["id"])["status"] == "cancelled"
    assert store.get(body["id"])["conversation_id"] == "9002"
    assert ensure_calls == ["5491144445555"]
