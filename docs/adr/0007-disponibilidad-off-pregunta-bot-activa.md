# ADR-0007: Disponibilidad off → Pregunta (bot stays active)

When the Horarios/Disponibilidad tab toggle is off (default), doctor-hours questions must not be answered from tab data or FAQ; they become a Pregunta without Derivación.

## Decision

- **Disponibilidad** is toggleable in the dashboard; **default off**.
- While off: doctor-hours intents get a fixed patient copy, insert `tipo=pregunta` (badge **Pregunta**), write a private Chatwoot note, **do not** assign Secretaría, **do not** enter Bot en silencio. Repeat hours asks re-send the copy without a second Pregunta.
- Horario de clínica (welcome / `route=horarios`) stays available.
- While on: doctor-hours may again reference Disponibilidad (FAQ IA gated on the toggle).
- `tipo=solicitud` is retired in favour of `pregunta` (migration + stop writing the old enum value). Respuesta a consulta applies to `estudio` | `pregunta`.
- Curated **Preguntas frecuentes** answer verbatim on LLM match only after human-needed intents lose, only in idle/`menu_shown`; hours-like FAQ hits while Disponibilidad is off follow this Pregunta path instead.

## Reason

Secretaría does not want the bot inventing or exposing weekly doctor windows when the tab is “off,” but trapping the patient in Derivación/Bot en silencio blocks booking. A queue row + Chatwoot note gives humans visibility without muting the bot. Retiring `solicitud` removes an unused badge; Preguntas frecuentes must not override the toggle.

## Consequences

- FAQ IA and any Pregunta frecuente matcher must read the Disponibilidad toggle.
- Estudio-style Hablar secretaria buttons are intentionally **not** used on this path.
- Board and KPIs gain a Pregunta tipo; old `solicitud` rows need display/migration handling.
