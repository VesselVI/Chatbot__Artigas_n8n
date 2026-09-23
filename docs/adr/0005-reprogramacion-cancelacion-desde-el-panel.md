# ADR-0005: Reprogramación y Cancelación desde el panel

Clinic-initiated reschedule/cancel notify is a first-class panel flow (not Confirmación desde el panel): always Meta utility plantillas, patient search with phone→Chatwoot conversation create when needed, one updated solicitud per action, and optional unsynced sends from Chatwoot’s template UI.

## Decision

- **Confirmación desde el panel** remains only for pending `tipo=turno` (first confirm + Nota + free-form/utility fallback per ADR-0003).
- **Reprogramación desde el panel** and **Cancelación desde el panel** are separate actions: board-level secondary controls plus row buttons after a Turno confirmado; pending patient `tipo=reprogramar` uses Reprogramar (not Confirmar).
- These two paths **always** send approved utility plantillas (`confirmacion_reprogramacion`, `cancelacion_turno`) — never free-form; no Nota al paciente on the modal.
- Secretaría may search solicitudes by nombre/phone; typing an unknown phone **creates** Chatwoot contact/conversation if missing, creates or updates one solicitud, sends the plantilla, and leaves a Chatwoot private note for audit.
- Picking an existing solicitud **updates that row** (`appointment_at` / cancelled status as applicable); after reprogram the board shows it under the **new appointment day**.
- The same Meta plantillas may be sent from Chatwoot’s UI; **v1 accepts dashboard drift** (no sync back).

## Reason

Many agenda changes happen outside WhatsApp booking; Secretaría still needs to notify. Utility plantillas are the only reliable cold-open channel. Splitting from Confirmación avoids overloading first-confirm UX and Nota rules. One modal/API with prefills keeps ops simple; Chatwoot remain available for emergencies without blocking the panel project on bidirectional sync.

## Consequences

- Plantillas must be Approved on the live WABA (`es_AR`, exact names) before the buttons are useful.
- Chatwoot API must support contact/conversation create from the dashboard credentials.
- `CONFIRMABLE_TIPOS` / Confirmar UI shrink to `turno`; reprogram/cancel get their own endpoints and badges (**Reprogramado**, **Cancelado**).
- Manual Chatwoot template sends will not update solicitud send status until a later sync exists.
