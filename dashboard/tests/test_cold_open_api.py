"""HTTP seam tests for cold-open Reprogramación (#11)."""

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
        "dni": "",
        "obra_social": "",
        "telefono_contacto": "5491112345678",
        "medico": "Adrian Artigas",
        "horario_preferido": "",
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
                nombre="Sin Chat",
                phone="5491100001111",
                telefono_contacto="5491100001111",
                conversation_id=None,
                status="confirmed",
                tipo="turno",
            ),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
    monkeypatch.setattr(dash_app, "insert_solicitud_reprogramacion", store.insert)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_cold_open_creates_solicitud_ensures_conversation_and_note(
    client, store, monkeypatch
):
    ensure_calls = []
    note_calls = []
    send_calls = []

    def fake_ensure(*, phone, nombre, **kwargs):
        ensure_calls.append({"phone": phone, "nombre": nombre})
        return {"conversation_id": "9001", "contact_id": "55", "created": True}

    def fake_send(cid, **kwargs):
        send_calls.append({"cid": cid, **kwargs})
        return SendResult(channel="utility", nota_omitted=True)

    def fake_note(cid, content, **kwargs):
        note_calls.append({"cid": cid, "content": content})

    monkeypatch.setattr(dash_app, "ensure_whatsapp_conversation", fake_ensure)
    monkeypatch.setattr(dash_app, "send_reprogramacion", fake_send)
    monkeypatch.setattr(dash_app, "send_private_note", fake_note)

    before = set(store.rows.keys())
    res = client.post(
        "/api/solicitudes/reprogramar",
        json={
            "phone": "11 5555-6677",
            "nombre": "Paciente Nuevo",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T15:00",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["created"] is True
    assert body["status_badge"] == "Reprogramado"
    assert body["conversation_id"] == "9001"
    new_id = body["id"]
    assert new_id not in before
    assert new_id in store.rows
    row = store.get(new_id)
    assert row["tipo"] == "reprogramar"
    assert row["status"] == "confirmed"
    assert row["conversation_id"] == "9001"
    assert row["phone"] == "5491155556677"
    assert ensure_calls and ensure_calls[0]["phone"] == "5491155556677"
    assert send_calls and send_calls[0]["cid"] == "9001"
    assert note_calls and "Reprogramación desde el panel" in note_calls[0]["content"]
    assert note_calls[0]["cid"] == "9001"


def test_cold_open_ensure_failure_surfaces(client, store, monkeypatch):
    def boom(**kwargs):
        raise ChatwootSendError("no inbox", code="misconfigured")

    monkeypatch.setattr(dash_app, "ensure_whatsapp_conversation", boom)
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no send")),
    )

    res = client.post(
        "/api/solicitudes/reprogramar",
        json={
            "phone": "5491199990000",
            "nombre": "X",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-05T15:00",
        },
    )
    assert res.status_code == 400
    assert res.json()["code"] in ("ensure_failed", "misconfigured", "http_error")
    # No half-created solicitud when ensure fails before persist
    assert all(r["phone"] != "5491199990000" for r in store.rows.values())


def test_selected_row_still_updated_no_insert(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "ensure_whatsapp_conversation",
        lambda **k: {"conversation_id": "42", "contact_id": "1", "created": False},
    )
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    notes = []
    monkeypatch.setattr(
        dash_app,
        "send_private_note",
        lambda cid, content, **k: notes.append(content),
    )

    before = set(store.rows.keys())
    res = client.post(
        "/api/solicitudes/reprogramar",
        json={
            "solicitud_id": 1,
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-06T11:00",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["created"] is False
    assert set(store.rows.keys()) == before
    assert store.get(1)["appointment_at"] == datetime(2026, 10, 6, 11, 0)
    assert store.get(1)["tipo"] == "reprogramar"
    assert notes


def test_existing_row_without_conversation_is_ensured(client, store, monkeypatch):
    ensure_calls = []

    def fake_ensure(*, phone, nombre, **kwargs):
        ensure_calls.append(phone)
        return {"conversation_id": "777", "contact_id": "9", "created": True}

    monkeypatch.setattr(dash_app, "ensure_whatsapp_conversation", fake_ensure)
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda cid, **k: SendResult(channel="utility", nota_omitted=True),
    )
    monkeypatch.setattr(dash_app, "send_private_note", lambda *a, **k: None)

    res = client.post(
        "/api/solicitudes/2/reprogramar",
        json={
            "nombre": "Sin Chat",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-07T09:30",
        },
    )
    assert res.status_code == 200, res.text
    assert ensure_calls == ["5491100001111"]
    assert store.get(2)["conversation_id"] == "777"
    assert res.json()["whatsapp_sent"] is True


def test_private_note_failure_does_not_undo_sent(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "ensure_whatsapp_conversation",
        lambda **k: {"conversation_id": "42", "contact_id": "1", "created": False},
    )
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )

    def note_boom(*a, **k):
        raise ChatwootSendError("note failed", code="http_error")

    monkeypatch.setattr(dash_app, "send_private_note", note_boom)

    res = client.post(
        "/api/solicitudes/1/reprogramar",
        json={
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "appointment_at": "2026-10-08T10:00",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["whatsapp_sent"] is True
    assert body["whatsapp_send_status"] == "sent"
    assert store.get(1)["status"] == "confirmed"
