"""HTTP seam tests for Respuesta a consulta / Contactado."""

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
        "medico": "",
        "horario_preferido": "Consulta estudio",
        "status": "pending",
        "conversation_id": "42",
        "tipo": "estudio",
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
            _row(id=2, tipo="solicitud", nombre="Luis"),
            _row(id=3, tipo="turno", nombre="María", medico="Adrian Artigas"),
            _row(id=4, tipo="estudio", status="contactado", nombre="Ya contactado"),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
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


def test_list_exposes_can_responder_and_contactado_badge(client, store):
    res = client.get("/api/solicitudes")
    assert res.status_code == 200
    by_id = {s["id"]: s for d in res.json()["dias"] for s in d["solicitudes"]}
    assert by_id[1]["can_responder_consulta"] is True
    assert by_id[1]["can_mark_contactado"] is True
    assert by_id[2]["can_responder_consulta"] is True
    assert by_id[3]["can_responder_consulta"] is False
    assert by_id[3]["can_mark_contactado"] is False
    assert by_id[4]["status_badge"] == "Contactado"
    assert by_id[4]["can_responder_consulta"] is True


def test_responder_consulta_persists_contactado_and_sends(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["cid"] = cid
        captured["nombre"] = kwargs["nombre"]
        captured["content"] = kwargs["freeform_content"]
        return SendResult(channel="freeform", nota_omitted=False)

    monkeypatch.setattr(dash_app, "send_respuesta_consulta", fake_send)

    res = client.post("/api/solicitudes/1/responder-consulta", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["status"] == "contactado"
    assert body["status_badge"] == "Contactado"
    assert body["whatsapp_send_channel"] == "freeform"
    assert store.get(1)["status"] == "contactado"
    assert captured["cid"] == "42"
    assert "recibimos tu consulta" in captured["content"]
    assert captured["nombre"] == "Ana Pérez"


def test_responder_consulta_rejects_turno(client):
    res = client.post("/api/solicitudes/3/responder-consulta", json={})
    assert res.status_code == 400
    assert res.json()["code"] == "ineligible_tipo"


def test_responder_consulta_allows_already_contactado(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "send_respuesta_consulta",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    res = client.post("/api/solicitudes/4/responder-consulta", json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "contactado"
    assert store.get(4)["status"] == "contactado"


def test_mark_contactado_no_whatsapp(client, store, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("mark-contactado must not send WhatsApp")

    monkeypatch.setattr(dash_app, "send_respuesta_consulta", boom)

    res = client.post("/api/solicitudes/1/mark-contactado", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["status"] == "contactado"
    assert body["status_badge"] == "Contactado"
    assert body.get("whatsapp_sent") is False
    assert store.get(1)["status"] == "contactado"


def test_mark_contactado_rejects_turno(client):
    res = client.post("/api/solicitudes/3/mark-contactado", json={})
    assert res.status_code == 400
    assert res.json()["code"] == "ineligible_tipo"


def test_responder_consulta_send_failure_still_contactado(client, store, monkeypatch):
    def fail(*a, **k):
        raise ChatwootSendError("boom", code="http_error")

    monkeypatch.setattr(dash_app, "send_respuesta_consulta", fail)

    res = client.post("/api/solicitudes/1/responder-consulta", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "contactado"
    assert body["whatsapp_send_status"] == "failed"
    assert store.get(1)["status"] == "contactado"
    assert store.get(1)["whatsapp_send_status"] == "failed"
