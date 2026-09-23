"""HTTP seam tests for Reprogramación desde el panel (#9)."""

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
        "por_orden_de_llegada": 0,
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
            _row(id=1, tipo="turno", status="pending"),
            _row(
                id=2,
                tipo="turno",
                status="confirmed",
                nombre="Confirmada",
                appointment_at=datetime(2026, 9, 22, 10, 30),
                whatsapp_send_status="sent",
                whatsapp_send_channel="freeform",
            ),
            _row(id=3, tipo="reprogramar", status="pending", nombre="Luis"),
            _row(id=4, tipo="cancelar", status="pending", nombre="Otro"),
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


def test_list_can_reprogramar_flags(client, store):
    listed = client.get("/api/solicitudes")
    assert listed.status_code == 200
    by_id = {s["id"]: s for s in listed.json()["solicitudes"]}
    assert by_id[1]["can_reprogramar"] is False  # pending turno → Confirmar
    assert by_id[1]["can_confirm"] is True
    assert by_id[2]["can_reprogramar"] is True  # confirmed turno
    assert by_id[2]["can_confirm"] is False
    assert by_id[3]["can_reprogramar"] is True  # pending reprogramar
    assert by_id[3]["can_confirm"] is False
    assert by_id[4]["can_reprogramar"] is False


def test_reprogram_confirmed_turno_persists_badge_and_day(client, store, monkeypatch):
    captured = {}

    def fake_send(cid, **kwargs):
        captured["cid"] = cid
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_reprogramacion", fake_send)

    res = client.post(
        "/api/solicitudes/2/reprogramar",
        json={
            "appointment_at": "2026-09-28T16:00",
            "nombre": "Confirmada",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["status"] == "confirmed"
    assert body["status_badge"] == "Reprogramado"
    assert body["tipo"] == "reprogramar"
    assert body["whatsapp_sent"] is True
    assert body["whatsapp_send_channel"] == "utility"
    assert store.get(2)["tipo"] == "reprogramar"
    assert store.get(2)["status"] == "confirmed"
    assert store.get(2)["appointment_at"] == datetime(2026, 9, 28, 16, 0)
    assert captured["cid"] == "42"
    assert captured.get("template_name") == "confirmacion_reprogramacion"
    assert captured.get("nombre") == "Confirmada"
    assert captured.get("medico") == "Adrian Artigas"
    assert captured.get("dia_hora_display") == "28/09/2026 16:00"

    listed = client.get("/api/solicitudes").json()
    item = next(s for s in listed["solicitudes"] if s["id"] == 2)
    assert item["status_badge"] == "Reprogramado"
    assert item["tipo"] == "reprogramar"
    assert item["dia"] == "2026-09-28"
    assert "28/09/2026" in item["dia_label"]
    # Grouped under new appointment day, not created_at (2026-09-20)
    day_labels = {d["fecha"]: d["label"] for d in listed["dias"]}
    assert "2026-09-28" in day_labels
    group = next(d for d in listed["dias"] if d["fecha"] == "2026-09-28")
    assert any(s["id"] == 2 for s in group["solicitudes"])


def test_reprogram_pending_reprogramar(client, store, monkeypatch):
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )
    res = client.post(
        "/api/solicitudes/3/reprogramar",
        json={
            "appointment_at": "2026-09-29T11:00",
            "nombre": "Luis",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status_badge"] == "Reprogramado"
    assert store.get(3)["tipo"] == "reprogramar"
    assert store.get(3)["status"] == "confirmed"


def test_reprogram_rejects_pending_turno(client, store, monkeypatch):
    called = {"n": 0}

    def fake_send(*a, **k):
        called["n"] += 1
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_reprogramacion", fake_send)
    res = client.post(
        "/api/solicitudes/1/reprogramar",
        json={
            "appointment_at": "2026-09-28T16:00",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 400
    assert res.json()["code"] == "use_confirm"
    assert called["n"] == 0
    assert store.get(1)["status"] == "pending"


def test_reprogram_never_freeform(client, store, monkeypatch):
    """Reprogramación siempre plantilla — no free-form collaborator."""
    monkeypatch.setattr(
        dash_app,
        "send_confirmacion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not freeform")),
    )
    captured = {}

    def fake_send(cid, **kwargs):
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_reprogramacion", fake_send)
    res = client.post(
        "/api/solicitudes/2/reprogramar",
        json={
            "appointment_at": "2026-09-28T16:00",
            "nombre": "Confirmada",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200
    assert captured.get("template_name") == "confirmacion_reprogramacion"
    assert captured.get("dia_hora_display") == "28/09/2026 16:00"
    assert store.get(2)["whatsapp_send_channel"] == "utility"


def test_reprogram_persists_when_send_fails(client, store, monkeypatch):
    def boom(*a, **k):
        raise ChatwootSendError("down", code="network")

    monkeypatch.setattr(dash_app, "send_reprogramacion", boom)
    res = client.post(
        "/api/solicitudes/2/reprogramar",
        json={
            "appointment_at": "2026-09-28T16:00",
            "nombre": "Confirmada",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "confirmed"
    assert body["status_badge"] == "Reprogramado"
    assert body["whatsapp_sent"] is False
    assert body["whatsapp_send_status"] == "failed"
    assert store.get(2)["tipo"] == "reprogramar"
    assert store.get(2)["appointment_at"] == datetime(2026, 9, 28, 16, 0)
    listed = client.get("/api/solicitudes").json()
    item = next(s for s in listed["solicitudes"] if s["id"] == 2)
    assert item["fallo_al_enviar"] is True
    assert item["can_reenviar"] is True


def test_reenviar_reprogramado_uses_utility(client, store, monkeypatch):
    store.update_confirm(
        2,
        {
            "tipo": "reprogramar",
            "status": "confirmed",
            "appointment_at": datetime(2026, 9, 28, 16, 0),
            "nombre": "Confirmada",
            "medico": "Adrian Artigas",
            "whatsapp_send_status": "failed",
        },
    )
    captured = {}

    def fake_send(cid, **kwargs):
        captured.update(kwargs)
        return SendResult(channel="utility", nota_omitted=True)

    monkeypatch.setattr(dash_app, "send_reprogramacion", fake_send)
    monkeypatch.setattr(
        dash_app,
        "send_confirmacion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not freeform")),
    )
    res = client.post("/api/solicitudes/2/reenviar")
    assert res.status_code == 200
    assert res.json()["whatsapp_sent"] is True
    assert captured.get("template_name") == "confirmacion_reprogramacion"
    assert captured.get("dia_hora_display") == "28/09/2026 16:00"
    assert store.get(2)["whatsapp_send_status"] == "sent"
