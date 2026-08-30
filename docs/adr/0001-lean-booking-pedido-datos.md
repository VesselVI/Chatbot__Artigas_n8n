# ADR-0001: Lean booking via Pedido de datos (no patient confirm step)

## Context

Meta will bill per outbound WhatsApp message from Oct 2026. The step-by-step booking flow (welcome → nombre → DNI → obra → médico → confirm → ack) sends ~6–7 bot messages per turno. The clinic previously used a single WhatsApp Business auto-reply asking for all datos at once.

## Decision

Replace the multi-step booking capture with:

1. **Pedido de datos** — one outbound ask for nombre, DNI, obra social, and médico (médicos listed in the footer).
2. **Parse → insert → Recepción de solicitud** — no separate confirm step; the ack repeats captured datos and offers **Corregir datos** (one bot correction, then Derivación).
3. **Menú de bienvenida** — horario de clínica + ubicación in the body; only **Sacar un turno** button; skip menú when turno intent is already clear.
4. **Obra social** — if unclear after the blob, send the structured obra list (Particular + dashboard + Otras) as a single follow-up.
5. **Médico** — if unclear, short prompt + WhatsApp list (not a full Pedido repeat).
6. Parsing: regex/heuristics first; OpenAI only on failure.

## Reason

Fewer billable messages with a familiar clinic UX. Corrección de datos on Recepción balances speed vs wrong-DNI risk without a full confirm wizard.

## Consequences

- Workflow **03** state machine shrinks to `awaiting_pedido_datos`, obra/médico follow-ups, and post-recepción correction states.
- **01** Decide Route must recognize `corregir_datos` and route complete blobs without menú.
- **02** welcome copy and buttons change; horarios route may become redundant for new chats.
- Tests in `scripts/test-booking-messages.js` and `scripts/test-decide-route.js` need new cases.
