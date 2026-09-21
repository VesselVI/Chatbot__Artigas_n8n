# ADR-0004: Solicitudes table UX (panel)

## Context

Secretaría uses the dashboard Solicitudes table to scan chatbot pedidos. Dense neon badges and overlapping action buttons made tipo/estado and row actions hard to read. A reference appointments UI (search bar, grey row hover, hover-reveal actions, clear status affordances) was chosen as visual inspiration while keeping the same solicitud columns and domain labels.

## Decision

- **Columns (order):** Tipo · Hora · Paciente · DNI · Teléfono · Médico · Detalle · Obra social · Estado · Acciones · Chat. Estado sits immediately right of Obra social.
- **Badges:** High-contrast tipo/estado chips (soft fill + border + readable ink); pendiente is a badge, not muted plain text alone.
- **Search:** Client-only filter on loaded rows by paciente name or teléfono; no `?q=` API in this pass. While filtering, **hide empty day groups**.
- **Hover:** Grey row background; no motion. Acciones (Confirmar / Reenviar / Editar y reenviar) and **Abrir Chat** stay **always visible** in separate columns (nowrap strip so buttons do not overlap). Rows with no Acciones show a muted `—`, never an empty white cell. (Hover-reveal Acciones was rejected in mock review: empty `td.col-acciones` looked broken.)
- **Ship path:** Visual mock (`dashboard/examples/solicitudes-sharp.html`) then live `dashboard/templates/index.html` (ported). Acciones/Chat are Lucide icon buttons with bubble tips; Acciones stay always visible as icons (no expand-into-cell).

## Reason

Client filter is enough for the current in-memory/day-grouped list and avoids API work before visual sign-off. Always-visible Acciones + Chat (nowrap) prevents overlap and avoids a dead Acciones column. Instant grey hover (no animation) matches “fastest” ops scanning. Moving Estado next to Obra social mirrors the reference’s “metadata then status” scan path without dropping clinic-specific columns.

## Consequences

- Mock is the sign-off surface; changing live panel without updating the mock risks drift.
- Search cannot find solicitudes not already loaded; server search needs a later ADR/API.
- Rows with no Acciones show muted `—` in Acciones.
- Porting to `index.html` must preserve day-group hide-on-filter and the Acciones/Chat split.
