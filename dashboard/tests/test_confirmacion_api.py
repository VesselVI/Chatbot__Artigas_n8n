"""HTTP seam tests for Confirmación desde el panel (solicitudes API)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure login works without real secrets
os.environ.setdefault("DASHBOARD_USERNAME", "testuser")
os.environ.setdefault("DASHBOARD_PASSWORD", "testpass")
os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret")

import app as dash_app  # noqa: E402


def _row(
    *,
    id: int = 1,
    tipo: str = "turno",
    status: str = "pending",
    nombre: str = "Ana Pérez",
    medico: str = "Adrian Artigas",
    appointment_at: datetime | None = None,
    nota_paciente: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "created_at": datetime(2026, 9, 20, 12, 0, 0),
        "phone": "5491112345678",
        "nombre": nombre,
        "dni": "30111222",
        "obra_social": "OSDE",
        "telefono_contacto": "5491112345678",
        "medico": medico,
        "horario_preferido": "A confirmar por secretaría",
        "status": status,
        "conversation_id": "42",
        "tipo": tipo,
        "appointment_at": appointment_at,
        "nota_paciente": nota_paciente,
        "whatsapp_send_status": None,
        "whatsapp_send_channel": None,
        "whatsapp_nota_omitted": 0,
    }


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = {r["id"]: dict(r) for r in rows}

    def get(self, sid: int) -> dict[str, Any] | None:
        return self.rows.get(sid)

    def list_rows(self) -> list[dict[str, Any]]:
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)

    def update_confirm(self, sid: int, fields: dict[str, Any]) -> None:
        self.rows[sid].update(fields)


@pytest.fixture
def store():
    return FakeStore([_row(id=1), _row(id=2, tipo="cancelar", nombre="Otro")])


@pytest.fixture
def client(store, monkeypatch):
    def fake_fetch(sid: int):
        return store.get(sid)

    def fake_list():
        return store.list_rows()

    def fake_save(sid: int, fields: dict[str, Any]):
        store.update_confirm(sid, fields)

    monkeypatch.setattr(dash_app, "fetch_solicitud", fake_fetch)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", fake_list)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", fake_save)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())

    from chatwoot_send import SendResult

    monkeypatch.setattr(
        dash_app,
        "send_confirmacion",
        lambda *a, **k: SendResult(channel="freeform", nota_omitted=False),
    )

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_confirm_turno_persists_and_lists_badge(client, store):
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
    assert body["ok"] is True
    assert body["status"] == "confirmed"
    assert body["status_badge"] == "Confirmado"
    assert store.get(1)["status"] == "confirmed"
    assert store.get(1)["appointment_at"] == datetime(2026, 9, 22, 10, 30)
    assert store.get(1)["nota_paciente"] == "Traiga estudios"
    assert store.get(1)["nombre"] == "Ana Pérez"

    listed = client.get("/api/solicitudes")
    assert listed.status_code == 200
    item = next(s for s in listed.json()["solicitudes"] if s["id"] == 1)
    assert item["status"] == "confirmed"
    assert item["status_badge"] == "Confirmado"
    assert item["appointment_at"]
    assert item["nota_paciente"] == "Traiga estudios"


def test_confirm_allows_empty_nota(client, store):
    res = client.post(
        "/api/solicitudes/1/confirm",
        json={
            "appointment_at": "2026-09-22T11:00",
            "nombre": "Ana Pérez",
            "medico": "Adrian Artigas",
            "nota_paciente": "",
        },
    )
    assert res.status_code == 200
    assert store.get(1)["nota_paciente"] == ""


def test_confirm_rejects_cancelar(client):
    res = client.post(
        "/api/solicitudes/2/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "Otro",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 400
    assert res.json()["code"] == "ineligible_tipo"


def test_confirm_not_found(client):
    res = client.post(
        "/api/solicitudes/999/confirm",
        json={
            "appointment_at": "2026-09-22T10:30",
            "nombre": "X",
            "medico": "Y",
        },
    )
    assert res.status_code == 404
