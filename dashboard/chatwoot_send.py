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


def send_reprogramacion(
    conversation_id: Any,
    *,
    nombre: str,
    medico: str,
    dia_hora_display: str,
    template_name: str = "confirmacion_reprogramacion",
    opener: Callable[..., Any] | None = None,
) -> SendResult:
    """
    Reprogramación desde el panel — always Meta utility plantilla (ADR-0005).
    Never free-form.
    WABA: confirmacion_reprogramacion (es_AR), numbered body vars:
      {{1}} = nombre, {{2}} = médico, {{3}} = nuevo día y hora.
    """
    return send_utility_template(
        conversation_id,
        template_name=template_name or "confirmacion_reprogramacion",
        body_params=[nombre, medico, dia_hora_display],
        opener=opener,
    )


def send_cancelacion(
    conversation_id: Any,
    *,
    nombre: str = "",
    template_name: str = "cancelacion_turno",
    opener: Callable[..., Any] | None = None,
) -> SendResult:
    """
    Cancelación desde el panel — always Meta utility plantilla (ADR-0005).
    Never free-form.
    WABA: cancelacion_turno (es_AR) — fixed body, no variables.
    `nombre` is accepted for call-site compatibility / audit only.
    """
    _ = nombre  # not a Meta body variable on this plantilla
    return send_utility_template(
        conversation_id,
        template_name=template_name or "cancelacion_turno",
        body_params=[],
        opener=opener,
    )


def send_private_note(
    conversation_id: Any,
    content: str,
    *,
    opener: Callable[..., Any] | None = None,
) -> None:
    """Chatwoot private note for panel audit (#11)."""
    cid = str(conversation_id or "").strip()
    if not cid:
        raise ChatwootSendError("Solicitud sin conversation_id.", code="missing_conversation")
    text = str(content or "").strip()
    if not text:
        raise ChatwootSendError("Nota privada vacía.", code="empty_message")
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
            "private": True,
            "content_type": "text",
        },
        opener=opener,
    )


def chatwoot_inbox_id() -> str:
    inbox = (
        _env("CHATWOOT_INBOX_ID")
        or _env("CHATWOOT_WHATSAPP_INBOX_ID")
        or ""
    ).strip()
    if not inbox:
        raise ChatwootSendError(
            "Falta CHATWOOT_INBOX_ID para abrir conversaciones.",
            code="misconfigured",
        )
    return inbox


def _contact_phone_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    payload = payload or {}
    for key in ("payload", "data"):
        block = payload.get(key)
        if isinstance(block, list):
            out.extend(c for c in block if isinstance(c, dict))
        elif isinstance(block, dict):
            nested = block.get("payload") or block.get("contacts") or []
            if isinstance(nested, list):
                out.extend(c for c in nested if isinstance(c, dict))
    if isinstance(payload.get("contacts"), list):
        out.extend(c for c in payload["contacts"] if isinstance(c, dict))
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for c in out:
        cid = str(c.get("id") or "")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        uniq.append(c)
    return uniq


def ensure_whatsapp_conversation(
    *,
    phone: str,
    nombre: str = "",
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """
    Find or create Chatwoot contact + WhatsApp conversation for cold open (#11).
    Returns {conversation_id, contact_id, created}.
    """
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) < 8:
        raise ChatwootSendError("Teléfono inválido para Chatwoot.", code="invalid_phone")
    e164 = f"+{digits}"
    inbox_id = chatwoot_inbox_id()
    account = chatwoot_account_id()
    base = f"{chatwoot_api_base()}/accounts/{account}"

    search = _http_json(
        "GET",
        f"{base}/contacts/search?q={digits}",
        opener=opener,
    )
    contacts = _contact_phone_candidates(search if isinstance(search, dict) else {})
    contact = None
    for c in contacts:
        cphone = "".join(
            ch
            for ch in str(c.get("phone_number") or c.get("identifier") or "")
            if ch.isdigit()
        )
        if cphone and (cphone.endswith(digits) or digits.endswith(cphone)):
            contact = c
            break
    created = False
    if not contact:
        created_payload = _http_json(
            "POST",
            f"{base}/contacts",
            {
                "inbox_id": int(inbox_id) if str(inbox_id).isdigit() else inbox_id,
                "name": (nombre or digits).strip() or digits,
                "phone_number": e164,
            },
            opener=opener,
        )
        contact = None
        if isinstance(created_payload, dict):
            nested = created_payload.get("payload")
            if isinstance(nested, dict):
                contact = nested.get("contact") if isinstance(nested.get("contact"), dict) else nested
            if not contact and isinstance(created_payload.get("contact"), dict):
                contact = created_payload["contact"]
            if not contact:
                contact = created_payload
        created = True
    contact_id = str((contact or {}).get("id") or "").strip()
    if not contact_id:
        raise ChatwootSendError(
            "No se pudo resolver el contacto en Chatwoot.",
            code="contact_failed",
        )

    conv_list = _http_json(
        "GET",
        f"{base}/contacts/{contact_id}/conversations",
        opener=opener,
    )
    conversations: list[dict[str, Any]] = []
    if isinstance(conv_list, dict):
        payload = conv_list.get("payload")
        if isinstance(payload, list):
            conversations = [c for c in payload if isinstance(c, dict)]
        elif isinstance(payload, dict) and isinstance(payload.get("conversations"), list):
            conversations = [
                c for c in payload["conversations"] if isinstance(c, dict)
            ]
    if conversations:
        cid = str(conversations[0].get("id") or "").strip()
        if cid:
            return {
                "conversation_id": cid,
                "contact_id": contact_id,
                "created": created,
            }

    created_conv = _http_json(
        "POST",
        f"{base}/conversations",
        {
            "source_id": digits,
            "inbox_id": int(inbox_id) if str(inbox_id).isdigit() else inbox_id,
            "contact_id": int(contact_id) if contact_id.isdigit() else contact_id,
            "status": "open",
        },
        opener=opener,
    )
    cid = ""
    if isinstance(created_conv, dict):
        cid = str(created_conv.get("id") or "").strip()
        nested = created_conv.get("payload")
        if not cid and isinstance(nested, dict):
            cid = str(nested.get("id") or "").strip()
    if not cid:
        raise ChatwootSendError(
            "No se pudo crear la conversación en Chatwoot.",
            code="conversation_failed",
        )
    return {
        "conversation_id": cid,
        "contact_id": contact_id,
        "created": True,
    }
