"""HTTP seam tests for patient search + board-level reprogram path (#10)."""

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
from chatwoot_send import SendResult


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
        self.insert_count = 0

    def get(self, sid: int):
        return self.rows.get(sid)

    def list_rows(self):
        return sorted(self.rows.values(), key=lambda r: r["created_at"], reverse=True)

    def update_confirm(self, sid: int, fields: dict[str, Any]):
        assert sid in self.rows, "must update existing row, not insert"
        self.rows[sid].update(fields)


@pytest.fixture
def store():
    return FakeStore(
        [
            _row(id=1, nombre="Ana Pérez", phone="5491112345678"),
            _row(
                id=2,
                nombre="Luis Gómez",
                phone="5491199988877",
                telefono_contacto="5491199988877",
                status="pending",
                tipo="reprogramar",
                appointment_at=None,
                whatsapp_send_status=None,
            ),
            _row(
                id=3,
                nombre="Otro Cancelar",
                phone="5491155550000",
                tipo="cancelar",
                status="pending",
                appointment_at=None,
                whatsapp_send_status=None,
            ),
        ]
    )


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(dash_app, "fetch_solicitud", store.get)
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "save_solicitud_confirmacion", store.update_confirm)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())
    monkeypatch.setattr(
        dash_app,
        "send_reprogramacion",
        lambda *a, **k: SendResult(channel="utility", nota_omitted=True),
    )

    with TestClient(dash_app.app) as c:
        r = c.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 302)
        yield c


def test_search_by_nombre(client):
    res = client.get("/api/solicitudes/search", params={"q": "ana"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "solicitudes" in body
    ids = [s["id"] for s in body["solicitudes"]]
    assert ids == [1]
    assert body["solicitudes"][0]["nombre"] == "Ana Pérez"
    assert body["solicitudes"][0]["can_reprogramar"] is True


def test_search_by_phone_digits(client):
    res = client.get("/api/solicitudes/search", params={"q": "999888"})
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["solicitudes"]]
    assert ids == [2]


def test_search_empty_query_returns_empty(client):
    res = client.get("/api/solicitudes/search", params={"q": ""})
    assert res.status_code == 200
    assert res.json()["solicitudes"] == []


def test_search_requires_auth(monkeypatch, store):
    monkeypatch.setattr(dash_app, "list_solicitudes_rows", store.list_rows)
    monkeypatch.setattr(dash_app, "get_db", lambda: MagicMock())
    with TestClient(dash_app.app) as c:
        res = c.get(
            "/api/solicitudes/search",
            params={"q": "ana"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "/login" in (res.headers.get("location") or "")


def test_board_level_reprogram_updates_existing_row_no_insert(client, store):
    """Global path: search hit → same /reprogramar update (no duplicate insert)."""
    search = client.get("/api/solicitudes/search", params={"q": "Luis"})
    assert search.status_code == 200
    hit = search.json()["solicitudes"][0]
    assert hit["id"] == 2
    assert hit["can_reprogramar"] is True

    before_ids = set(store.rows.keys())
    res = client.post(
        f"/api/solicitudes/{hit['id']}/reprogramar",
        json={
            "appointment_at": "2026-10-01T09:00",
            "nombre": "Luis Gómez",
            "medico": "Adrian Artigas",
        },
    )
    assert res.status_code == 200, res.text
    assert set(store.rows.keys()) == before_ids
    assert store.get(2)["tipo"] == "reprogramar"
    assert store.get(2)["status"] == "confirmed"
    assert store.get(2)["appointment_at"] == datetime(2026, 10, 1, 9, 0)
    assert res.json()["status_badge"] == "Reprogramado"
