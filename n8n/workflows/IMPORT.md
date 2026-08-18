# Importing Clínica Artigas n8n workflows

## Import order

1. `02-welcome-menu.json`
2. `03-booking-flow.json`
3. `04-faq-ia.json`
4. `01-entry-router.json` (depends on 02/03/04)

In n8n: **Workflows → Import from File** for each JSON. Leave them **inactive** until credentials and links are set.

## Credentials to create

### 1. MySQL account

- Host: `mysql` (Docker service name) or your DB host
- Database / User / Password: from `.env` (`MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`)
- Attach to every **MySQL** node (name in exports: `MySQL account`)

### 2. Google Gemini (PaLM) API

- Create credential **Google Gemini(PaLM) Api account** with your Gemini API key
- Attach to **Google Gemini Chat Model** in `04 - FAQ IA`

### 3. Chatwoot API (Header Auth)

Chatwoot returns *"Necesitas iniciar sesión"* when this header never arrives.

- Type: **Header Auth** (`httpHeaderAuth`)
- Credential name: **Chatwoot API**
- Header **name:** `api-access-token` (hyphens, not underscores)
- Header **value:** Chatwoot **Profile settings → Access Token** (not the Meta/WhatsApp token, not `Bearer …`)

Caddy also copies `api-access-token` → `api_access_token` for Rails.

Attach this credential to every Chatwoot **HTTP Request** node.

## n8n environment

`CHATWOOT_HOST` / `DOMAIN` must be the **root** domain (`tiden.tech`), not `chat.tiden.tech`.

Set `CHATWOOT_TEAM_ID` to the numeric id of the **Secretaría** team (see [Chatwoot team and notifications](#chatwoot-team-and-notifications)). Compose passes it into the n8n container.

n8n blocks `$env` unless compose sets:

- `N8N_BLOCK_ENV_ACCESS_IN_EXPRESSIONS=false`
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`

Then recreate: `docker compose up -d n8n`

Example URL built by workflows:

`https://chat.YOUR_DOMAIN/api/v1/accounts/{{account_id}}/conversations/{{conversation_id}}/messages`

Team assign:

`https://chat.YOUR_DOMAIN/api/v1/accounts/{{account_id}}/conversations/{{conversation_id}}/assignments` with `{ "team_id": CHATWOOT_TEAM_ID }`

## Re-link Execute Workflow nodes

After import, workflow IDs change. Open **01 - Entry Router** and re-select the target workflow on each **Execute Workflow** node:

| Node | Target |
|------|--------|
| Call Welcome 02 / Welcome after cancel | `02 - Welcome Menu` |
| Call FAQ 04 | `04 - FAQ IA` |
| Call Booking 03 / Re-ask after cancel no | `03 - Booking Flow` |

Confirm input mappings still pass: `telefono`, `texto`, `boton_id`, `estado`, `datos_json`, `conversation_id`, `account_id` (subset for 02/04).

## Chatwoot Agent Bot

1. In Chatwoot: **Settings → Applications → Agent Bots** (or Inbox bot settings)
2. Create/configure a bot with webhook URL:

```
https://n8n.DOMAIN/webhook/chatwoot-bot
```

Replace `DOMAIN` with your real domain (same host as `N8N_HOST` / `WEBHOOK_URL`).

3. Assign the bot to the WhatsApp inbox
4. Activate **01 - Entry Router** in n8n (production webhook)

## Chatwoot team and notifications

Handoff after **Hablar secretaria** assigns the conversation to a **Team** (not a single agent). Do **not** auto-assign the WhatsApp inbox to this team, or the bot will stay mute (`team_id` set).

1. Chatwoot: **Settings → Teams → New team**
2. Name: `Secretaría`. Add the secretary agents.
3. Copy the numeric **team id** from the team URL (`/app/accounts/{account_id}/settings/teams/{team_id}`) or **Settings → Teams** after opening the team.
4. Put that number in `.env` as `CHATWOOT_TEAM_ID`, then recreate n8n so `$env.CHATWOOT_TEAM_ID` is visible:

```bash
docker compose up -d n8n
```

5. Each secretary: **Profile settings → Notifications** (Configuración de perfil → Notificaciones):
   - Enable **Mention** / **Mención** (push + in-app) — the bot @mentions team **Secretaría** in the private note so all inbox members on that team get notified.
   - Enable **Push notifications** for the browser (allow when prompted).
   - Optional: enable **Unassigned conversations** audio alerts while Chatwoot is open (team handoff often leaves **Agente = Ninguna** until someone picks it up; assignment push alone may not fire).
   - **Conversation assignment** push only fires when a **specific agent** is assigned; team-only assign does not ping everyone by default.
6. Optional (Chatwoot UI): on team **Secretaría**, enable **Allow auto assign for this team** — then team assign also picks a secretary and sends them an assignment notification (round-robin). Without this, rely on **Mentions** + filter by team.
7. Secretaries find chats under **Conversations → filter by team Secretaría**, or **Mentions**, or **My Inbox** (notification bell). Not only **Mine**.
8. Do **not** apply a Chatwoot **label** from n8n for this flow. The Labels API **overwrites** the full list; skip labels unless the conversation has none you care about.

## Behaviour checklist

- Bot **skips** replies when a **human** is assigned (`conversation.meta.assignee.type === 'user'` or `assignee_id` without bot) **or** `conversation.team_id` / team handoff is set. It does **not** assign on the media or estudio warning itself — only after **Hablar secretaria**.
- Booking states: `idle/menu_shown` → nombre → DNI → obra social (**Particular/Sin Obra Social** first, then dashboard obras, then **Otras**) → médico (**Mi médico de cabecera** first, WhatsApp list) → día/hora → confirmación. Phone is the WhatsApp number from Normalize (no phone question).
- **Cancelar turno** / keywords `cancelar|salir|menu|menú` → confirm → sí inserts `turno_solicitudes` with `tipo=cancelar` (data filled so far) then clears + welcome / no restores + re-asks
- **Repetir pregunta** re-sends the current step
- Confirm: `INSERT turno_solicitudes` (`tipo` defaults to `turno`) + Chatwoot **private** note + patient message with `volver_menu`. For **Particular / Sin Obra Social** with a **named** doctor, confirmation and the solicitud ficha add `Precio de consulta: 70 mil pesos` (Adrián Artigas) or `40 mil pesos` (other doctors). **Mi médico de cabecera** does not show a price. Other obras never show a price.
- Typed `particular` / `sin obra` / `sin obra social` / `no tengo obra social` / `soy particular` / `como particular` (and close variants, case-insensitive) save as `Particular / Sin Obra Social` and skip the Otras prompt. `otra` / `otras` still open the free-text obra step.
- FAQ (free text on `menu_shown` that is not a turno/horarios/`menú`/greeting intent) loads `clinic_settings` + doctors + current-week availability into Gemini. Typed `menú` / `menu` / `hola` return to the welcome menu. `turni` and similar typos still start booking.
- WhatsApp allows **max 3 reply buttons** (titles **max 20 characters**). Obra social stays as text (`Escribí una opción`) plus Cancelar/Repetir. The doctor picker sends **all** rows as Chatwoot `input_select` (more than 3 items → Meta **list**). WhatsApp lists allow at most 10 rows; n8n cannot set the list button label (Chatwoot I18n / locale controls that).
- **Fotos / audios / video / archivo:** Normalize sets `tipo: media`. Decide Route sends `media_warn` even mid-booking (MySQL `state` unchanged). Message: *Por acá no podemos recibir fotos ni audios…* Buttons: `Continuar consulta` (`continuar_consulta`) / `Hablar secretaria` (`hablar_secretaria`). Continuar re-asks the booking step if `awaiting_*`, otherwise welcome. Hablar secretaria → team assign.
- **Estudios / tratamientos / precio** and **secretaria / persona phrases** route to the same handoff prompt (`estudio_handoff`), **anytime** (including mid-booking), **before** booking continues. Message: *Para poder responder mejor esta consulta necesitamos derivarlo con una secretaria.* Buttons: `Hablar secretaria` / `Hacer otra consulta` (`otra_consulta`). Typed examples that must **not** reach FAQ: `Quiero hablar con una secretaria`, `me podes pasar con una persona?`, `necesito atención humana`, `¿cuánto sale un OCT?`, `campo visual`. Typed `sacar un turno` / `quiero_turno` still starts booking (`isTurno` wins). FAQ / Gemini never sees handoff phrases.
- After **Hablar secretaria:** public confirm *Te derivamos con una secretaria. En breve te van a escribir.* + **private** note (motivo `imagen/audio`, `estudio/precio`, or `solicitud_secretaria` + patient quote) + `POST .../assignments` `{ "team_id": CHATWOOT_TEAM_ID }`. Only motivo `estudio/precio` also `INSERT turno_solicitudes` with `tipo=estudio`. Secretary-only requests (`solicitud_secretaria`) do not create a solicitud row. Bot then mutes.
- Typed `1` / `2` after those prompts follow the last prompt (media: 1 continuar / 2 secretaria; estudio: 1 secretaria / 2 otra). Welcome menu `1`/`2` still mean Horarios / Turno when no such prompt is pending.
- Confirmation and horarios replies are **plain text** (Meta test numbers often drop buttons). Type `confirmar` / `sí` / `cancelar` / `repetir`. The confirm step must not end without an HTTP send.
- Chatwoot inbound often sends the button **title** (and WhatsApp may quote the previous message). The router uses the **last line** for Horarios/Turno and only scans earlier lines for nav titles (Repetir/Cancelar/menú), so a quoted welcome cannot steal the tap. Doctor replies must match `medico_*` ids (typed names are ignored and the list is sent again).

## Updating live n8n (do not full-reimport 01)

Re-importing **01** breaks Execute Workflow links to 02/03/04. **Never** Import-from-File the whole `01-entry-router.json` onto a live canvas that already has those links.

### Media and study handoff (paste + add nodes)

Open the repo file `n8n/workflows/01-entry-router.json` (or open each Code node in a text editor) and the live **01 - Entry Router**.

1. **Paste Code nodes** (open the live node → replace `jsCode` with the repo version):
   - **Normalize Message** — attachments → `tipo: 'media'`; `titleMap` includes `Continuar consulta` / `Hablar secretaria` / `Hacer otra consulta` (do **not** map global `1`/`2` here; that would steal DNI and the welcome menu).
   - **Decide Route** — `isSecretariaIntent()` (hablar con secretaria, pasar/derivar con persona/humano, atención humana, etc.) + `isEstudioIntent()` → `estudio_handoff` anytime (before `awaiting_*` booking); `handoff_reason` is `solicitud_secretaria` vs `estudio/precio`; `media_warn`, `hablar_secretaria`; `isTurno` still wins over leftover handoff buttons. **Paste this node on live 01 after pulling this change** — do not full-reimport.
   - **Merge Context** (optional but recommended) — passes `pending_prompt`, `handoff_quote`, `media_kind`.
2. **Do not** change Execute Workflow nodes (Call Welcome 02 / Call FAQ 04 / Call Booking 03).
3. Between **Decide Route** and **Route Switch**, insert (copy from repo if missing):
   - MySQL **Sync pending prompt** — stores `pending_prompt` + quote on `media_warn` / `estudio_handoff`, clears them otherwise. Same MySQL credential as **Get State**. `alwaysOutputData: true`.
   - Code **Restore route item** — `return [{ json: $('Decide Route').first().json }];` so Switch still sees `$json.route`.
   - Connect: **Decide Route → Sync pending prompt → Restore route item → Route Switch**.
4. On **Route Switch**, add three rules (`{{ $json.route }}` equals), then connect:
   | Output | Connect to |
   |--------|------------|
   | `media_warn` | **Build media warning** → **Send media warning** |
   | `estudio_handoff` | **Build estudio handoff** → **Send estudio handoff** |
   | `hablar_secretaria` | **Build handoff confirm** → **Send handoff confirm** → **Prep estudio solicitud** → **Insert estudio solicitud** → **Prep handoff private note** → **Send handoff private note** → **Prep team assign** → **Assign Secretaría team** |
5. New **HTTP Request** nodes: clone **Send horarios** / **Send cancel confirm** (Header Auth **Chatwoot API**, POST `.../messages`, body `={{ $json.cw_body }}`). For **Assign Secretaría team** the path is `.../assignments` (not `/messages`). Attach the same Chatwoot credential.
6. **Solicitudes dashboard (`tipo`)** — after running `mysql/migrate_solicitudes_tipo.sql`, add these MySQL writes (do **not** re-import 01). Booking confirm in **03** still inserts without `tipo`; the column default is `turno`.
   - On **cancel_yes**, before **Clear state cancel yes**:
     - Code **Prep cancelar solicitud** — builds `INSERT ... tipo='cancelar'` from Merge Context (`nombre`, `dni`, `medico`, `dia_hora`, …).
     - MySQL **Insert cancelar solicitud** — query `{{ $json.sql_insert }}`, same MySQL credential as **Get State**. `alwaysOutputData: true`. `onError: continueRegularOutput` so a missing column does not block welcome.
     - Connect: **Route Switch `cancel_yes` → Prep cancelar solicitud → Insert cancelar solicitud → Clear state cancel yes**.
   - On **hablar_secretaria**, after **Send handoff confirm** and before **Prep handoff private note**:
     - Code **Prep estudio solicitud** — if `handoff_reason` is `estudio/precio`, builds `INSERT ... tipo='estudio'` (quote in `horario_preferido`; DNI/nombre from context or empty). Media handoff (`imagen/audio`) runs `SELECT 1` (no row).
     - MySQL **Insert estudio solicitud** — same as cancelar insert node. `alwaysOutputData: true`, `onError: continueRegularOutput`.
     - Connect: **Send handoff confirm → Prep estudio solicitud → Insert estudio solicitud → Prep handoff private note**.
7. Save. Do not deactivate/reactivate in a way that changes the webhook path.

### Booking / shifts (older update)

1. Re-import **03 - Booking Flow** only if that workflow changed (re-attach MySQL + Chatwoot credentials and Execute Workflow links).
2. On the VPS, run `mysql/migrate_shifts.sql` **before** using the new dashboard save (adds `shift` and classifies existing rows). For solicitud labels (`turno` / `cancelar` / `estudio`), also run `mysql/migrate_solicitudes_tipo.sql` (existing rows stay `turno`).

```bash
docker compose exec -T mysql mysql -uartigas -p"$MYSQL_PASSWORD" artigas_bot < mysql/migrate_shifts.sql
docker compose exec -T mysql mysql -uartigas -p"$MYSQL_PASSWORD" artigas_bot < mysql/migrate_solicitudes_tipo.sql
```

### How to test (media + estudio)

Use a conversation that is **not** already assigned to an agent or team.

1. Send an **image** (empty caption is fine). Expect the fotos/audios warning with **Continuar consulta** / **Hablar secretaria**. Bot must **not** assign yet. If you were booking, the next **Continuar consulta** must re-ask the same step (state still `awaiting_*`).
2. Tap **Continuar consulta** (or type that title / `1` after the warning). Expect welcome or the current booking question. Send another image, then tap **Hablar secretaria**. Expect the short confirm on WhatsApp, a **private** note in Chatwoot (motivo `imagen/audio` + quote), conversation assigned to team **Secretaría**, and further patient messages **ignored** by the bot.
3. In a **new** unassigned chat, type a precio/OCT question (`¿cuánto sale un OCT?`, `campo visual`, `topografía`). Expect the estudio message with **Hablar secretaria** / **Hacer otra consulta**. Gemini/FAQ must **not** run. **Hacer otra consulta** returns to the welcome menu. **Hablar secretaria** assigns + private note motivo `estudio/precio`, and a dashboard **Solicitudes** row with badge `estudio`.
4. Type **Quiero hablar con una secretaria** or **me podes pasar con una persona?** (menu or mid-booking). Expect the same handoff prompt, not FAQ/booking. **Hablar secretaria** → private note motivo `solicitud_secretaria` (no dashboard estudio row).
5. From the estudio prompt, type **sacar un turno** (or tap that welcome button). Expect booking, not assign.
6. Confirm a booking → dashboard badge `turno` (DNI column filled). Confirm **Sí, cancelar** mid-booking → badge `cancelar`.
7. Secretaries with assignment notifications enabled should see the new team conversation.

### Test workflow: team assign only (`05-handoff-test.json`)

Import **`05 - Handoff Test (Secretaría assign)`** to exercise the handoff HTTP chain without touching live **01**.

1. n8n → **Import from File** → `n8n/workflows/05-handoff-test.json`
2. Attach **Chatwoot API** (Header Auth) on all three HTTP nodes
3. VPS: `CHATWOOT_TEAM_ID` in `.env` → `docker compose up -d n8n`
4. Open **Decide Route** → set `conversation_id` to the Chatwoot **display_id** (unassigned conversation)
5. **Test workflow** → expect confirm + private note + **Assign Secretaría team** green; Chatwoot **Equipo asignado: Secretaría**
6. Copy **Prep team assign** + **Assign Secretaría team** (and wire after **Send handoff private note**) into live **01**

## Column mapping (legacy → current)

| Legacy (`estado_pacientes`) | Current (`conversation_state`) |
|-----------------------------|--------------------------------|
| `telefono` | `phone` |
| `estado` | `state` |
| `datos_json` | `context` |
