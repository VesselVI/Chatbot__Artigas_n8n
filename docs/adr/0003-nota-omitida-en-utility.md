# ADR-0003: Nota al paciente omitted on Meta utility fallback

## Context

Confirmación desde el panel sends a Mensaje de confirmación / Mensaje de reprogramación that may include a Nota al paciente. Inside Meta’s 24h customer-service window that can be free-form via Chatwoot. Outside the window, only an approved UTILITY template is allowed, with fixed variables.

## Decision

- Free-form path: include `Nota:` when non-empty.
- Utility fallback: send the template **without** the note; keep the note stored on the solicitud; **warn Secretaría** in the panel that it was omitted.
- Do not block confirm when a note exists and only utility is available.
- Do not add a `{{nota}}` template variable in v1.

## Reason

Silent omit loses ops trust. Blocking stalls confirmations. A free-text template variable is harder to get approved and easier for Meta to treat as abuse. Warning keeps the commercial “guarda + envía” path working while making the gap visible.

## Consequences

- Panel must distinguish free-form vs utility outcome and surface the warning.
- Meta template copy for `confirmacion_turno` / reprogramación has no note slot; changing that later means re-approval.
- Secretaría may still Abrir Chat to deliver a note when the window is closed.
