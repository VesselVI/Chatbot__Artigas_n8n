"""Unit tests: Meta plantilla payload shape for panel reprogram/cancel."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.error import HTTPError

import pytest

import chatwoot_send as cw


class _FakeResp:
    def __init__(self, payload: dict[str, Any] | None = None):
        self._raw = json.dumps(payload or {"ok": True}).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_reprogramacion_sends_numbered_body_params(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_open(req, timeout=30):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")
    monkeypatch.setenv("CHATWOOT_ACCOUNT_ID", "2")

    cw.send_reprogramacion(
        "42",
        nombre="Maria Gómez",
        medico="Dr. Artigas",
        dia_hora_display="23/09/2026 10:30",
        opener=fake_open,
    )
    tp = captured["payload"]["template_params"]
    assert tp["name"] == "confirmacion_reprogramacion"
    assert tp["language"] == "es_AR"
    assert tp["category"] == "UTILITY"
    assert tp["processed_params"] == {
        "body": {
            "1": "Maria Gómez",
            "2": "Dr. Artigas",
            "3": "23/09/2026 10:30",
        }
    }


def test_cancelacion_sends_no_body_params(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_open(req, timeout=30):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")

    cw.send_cancelacion("42", nombre="Ana", opener=fake_open)
    tp = captured["payload"]["template_params"]
    assert tp["name"] == "cancelacion_turno"
    assert tp["language"] == "es_AR"
    assert tp["processed_params"] == {}


def test_recordatorio_sends_numbered_body_params(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_open(req, timeout=30):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")
    monkeypatch.setenv("CHATWOOT_ACCOUNT_ID", "2")

    cw.send_recordatorio(
        "42",
        nombre="Ana Pérez",
        medico="Adrian Artigas",
        dia_hora_display="26/09/2026 10:30",
        opener=fake_open,
    )
    tp = captured["payload"]["template_params"]
    assert tp["name"] == "recordatorio_turno"
    assert tp["language"] == "es_AR"
    assert tp["category"] == "UTILITY"
    assert tp["processed_params"] == {
        "body": {
            "1": "Ana Pérez",
            "2": "26/09/2026 10:30",
            "3": "Adrian Artigas",
        }
    }


def test_respuesta_consulta_utility_body_param(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_open(req, timeout=30):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")
    monkeypatch.setenv("CHATWOOT_FORCE_WINDOW", "closed")

    cw.send_respuesta_consulta(
        "42",
        nombre="Ana Pérez",
        freeform_content="Hola Ana Pérez, recibimos tu consulta. Te respondemos por este chat en breve.",
        opener=fake_open,
    )
    tp = captured["payload"]["template_params"]
    assert tp["name"] == "respuesta_consulta"
    assert tp["language"] == "es_AR"
    assert tp["category"] == "UTILITY"
    assert tp["processed_params"] == {"body": {"1": "Ana Pérez"}}


def test_respuesta_consulta_freeform_when_window_open(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_open(req, timeout=30):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")
    monkeypatch.setenv("CHATWOOT_FORCE_WINDOW", "open")

    result = cw.send_respuesta_consulta(
        "42",
        nombre="Ana Pérez",
        freeform_content="Hola Ana Pérez, recibimos tu consulta. Te respondemos por este chat en breve.",
        opener=fake_open,
    )
    assert result.channel == "freeform"
    assert "template_params" not in captured["payload"]
    assert "recibimos tu consulta" in captured["payload"]["content"]


def test_respuesta_consulta_falls_back_on_window_closed_error(monkeypatch):
    calls: list[dict[str, Any]] = []

    def fake_open(req, timeout=30):
        payload = json.loads(req.data.decode("utf-8"))
        calls.append(payload)
        if "template_params" not in payload:
            raise HTTPError(
                req.full_url,
                422,
                "Unprocessable",
                hdrs=None,
                fp=BytesIO(b'{"error":"outside 24 hour window"}'),
            )
        return _FakeResp()

    monkeypatch.setenv("CHATWOOT_HOST", "example.com")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "tok")
    monkeypatch.setenv("CHATWOOT_FORCE_WINDOW", "open")

    result = cw.send_respuesta_consulta(
        "42",
        nombre="Luis",
        freeform_content="Hola Luis, recibimos tu consulta. Te respondemos por este chat en breve.",
        opener=fake_open,
    )
    assert result.channel == "utility"
    assert len(calls) == 2
    assert calls[1]["template_params"]["name"] == "respuesta_consulta"
