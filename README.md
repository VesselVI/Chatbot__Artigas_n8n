# Clínica Artigas WhatsApp Chatbot

A WhatsApp booking assistant for a private medical clinic in San Miguel de Tucumán, Argentina.
Patients request appointments in an ordinary WhatsApp conversation. The clinic's secretaries manage
doctor availability and incoming requests from a web dashboard, and can take over any conversation
at any moment.

Built for a real client and running in production on a single Ubuntu VPS.

## The problem

The clinic handled appointments with one WhatsApp Business auto-reply that asked patients to send
all their details at once. A secretary then read every message by hand and copied the appointment
into an agenda. That works until volume grows: messages arrive outside opening hours, details come
in incomplete or spread across several messages, and nothing is recorded in a form anyone can query
later.

The aim was to leave the conversation feeling the same to the patient while making the data
structured, searchable and visible to the whole front desk.

## Architecture

```
Patient (WhatsApp)
       │
       ▼
WhatsApp Cloud API
       │
       ▼
   Chatwoot  ─────────────────────►  Secretaries (shared inbox, human takeover)
       │
       │  agent bot webhook
       ▼
     n8n  ──►  bot-redis   burst accumulation
       │  ──►  MySQL       conversation state, doctors, availability, requests
       │  ──►  OpenAI      parsing fallback and FAQ answers
       │
       ▼
  replies, buttons and interactive lists


   Secretaries  ──►  Dashboard (FastAPI)  ──►  MySQL
```

Nine containers behind Caddy, which terminates TLS and issues Let's Encrypt certificates
automatically. Chatwoot owns the WhatsApp channel so that a human can always step in; n8n runs the
bot logic; MySQL is the single source of truth for clinic data.

## Stack

| Layer | Choice |
|---|---|
| Messaging | WhatsApp Cloud API, Chatwoot |
| Bot logic | n8n workflows, OpenAI API |
| Dashboard | Python, FastAPI, Jinja2, Bootstrap |
| Data | MySQL 8, Redis |
| Infrastructure | Docker Compose, Caddy, Ubuntu VPS, Bash |

## How a booking works

1. A patient messages the clinic number. If the intent is already clear, the welcome menu is skipped.
2. One **pedido de datos** message asks for name, DNI, obra social and doctor together.
3. The reply is parsed. Obra social and doctor fall back to a structured WhatsApp list only when the
   free text was ambiguous.
4. The request is written to MySQL and acknowledged. The acknowledgement echoes what was captured and
   offers a single correction pass.
5. Chatwoot receives a private note with the full record; the dashboard shows the request to the
   secretaries, who assign the actual day and time.
6. Outside clinic hours the acknowledgement says so, rather than implying instant confirmation.

If a Chatwoot agent is assigned to the conversation, the bot stops replying. Human handoff always
wins.

## Engineering decisions

The two decisions that shaped the current design are written up as ADRs, with the alternatives and
the consequences.

### Cutting the number of outbound messages, [ADR-0001](docs/adr/0001-lean-booking-pedido-datos.md)

Meta begins billing per outbound WhatsApp message in October 2026. The original step-by-step flow
(name, then DNI, then obra social, then doctor, then confirm, then acknowledge) sent six or seven bot
messages per appointment. At the clinic's volume that is a recurring bill that grows with usage.

The capture was rebuilt around a single request for all the data at once, which is also how the
clinic's old auto-reply behaved, so patients did not have to learn anything new. The separate
confirmation step was dropped in favour of an acknowledgement that repeats the captured data and
offers one correction, trading a small risk of a wrong DNI against roughly half the messages.
Parsing tries regex and heuristics first and only calls OpenAI when those fail, so the language model
is a fallback rather than a per-message cost.

### Handling patients who type in bursts, [ADR-0002](docs/adr/0002-message-accumulation-redis.md)

Patients rarely send their details in one message. They send four in ten seconds. Every Chatwoot
webhook was processed the moment it arrived, so a single booking could fire several bot replies and
the parser would only ever see a fragment of the answer.

Free text is now debounced before routing. Fragments are pushed to a dedicated Redis instance with a
version counter per phone number, and after a seven second trailing wait the buffer is flushed only
if no newer fragment has arrived. Button and list taps bypass the buffer entirely so they still feel
immediate. Redis is kept separate from the one Chatwoot uses so that bot state cannot interfere with
the inbox.

The trade-off is that superseded fragments still start an n8n execution that exits after the wait,
so execution volume is worth watching. The escape hatch, if it becomes expensive, is to move the
buffer into a small sidecar service.

## Data model

Five MySQL tables, created by [`mysql/init.sql`](mysql/init.sql) and evolved through the migrations
alongside it:

| Table | Holds |
|---|---|
| `conversation_state` | Per-phone bot state machine position |
| `doctors` | Doctors and their WhatsApp numbers |
| `doctor_availability` | Weekly morning and evening shifts per doctor |
| `clinic_settings` | Address, opening hours, welcome copy, obras sociales |
| `turno_solicitudes` | Appointment, cancellation, study and reschedule requests |

## The dashboard

A FastAPI application with session auth, serving both the secretaries' pages and a small REST API
that the pages call.

- **Horarios** — pick a doctor, move week by week, set morning and evening shifts in 30 minute steps,
  or mark days unavailable.
- **Solicitudes** — requests from the bot grouped by day, labelled `turno`, `cancelar`, `estudio` or
  `reprogramar`, each linking back to its Chatwoot conversation.
- **Clínica** — address, opening hours, welcome text and the obras sociales list.

It also serves the public privacy policy that Meta requires before a WhatsApp app can go live.

## Tests

Node scripts under [`scripts/`](scripts/) cover the parts most likely to break silently:

| Script | Covers |
|---|---|
| `test-decide-route.js` | Intent routing out of the entry router |
| `test-parse-pedido-datos.js` | Parsing names, DNI, obra social and doctor from free text |
| `test-acc-gate.js`, `test-accumulation-wiring.js` | Which messages get buffered and which bypass |
| `test-booking-messages.js` | Wording of the booking messages |

## Repository layout

```
caddy/       reverse proxy config
dashboard/   FastAPI app, templates, Dockerfile
mysql/       schema, migrations, test-data wipe
n8n/         exported workflows and import notes
scripts/     deployment, backup and test scripts
docs/adr/    architecture decision records
```

## Running it

Deployment, WhatsApp Cloud API setup, the production cutover runbook and backups are in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Configuration is entirely environment driven; see [`.env.example`](.env.example). No credentials,
tokens or phone numbers are stored in this repository.
