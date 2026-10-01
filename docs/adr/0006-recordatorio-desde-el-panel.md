# ADR-0006: Recordatorio desde el panel

Clinic-initiated reminder notify is a board-level panel flow parallel to Reprogramación/Cancelación desde el panel (ADR-0005), distinct from Recordatorio automatico (cron).

## Decision

- Board control **Recordar turno** only (no row action): patient search / phone→Chatwoot conversation, modal with plantilla slots, **always** utility `recordatorio_turno` (never free-form).
- Prefill from a selected Turno confirmado when present (nombre, médico, Día/hora); every slot stays editable. Cold phone with no row is **send-only** (no new solicitud).
- Send immediately (warn if outside automatic quiet hours 8–20). On a targeted row, set `reminder_sent_at` so the cron does not double-send; re-send requires explicit confirm.
- Fallo al enviar / Reenviar when a solicitud was the target; cold failures are toast-only.

## Reason

Secretaría needs to remind patients who never wrote the bot and to force a reminder outside the 20–28h cron window. Cloning the ADR-0005 search/cold-open pattern keeps ops consistent; tying `reminder_sent_at` on row targets prevents duplicate patient messages from Recordatorio automatico.

## Consequences

- Plantilla variable order differs from reprogram (`{{2}}` día/hora, `{{3}}` médico) — send path must not copy reprogram param wiring.
- Manual send outside quiet hours is allowed by design; cron rules stay unchanged.
