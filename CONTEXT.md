# Clínica Artigas chatbot

Domain language for the WhatsApp clinic bot: patients request appointments and related help; secretaries confirm slots and take over chats in Chatwoot.

## Language

### Requests and appointments

**Solicitud**:
A row in the secretaries' request queue for something humans must act on or have acted on — usually captured by the bot (new turno, cancelación, estudio, precio, or reprogramación), and sometimes created by Secretaría when notifying a patient who had no prior WhatsApp booking row.
_Avoid_: Turno solicitud (as the spoken name for the row), ticket, lead

**Turno**:
A patient ophthalmology appointment (or the patient's request for one). Distinct from a doctor availability window.
_Avoid_: Cita, consulta (except in patient-facing copy that already uses those words), appointment

**Turno solicitado**:
A turno request the bot has accepted and queued as a solicitud; the paciente waits until Secretaría assigns día/hora via Confirmación desde el panel.
_Avoid_: Turno confirmado (at this stage), booking complete, horario preferido

**Turno confirmado**:
A turno whose Día/hora del turno Secretaría has assigned on the solicitud via Confirmación desde el panel (`status=confirmed`). WhatsApp is attempted on submit; persistence does not wait on delivery.
_Avoid_: Turno solicitado, confirmed booking (at bot ack / Recepción de solicitud alone)

**Confirmación desde el panel**:
Secretaría opens a form on a pending solicitud with `tipo=turno`, edits prefilled nombre/médico, sets Día/hora del turno (free datetime), and may add a Nota al paciente; on submit the solicitud becomes confirmed and WhatsApp is sent. If Chatwoot/WhatsApp send fails, the row shows a red **!** with **Fallo al enviar** and **Reenviar** (same payload). When the utility fallback runs, Secretaría is warned that the Nota al paciente was omitted. UI badge: **Confirmado**. Day/time changes after confirm use Reprogramación desde el panel (not a separate edit-and-resend control).
_Avoid_: Confirmación de turno (alone, when meaning Recepción de solicitud), one-click with no form, immutable-after-confirm, using Confirmación for `tipo=reprogramar`

**Marcar confirmado**:
Board-only Confirmado for a pending `tipo=turno` when Secretaría already notified the patient from Chatwoot (e.g. plantilla `confirmacion_turno`). Same día/hora (and optional Nota) form as Confirmación desde el panel, but **no WhatsApp send**; stores `whatsapp_send_channel=external` / `whatsapp_send_status=skipped` so the row is eligible for agenda features (e.g. recordatorios) without a second patient message.
_Avoid_: Confirmación desde el panel (which always attempts WhatsApp), syncing Chatwoot template sends automatically

**Mensaje de confirmación**:
Patient-facing WhatsApp body after Confirmación desde el panel (free-form). Shape:

```
✅ TURNO CONFIRMADO

Nombre: …
Médico: …
Día y hora: …
Nota: …   (line omitted when empty)

Te esperamos unos minutos antes del horario. Si necesitás reprogramar o cancelar, escribinos por acá. Escribí menú para volver.
```

Utility template maps the same fields except Nota (omitted; warn Secretaría).
_Avoid_: Confirmación turno (clara), Recepción de solicitud, Mensaje de reprogramación

**Reprogramación desde el panel**:
Clinic-initiated reschedule notify from the dashboard: Secretaría picks or creates a patient context (search by nombre/phone, or type a phone to open a Chatwoot conversation if none exists), fills Día/hora del turno in a confirm-style modal (no Nota al paciente), always sends the approved Meta utility plantilla `confirmacion_reprogramacion`, and updates one solicitud (`tipo=reprogramar`, `status=confirmed`, badge **Reprogramado**). Entry points: a secondary board-level control, and row actions **Reprogramar** after a Turno confirmado. The board surfaces that solicitud under the new appointment day. Same Meta plantilla may also be sent from Chatwoot’s template UI without updating the board.
_Avoid_: Confirmación desde el panel, Reprogramación (alone, when meaning only the patient’s bot request), free-form WhatsApp for this path

**Mensaje de reprogramación**:
Patient-facing WhatsApp content for Reprogramación desde el panel — always the utility plantilla `confirmacion_reprogramacion` (nombre, médico, nuevo día y hora). Not free-form; no Nota al paciente.
_Avoid_: Mensaje de confirmación, Recepción de solicitud, relying on the old free-form “✅ TURNO REPROGRAMADO” body for this panel path

**Cancelación desde el panel**:
Clinic-initiated cancel notify from the dashboard: same patient search / phone→conversation behaviour as Reprogramación desde el panel; thinner modal (no Día/hora); always sends utility plantilla `cancelacion_turno` (fixed Meta body, no variables); sets the solicitud to cancelled with badge **Cancelado**. Entry points: board-level control next to Reprogramar, and row **Cancelar** after a Turno confirmado. Chatwoot may send the same plantilla manually without board sync.
_Avoid_: Cancelación de turno (alone, when meaning only the patient’s bot request), Cancelación de solicitud

**Fallo al enviar**:
Panel warning when Chatwoot/WhatsApp rejects or fails an outbound send from Confirmación, Reprogramación, or Cancelación desde el panel; paired with **Reenviar** where that action applies.
_Avoid_: Error genérico, failed booking, turno no confirmado (the solicitud may already be confirmed or cancelled in DB)

**Nota al paciente**:
Free-text Secretaría writes in Confirmación desde el panel only; persisted on the solicitud. On free-form send, shown as a `Nota:` line in the Mensaje de confirmación (line omitted when empty). If the Meta customer-service window is closed and the utility template is used, the note is omitted from that send and Secretaría sees an explicit warning. Not collected on Reprogramación o Cancelación desde el panel (those paths always use plantillas without a note slot).
_Avoid_: Note, comentario, Ficha para Secretaría (private; never patient-facing)

**Turno de agenda**:
A doctor availability window on a given day — mañana or noche — with optional start/end times, managed in the dashboard.
_Avoid_: Turno (alone), shift (in domain prose; OK in code comments)

**Horario de clínica**:
The clinic's public opening hours (FAQ, after-hours footer on patient messages).
_Avoid_: Horario (alone), disponibilidad

**Disponibilidad**:
Which Turnos de agenda a médico has for a given week in the dashboard.
_Avoid_: Horario de clínica, slots (in domain prose)

**Horario preferido**:
Deprecated in the booking process: the bot no longer asks the paciente for a preferred slot. Día/hora exist only after Confirmación desde el panel. Legacy DB column may still hold a placeholder until removed; do not treat it as a real appointment time.
_Avoid_: Disponibilidad, día/hora del turno, appointment time

**Día/hora del turno**:
The appointment datetime Secretaría assigns in Confirmación desde el panel; stored as a structured field on the solicitud (not free-text preference).
_Avoid_: Horario preferido, Disponibilidad, Turno de agenda (those are doctor windows, not the patient's slot)

**Recordatorio automatico**:
Utility WhatsApp plantilla `recordatorio_turno` sent ~24h before Día/hora del turno for Turnos confirmados that have a linked Chatwoot conversation. n8n Schedule (hourly) calls the dashboard cron endpoint; the dashboard selects due rows, sends via Chatwoot `template_params`, and sets `reminder_sent_at`. Quiet hours 8–20 local; text-only (no quick-reply buttons in v1). Only turnos that live in this system — never DrApp bulk.
_Avoid_: Recordatorio (alone), reminder blast, CRM sync

**Cancelación de solicitud**:
Aborting an in-progress booking flow before a completed new-appointment solicitud; may still leave a cancel-labelled solicitud with partial data for secretaries.
_Avoid_: Cancelación (alone), cancelar turno (when meaning mid-flow abort)

**Cancelación de turno**:
A patient's request to cancel an existing appointment (typically after confirming intent and giving nombre + DNI). Fulfillment and patient notify use Cancelación desde el panel when Secretaría acts from the dashboard.
_Avoid_: Cancelación de solicitud, salir, menú, Cancelación desde el panel (when meaning only the inbound request)

**Reprogramación**:
A patient's request to change day/time of an existing turno. Secretaría handles the actual reschedule in the CRM/agenda; patient notify uses Reprogramación desde el panel (not Confirmación desde el panel).
_Avoid_: Cambio de turno (unless clarifying copy), reschedule (in domain prose), Reprogramación desde el panel (when meaning only the inbound request)

**Solicitud de estudio**:
A human-needed request about a clinical study or treatment (e.g. OCT, campo visual), not a plain turno booking.
_Avoid_: Consulta de precio, FAQ answer (these need Secretaría)

**Consulta de precio**:
A human-needed question about prices or fees. Domain-distinct from Solicitud de estudio even if the bot currently stores both under one queue label.
_Avoid_: Solicitud de estudio, FAQ answer

**Respuesta a consulta desde el panel**:
Row action on a pending solicitud with `tipo=estudio` or `tipo=solicitud`: sends a short patient ack (free-form inside Meta’s customer-service window; utility plantilla `respuesta_consulta` when that window is closed), then sets Contactado. Same plantilla and copy for both tipos. Re-send and Abrir Chat remain allowed after Contactado. No board-level control.
_Avoid_: Bienvenida, Saludo, Confirmar estudio, Menú de bienvenida (bot screen), Confirmación desde el panel

**Mensaje de respuesta a consulta**:
Patient-facing ack for Respuesta a consulta desde el panel — same wording whether free-form or utility: “Hola …, recibimos tu consulta. Te respondemos por este chat en breve.” (nombre only). Not the real estudio/precio answer; that stays free-form in Chatwoot after the window allows it.
_Avoid_: Mensaje de confirmación, Menú de bienvenida, Texto de bienvenida (Settings)

**Contactado**:
Solicitud status (`status=contactado`, badge **Contactado**) for `tipo=estudio` or `tipo=solicitud` after Secretaría starts the WhatsApp thread via Respuesta a consulta desde el panel or Abrir Chat. Means “thread opened / ack sent,” not that the consulta is finished. Never used for pending turnos (those stay pending until Confirmación desde el panel).
_Avoid_: Confirmado, En curso, Avisada, contacted (in domain prose), Turno confirmado

**Obra social**:
The paciente's health coverage or insurer as recorded on a solicitud (including free-text when they choose Otras).
_Avoid_: Seguro, prepaga (unless that is what the paciente said), insurance

**Particular**:
A paciente paying without obra social. Stored as "Particular / Sin Obra Social" in solicitud data.
_Avoid_: Sin obra social (as the primary term), private pay (in domain prose)

**Menú de bienvenida**:
The first bot screen after a greeting. Body includes horario de clínica and ubicación; the only reply button is Sacar un turno (starts the booking ask). No separate Horarios button.
_Avoid_: Menú principal, welcome menu (in domain prose), home screen

**Pedido de datos**:
The single outbound message asking the paciente to send nombre, DNI, obra social, and médico in one reply. Footer lists active médicos (including médico de cabecera). Shown after Sacar un turno or when a turno intent still needs data.
_Avoid_: Ficha de solicitud, formulario, booking wizard

**Recepción de solicitud**:
The outbound ack after a turno solicitud is inserted: confirms receipt, repeats the captured datos for the paciente to verify, and offers a Corregir datos button.
_Avoid_: Confirmación de turno (día/hora is still Secretaría's job), mensaje de éxito

**Corrección de datos**:
The paciente taps Corregir datos on Recepción de solicitud to fix wrong captured datos before Secretaría acts. One bot-led correction (re-Pedido de datos → update same solicitud); a second Corregir datos tap routes to Derivación.
_Avoid_: Reprogramación, editar turno

**Acumulación de mensajes**:
Short inbound bursts from the same paciente are held until 7 seconds after the last text fragment, then merged (space-separated) into one texto before routing or parsing a Pedido de datos. Applies in idle, menu_shown, awaiting_pedido_datos, awaiting_correccion_datos, and immediately after Sacar un turno or Corregir datos. Button and list taps bypass accumulation and run at once. Implemented in workflow 01 with a dedicated bot Redis (not Chatwoot's).
_Avoid_: Debounce, buffer, batching (in domain prose)

**Ficha para Secretaría**:
The full patient/request details Secretaría sees in a Chatwoot nota privada (not sent to the paciente).
_Avoid_: Nota privada (as the domain name for the content; OK when referring to Chatwoot's UI label), private note (in domain prose)

### People and takeover

**Derivación**:
Handing the WhatsApp conversation to team Secretaría so humans reply and the bot enters Bot en silencio.
_Avoid_: Handoff (domain prose), escalate, transfer (prefer Derivación)

**Bot en silencio**:
The bot does not send further replies on that WhatsApp conversation — after Derivación, manual assign to a human, or inbox auto-assign that sets a team on the chat.
_Avoid_: Muted, bot off, conversación atendida (prefer Bot en silencio for the bot's behavior)

**Secretaría**:
The Chatwoot team (and the human secretaries on it) that confirms turnos and handles derivaciones.
_Avoid_: Agent (alone), support, admin

**Paciente**:
The person the clinic serves on WhatsApp — usually someone messaging the clinic, and sometimes someone Secretaría notifies first via plantilla when opening a conversation from the panel.
_Avoid_: Usuario, cliente, contact (prefer Paciente in domain prose)

**Médico**:
A named clinic doctor the patient can choose when requesting a turno.
_Avoid_: Doctor (in Spanish domain prose; OK in English code identifiers), profesional

**Médico de cabecera**:
The paciente's usual doctor at the clinic. Choosing this in booking means Secretaría looks that person up in the clinic CRM (DrApp); the bot does not name a médico.
_Avoid_: Médico cualquiera, any doctor, sin preferencia

**CRM**:
The clinic's patient-record system (they use DrApp). Secretaría uses it to find a paciente's médico de cabecera and related clinical context.
_Avoid_: CMR, EMR (in domain prose unless staff use those words), spreadsheet

**DrApp**:
The CRM product the clinic uses.
_Avoid_: Dr App, doctor app (when meaning this specific system)
