# ADR-0002: Acumulación de mensajes with bot Redis in workflow 01

## Context

Patients often send booking datos in several quick WhatsApp messages. The router processes each Chatwoot webhook immediately, which can trigger multiple bot replies and break Pedido de datos parsing. Lean booking (ADR-0001) assumes one combined texto per capture attempt.

## Decision

- Add a **dedicated `bot-redis`** service (separate from Chatwoot Redis).
- In **workflow 01**, before Decide Route: **trailing 7s accumulation** for free-text only.
- **Scope:** `idle`, `menu_shown`, `awaiting_pedido_datos`, `awaiting_correccion_datos`, and bursts right after **Sacar un turno** or **Corregir datos**.
- **Bypass:** button/list taps (`boton_id` set, `input_select` replies) process immediately.
- **Join rule:** space-separated fragments into one `texto`.
- **Mechanism:** `RPUSH` fragments, `INCR` version per phone, Wait 7s; flush only if version unchanged; then continue existing Normalize/Merge Context path with merged text.

## Reason

One parse per burst without a sidecar service for v1. Trailing debounce matches “wait until they stop typing.” Buttons stay instant.

## Consequences

- Each fragment may spawn an n8n execution that exits after Wait if superseded; monitor execution volume.
- Chatwoot webhook must still return 200 quickly (accumulation branch must not block the HTTP response longer than acceptable — may need early respond or async sub-workflow if Chatwoot times out).
- `IMPORT.md` must document `bot-redis` deploy and Redis credentials on n8n.
- Escape hatch: extract buffer to a sidecar if n8n wait executions become costly.
