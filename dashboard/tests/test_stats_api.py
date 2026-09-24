"""HTTP seam for GET /api/solicitudes/stats."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DASHBOARD_USERNAME", "testuser")
os.environ.setdefault("DASHBOARD_PASSWORD", "testpass")
os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret")

import app as dash_app  # noqa: E402
import stats as stats_mod  # noqa: E402
from stats import week_bounds as real_week_bounds  # noqa: E402


@pytest.fixture
def client():
    with TestClient(dash_app.app) as c:
        yield c


def _login(client: TestClient) -> None:
    r = client.post(
        "/login",
        data={"username": "testuser", "password": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)


def test_stats_requires_login(client: TestClient):
    res = client.get("/api/solicitudes/stats", follow_redirects=False)
    assert res.status_code == 303
    assert "/login" in (res.headers.get("location") or "")


def test_stats_api_aggregates_rows(client: TestClient, monkeypatch):
    _login(client)
    rows: list[dict[str, Any]] = [
        {
            "id": 1,
            "created_at": datetime(2026, 9, 22, 10, 0),
            "status": "confirmed",
            "tipo": "turno",
        },
        {
            "id": 2,
            "created_at": datetime(2026, 9, 23, 11, 0),
            "status": "cancelled",
            "tipo": "cancelar",
        },
        {
            "id": 3,
            "created_at": datetime(2026, 9, 15, 10, 0),
            "status": "confirmed",
            "tipo": "turno",
        },
    ]
    fixed = date(2026, 9, 23)

    def freeze_week_bounds(today=None):
        return real_week_bounds(fixed)

    monkeypatch.setattr(
        dash_app, "fetch_solicitudes_created_between", lambda *a, **k: rows
    )
    monkeypatch.setattr(dash_app, "week_bounds", freeze_week_bounds)
    monkeypatch.setattr(stats_mod, "week_bounds", freeze_week_bounds)

    res = client.get("/api/solicitudes/stats")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["week_start"] == "2026-09-21"
    assert body["week_end"] == "2026-09-27"
    assert body["current"]["total"] == 2
    assert body["current"]["confirmados"] == 1
    assert body["current"]["cancelaciones"] == 1
    assert body["previous"]["total"] == 1
    assert body["trends"]["cancelaciones"]["label"] == "50% del total"
    assert "no-store" in res.headers.get("Cache-Control", "")
