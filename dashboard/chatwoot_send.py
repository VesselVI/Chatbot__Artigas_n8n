"""Chatwoot outbound helpers for Confirmación desde el panel."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class ChatwootSendError(RuntimeError):
    def __init__(self, message: str, *, code: str = "send_failed", window_closed: bool = False):
        super().__init__(message)
        self.code = code
        self.window_closed = window_closed


@dataclass
class SendResult:
    channel: str  # freeform | utility
    nota_omitted: bool = False


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def chatwoot_api_base() -> str:
    host = (_env("CHATWOOT_HOST") or _env("DOMAIN") or "").strip().lstrip(".")
    if not host:
        raise ChatwootSendError("CHATWOOT_HOST / DOMAIN no configurado.", code="misconfigured")
    return f"https://chat.{host}/api/v1"


def chatwoot_account_id() -> str:
    return (_env("CHATWOOT_ACCOUNT_ID") or "2").strip() or "2"


def chatwoot_api_token() -> str:
    token = (
        _env("CHATWOOT_API_TOKEN")
        or _env("CHATWOOT_ACCESS_TOKEN")
        or _env("CHATWOOT_BOT_TOKEN")
        or ""
    ).strip()
    if not token:
        raise ChatwootSendError("Falta CHATWOOT_API_TOKEN.", code="misconfigured")
    return token


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "api-access-token": chatwoot_api_token(),
        },
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        lower = (body or str(e)).lower()
        window_closed = e.code in (401, 403, 422) and (
            "window" in lower
            or "24 hour" in lower
            or "24-hour" in lower
            or "template" in lower
            or "outside" in lower
        )
        raise ChatwootSendError(
            f"Chatwoot HTTP {e.code}: {body or e.reason}",
            code="http_error",
            window_closed=window_closed,
        ) from e
    except urllib.error.URLError as e:
        raise ChatwootSendError(f"Chatwoot red: {e.reason}", code="network") from e


def send_freeform_message(
    conversation_id: Any,
    content: str,
    *,
    opener: Callable[..., Any] | None = None,
) -> SendResult:
    cid = str(conversation_id or "").strip()
    if not cid:
        raise ChatwootSendError("Solicitud sin conversation_id.", code="missing_conversation")
    text = str(content or "").strip()
    if not text:
        raise ChatwootSendError("Mensaje vacío.", code="empty_message")
    url = (
        f"{chatwoot_api_base()}/accounts/{chatwoot_account_id()}"
        f"/conversations/{cid}/messages"
    )
    _http_json(
        "POST",
        url,
        {
            "content": text,
            "message_type": "outgoing",
            "private": False,
            "content_type": "text",
        },
        opener=opener,
    )
    return SendResult(channel="freeform", nota_omitted=False)


def send_utility_template(
    conversation_id: Any,
    *,
    template_name: str,
    body_params: list[str],
    opener: Callable[..., Any] | None = None,
) -> SendResult:
    """Send Meta UTILITY template via Chatwoot (no Nota slot — ADR-0003)."""
    cid = str(conversation_id or "").strip()
    if not cid:
        raise ChatwootSendError("Solicitud sin conversation_id.", code="missing_conversation")
    name = (template_name or "").strip() or "confirmacion_turno"
    url = (
        f"{chatwoot_api_base()}/accounts/{chatwoot_account_id()}"
        f"/conversations/{cid}/messages"
    )
    # Chatwoot WhatsApp template payload shape (template_params)
    _http_json(
        "POST",
        url,
        {
            "message_type": "outgoing",
            "private": False,
            "content": " ",
            "template_params": {
                "name": name,
                "category": "UTILITY",
                "language": "es_AR",
                "processed_params": {str(i + 1): v for i, v in enumerate(body_params)},
            },
        },
        opener=opener,
    )
    return SendResult(channel="utility", nota_omitted=True)


def is_customer_service_window_open(
    conversation_id: Any,
    *,
    force: bool | None = None,
    opener: Callable[..., Any] | None = None,
) -> bool:
    """
    Best-effort window check. Env CHATWOOT_FORCE_WINDOW=open|closed overrides.
    Default: assume open (free-form) unless forced closed.
    """
    if force is not None:
        return force
    override = (_env("CHATWOOT_FORCE_WINDOW") or "").strip().lower()
    if override in ("closed", "0", "false", "utility"):
        return False
    if override in ("open", "1", "true", "freeform"):
        return True
    # Without a reliable Chatwoot field in this stack, prefer free-form (ticket #3).
    _ = conversation_id
    _ = opener
    return True


def send_confirmacion(
    conversation_id: Any,
    *,
    freeform_content: str,
    tipo: str,
    nombre: str,
    medico: str,
    dia_hora_display: str,
    nota_paciente: str = "",
    window_open: bool | None = None,
    opener: Callable[..., Any] | None = None,
) -> SendResult:
    open_win = is_customer_service_window_open(
        conversation_id, force=window_open, opener=opener
    )
    if open_win:
        try:
            return send_freeform_message(conversation_id, freeform_content, opener=opener)
        except ChatwootSendError as e:
            if not e.window_closed:
                raise
            # fall through to utility
    template = (
        "confirmacion_reprogramacion"
        if str(tipo).lower() == "reprogramar"
        else "confirmacion_turno"
    )
    # Utility has no Nota variable (ADR-0003)
    return send_utility_template(
        conversation_id,
        template_name=template,
        body_params=[nombre, medico, dia_hora_display],
        opener=opener,
    )
