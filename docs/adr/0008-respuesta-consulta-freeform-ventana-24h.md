# ADR-0008: Respuesta a consulta — free-form only while 24h window open

## Decision

- **Responder consulta** (estudio | pregunta) is a free-form quick answer typed in the panel modal — not a fixed ack and not Meta utility from the dashboard.
- The row button is shown only while Meta’s ~24h customer-service window is still open (heuristic: solicitud `created_at` within 24h). When closed, hide the button; Secretaría uses Abrir Chat / Chatwoot utility if needed.
- Same rules for `tipo=estudio` and `tipo=pregunta`.

## Reason

Secretaría needs to answer the real consulta (price, hours follow-up, etc.) in one click when WhatsApp still allows free-form. A canned ack was useless; sending utility from the panel when the window is closed duplicated Chatwoot without letting them write the answer.

## Consequences

- `can_responder_consulta` gates on window + tipo + conversation.
- Panel send path never falls back to plantilla `respuesta_consulta` (that plantilla remains optional for Chatwoot-only use).
- Window heuristic can drift from Meta’s true last-inbound timestamp; false negatives hide the button early, false positives fail at send.
