# Clínica Artigas chatbot

Domain language for the WhatsApp clinic bot: patients request appointments and related help; secretaries confirm slots and take over chats in Chatwoot.

## Language

### Requests and appointments

**Solicitud**:
A row in the secretaries' request queue representing something the bot captured for humans to act on (new turno, cancelación, estudio, precio, or reprogramación).
_Avoid_: Turno solicitud (as the spoken name for the row), ticket, lead

**Turno**:
A patient ophthalmology appointment (or the patient's request for one). Distinct from a doctor availability window.
_Avoid_: Cita, consulta (except in patient-facing copy that already uses those words), appointment

**Turno solicitado**:
A turno request the bot has accepted and queued as a solicitud; día/hora not yet assigned by Secretaría.
_Avoid_: Turno confirmado (at this stage), booking complete

**Turno confirmado**:
A turno whose día/hora Secretaría has communicated to the paciente.
_Avoid_: Turno solicitado, confirmed booking (at bot ack alone)

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
What the solicitud records about when the paciente wanted to come; today often "A confirmar por secretaría" until Secretaría sets the real slot.
_Avoid_: Disponibilidad, día/hora (as if the bot had already booked it)

**Cancelación de solicitud**:
Aborting an in-progress booking flow before a completed new-appointment solicitud; may still leave a cancel-labelled solicitud with partial data for secretaries.
_Avoid_: Cancelación (alone), cancelar turno (when meaning mid-flow abort)

**Cancelación de turno**:
A patient's request to cancel an existing appointment (typically after confirming intent and giving nombre + DNI).
_Avoid_: Cancelación de solicitud, salir, menú

**Reprogramación**:
A patient's request to change day/time of an existing turno; secretaries handle the actual reschedule.
_Avoid_: Cambio de turno (unless clarifying copy), reschedule (in domain prose)

**Solicitud de estudio**:
A human-needed request about a clinical study or treatment (e.g. OCT, campo visual), not a plain turno booking.
_Avoid_: Consulta de precio, FAQ answer (these need Secretaría)

**Consulta de precio**:
A human-needed question about prices or fees. Domain-distinct from Solicitud de estudio even if the bot currently stores both under one queue label.
_Avoid_: Solicitud de estudio, FAQ answer

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
The person messaging the clinic on WhatsApp.
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
