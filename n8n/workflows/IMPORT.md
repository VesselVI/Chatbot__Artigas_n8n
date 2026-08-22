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

### 2. OpenAI API (pay as you go)

Use the **OpenAI Platform** API, not a ChatGPT Plus/Pro subscription. ChatGPT Plus does not give n8n an API key.

1. Create/sign in at [platform.openai.com](https://platform.openai.com/signup/) (this is a different product from [chatgpt.com](https://chatgpt.com)).
2. **Settings → Billing → Payment methods** → add a card. Then either:
   - **Prepaid credits** (buy a balance, e.g. $5–$10; usage draws it down), or
   - Leave **auto-recharge** on with a **monthly recharge limit** so spend cannot run away.
3. Set a **monthly usage limit** under **Settings → Limits** (and optionally a project limit). Without a limit, pay-as-you-go can keep charging.
4. **API keys → Create new secret key** (name it e.g. `artigas-n8n`). Copy it once; OpenAI will not show it again.
5. In n8n: **Credentials → Add credential → OpenAI API**. Paste the key. Leave Organization ID blank unless you belong to several orgs. Name it **OpenAI account**.
6. Attach that credential to **OpenAI Chat Model** in `04 - FAQ IA`. Model in the export is **`gpt-5-mini`** (cheap chat model, billed per token). You can pick another `*-mini` / `*-nano` from the list if that id is missing on your account.

FAQ volume for this clinic is small; `gpt-5-mini` is typically cents per month. Do **not** put the key in `.env` or git — n8n stores it encrypted in its credentials DB.

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

3. Assign the bot to the **production** WhatsApp inbox (after cutover: the clinic-number inbox, not the Meta test inbox)
4. Activate **01 - Entry Router** in n8n (production webhook). Do not change this URL when adding a new inbox.

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
- Booking states: `idle/menu_shown` → nombre → DNI → obra social (**Particular/Sin Obra Social** first, then dashboard obras, then **Otras**) → médico (**Mi médico de cabecera** first, WhatsApp list) → confirmación (sin día/hora). Phone is the WhatsApp number from Normalize (no phone question). Día/hora lo confirma secretaría por mensaje (canned responses).
- **Cancelar turno (mid-booking)** / keywords `cancelar|salir|menu|menú` → confirm → sí inserts `turno_solicitudes` with `tipo=cancelar` (data filled so far) then clears + welcome / no restores + re-asks.
- **Solicitud de cancelación (NL intent):** frases como `quiero cancelar un turno`, `no voy a poder ir a la consulta`, `cancelar turno` (y variantes) disparan `cancelar_prompt` (Sí/No). Si responde **Sí**, el bot pide **nombre completo + DNI** en un solo mensaje y genera:
  - mensaje al paciente: `Su turno ha sido cancelado.`
  - **private note** para Secretaría con nombre, DNI y texto del paciente
  - fila en `turno_solicitudes` con `tipo=cancelar`
- **Solicitud de reprogramación (NL intent):** frases como `quiero reprogramar un turno`, `necesito un turno para otro día`, `quiero cambiar el horario de mi turno` (y variantes) disparan `reprogramar_prompt` (Sí/No). Si responde **Sí**, pide **nombre completo + DNI** en un solo mensaje y genera:
  - mensaje al paciente de confirmación de solicitud
  - **private note** para Secretaría con nombre, DNI y texto del paciente
  - fila en `turno_solicitudes` con `tipo=reprogramar`
- **Repetir pregunta** re-sends the current step
- Confirm: `INSERT turno_solicitudes` (`tipo` defaults to `turno`) + Chatwoot **private** note + patient message with `volver_menu`. For **Particular / Sin Obra Social** with a **named** doctor, confirmation and the solicitud ficha add `Precio de consulta: 70 mil pesos` (Adrián Artigas) or `40 mil pesos` (other doctors). **Mi médico de cabecera** does not show a price. Other obras never show a price.
- Typed `particular` / `sin obra` / `sin obra social` / `no tengo obra social` / `soy particular` / `como particular` (and close variants, case-insensitive) save as `Particular / Sin Obra Social` and skip the Otras prompt. `otra` / `otras` still open the free-text obra step.
- FAQ (free text on `menu_shown` that is not a turno/horarios/`menú`/greeting intent) loads `clinic_settings` + doctors + current-week availability into OpenAI (`gpt-5-mini`). Typed `menú` / `menu` / `hola` return to the welcome menu. `turni` and similar typos still start booking.
- WhatsApp allows **max 3 reply buttons** (titles **max 20 characters**). Obra social stays as text (`Escribí una opción`) plus Cancelar/Repetir. The doctor picker sends **all** rows as Chatwoot `input_select` (more than 3 items → Meta **list**). WhatsApp lists allow at most 10 rows; n8n cannot set the list button label (Chatwoot I18n / locale controls that).
- **Fotos / audios / video / archivo:** Normalize sets `tipo: media`. Decide Route sends `media_warn` even mid-booking (MySQL `state` unchanged). Message: *Por acá no podemos recibir fotos ni audios…* Buttons: `Continuar consulta` (`continuar_consulta`) / `Hablar secretaria` (`hablar_secretaria`). Continuar re-asks the booking step if `awaiting_*`, otherwise welcome. Hablar secretaria → team assign.
- **Estudios / tratamientos / precio** and **secretaria / persona phrases** route to the same handoff prompt (`estudio_handoff`), **anytime** (including mid-booking), **before** booking continues. Message: *Para poder responder mejor esta consulta necesitamos derivarlo con una secretaria.* Buttons: `Hablar secretaria` / `Hacer otra consulta` (`otra_consulta`). Typed examples that must **not** reach FAQ: `Quiero hablar con una secretaria`, `me podes pasar con una persona?`, `necesito atención humana`, `¿cuánto sale un OCT?`, `campo visual`. Typed `sacar un turno` / `quiero_turno` still starts booking (`isTurno` wins). FAQ / OpenAI never sees handoff phrases.
- **Hybrid intent routing:** `Decide Route` now uses regex + OpenAI classifier (`cancelar`, `reprogramar`, `estudio_precio`, `other`) with confidence threshold fallback. Explicit button/state transitions always win over AI.
- After **Hablar secretaria:** public confirm *Te derivamos con una secretaria. En breve te van a escribir.* + **private** note (motivo `imagen/audio`, `estudio/precio`, or `solicitud_secretaria` + patient quote) + `POST .../assignments` `{ "team_id": CHATWOOT_TEAM_ID }`. Only motivo `estudio/precio` also `INSERT turno_solicitudes` with `tipo=estudio`. Secretary-only requests (`solicitud_secretaria`) do not create a solicitud row. Bot then mutes.
- Typed `1` / `2` after those prompts follow the last prompt (media: 1 continuar / 2 secretaria; estudio: 1 secretaria / 2 otra). Welcome menu `1`/`2` still mean Horarios / Turno when no such prompt is pending.
- Confirmation and horarios replies are **plain text** (Meta test numbers often drop buttons). Type `confirmar` / `sí` / `cancelar` / `repetir`. The confirm step must not end without an HTTP send.
- Chatwoot inbound often sends the button **title** (and WhatsApp may quote the previous message). The router uses the **last line** for Horarios/Turno and only scans earlier lines for nav titles (Repetir/Cancelar/menú), so a quoted welcome cannot steal the tap. Doctor replies must match `medico_*` ids (typed names are ignored and the list is sent again).

## Updating live n8n (do not full-reimport 01)

Re-importing **01** breaks Execute Workflow links to 02/03/04. **Never** Import-from-File the whole `01-entry-router.json` onto a live canvas that already has those links.

### Swap FAQ LLM: Gemini → OpenAI (do not reimport 04)

Re-importing **04** can change its workflow id and break **Call FAQ 04** on live **01**. Swap the model sub-node instead.

1. Create the **OpenAI account** credential (see [OpenAI API (pay as you go)](#2-openai-api-pay-as-you-go)).
2. Open live **04 - FAQ IA**.
3. Delete **Google Gemini Chat Model**.
4. Add **OpenAI Chat Model** (LangChain). Drag its **Model** output onto **Basic LLM Chain**.
5. Select model **`gpt-5-mini`** (or another `*-mini` / `*-nano` if that id is missing). Temperature **0.2**.
6. Attach credential **OpenAI account**. Save.
7. Test: unassigned chat, free-text FAQ such as `dónde queda la clínica?` — expect an OpenAI answer from `clinic_settings`, not a Gemini error. Estudio/precio phrases must still skip FAQ.

The Gemini credential can stay unused in n8n; it is no longer referenced.

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

### Cancelar / reprogramar (Decide Route + collect wiring)

When pasting cancel/reprogramar nodes onto live **01**, verify these fixes from the repo (run `node scripts/test-decide-route.js` locally after pull):

1. **Decide Route** (Code):
   - `cancelar` / `reprogramar` intents are checked **before** generic `turno` booking.
   - `isTurno` excludes cancel/reprogramar phrases (`&& !regexCancelar && !regexReprogramar`).
   - Yes/no accepts WhatsApp button ids `si_generico` / `no_generico` plus typed `si` / `no` on any line (quoted replies).
   - **Mid-booking (`awaiting_*` from workflow 03):** free-text steps (obra, médico) must stay on `booking`. Route `isAwaiting → booking` **before** NL `reprogramar` / `cancelar` (and before AI reprogramar). Estudio/precio handoff still wins when `wantsHandoff` matches. Booking no longer asks día/hora.
2. **Collect chains must be MySQL → Build → Send** (same pattern as mid-booking cancel confirm):
   | Route Switch output | Wire order |
   |---------------------|------------|
   | `cancelar_collect` | **Set awaiting cancelar datos** (MySQL) → **Build cancelar collect** → **Send cancelar collect** |
   | `reprogramar_collect` | **Set awaiting reprogramar datos** (MySQL) → **Build reprogramar collect** → **Send reprogramar collect** |
3. **Set awaiting cancelar datos** query (inline, not `$json.sql_state`):

```sql
UPDATE conversation_state
SET state = 'awaiting_cancelar_datos'
WHERE phone = '{{ $('Decide Route').item.json.telefono }}';
```

4. **Set awaiting reprogramar datos** — same pattern with `awaiting_reprogramar_datos`.
5. **Send cancelar collect** / **Send reprogramar collect** keep `jsonBody: ={{ $json.cw_body }}` because **Build** runs immediately before **Send**.
6. **Finalize chains (n8n 2.34 HTTP Request 4.2):** `Send cancelar confirm` replaces `$json` with the Chatwoot response. Do **not** put `$("Prep …")` in the HTTP **URL** — n8n 2.34 prepends `=` and throws `Invalid URL: =https://…`.
   - Add Code **Restore cancelar finalize item**: `return [{ json: $('Prep cancelar finalize').first().json }];`
   - Wire: **Insert cancelar solicitud ext** → **Restore cancelar finalize item** → **Send cancelar private note**
   - Copy the **URL** from **Send cancelar confirm** (uses `$json.account_id`). If the URL field already has the expression (fx) toggle on, paste **without** a leading `=`.
   - JSON Body: `={{ $json.cw_private }}`
   - Insert/Clear may still use `$('Prep cancelar finalize').first().json.sql_insert` / `sql_state`.
   - Reprogramar: same with **Restore reprogramar finalize item**.
7. If a patient is stuck mid-flow, reset one row: `UPDATE conversation_state SET state='idle', context=JSON_OBJECT() WHERE phone='54…';` or use [mysql/wipe_test_data.sql](../../mysql/wipe_test_data.sql) for a full test wipe.

### Booking / shifts (older update)

1. Re-import **03 - Booking Flow** only if that workflow changed (re-attach MySQL + Chatwoot credentials and Execute Workflow links).
2. On the VPS, run `mysql/migrate_shifts.sql` **before** using the new dashboard save (adds `shift` and classifies existing rows). For solicitud labels (`turno` / `cancelar` / `estudio` / `reprogramar`), also run `mysql/migrate_solicitudes_tipo.sql` (existing rows stay `turno`).

```bash
docker compose exec -T mysql mysql -uartigas -p"$MYSQL_PASSWORD" artigas_bot < mysql/migrate_shifts.sql
docker compose exec -T mysql mysql -uartigas -p"$MYSQL_PASSWORD" artigas_bot < mysql/migrate_solicitudes_tipo.sql
```

### How to test (media + estudio + cancelar/reprogramar)

Use a conversation that is **not** already assigned to an agent or team.

1. Send an **image** (empty caption is fine). Expect the fotos/audios warning with **Continuar consulta** / **Hablar secretaria**. Bot must **not** assign yet. If you were booking, the next **Continuar consulta** must re-ask the same step (state still `awaiting_*`).
2. Tap **Continuar consulta** (or type that title / `1` after the warning). Expect welcome or the current booking question. Send another image, then tap **Hablar secretaria**. Expect the short confirm on WhatsApp, a **private** note in Chatwoot (motivo `imagen/audio` + quote), conversation assigned to team **Secretaría**, and further patient messages **ignored** by the bot.
3. In a **new** unassigned chat, type a precio/OCT question (`¿cuánto sale un OCT?`, `campo visual`, `topografía`). Expect the estudio message with **Hablar secretaria** / **Hacer otra consulta**. OpenAI/FAQ must **not** run. **Hacer otra consulta** returns to the welcome menu. **Hablar secretaria** assigns + private note motivo `estudio/precio`, and a dashboard **Solicitudes** row with badge `estudio`.
4. Type **Quiero hablar con una secretaria** or **me podes pasar con una persona?** (menu or mid-booking). Expect the same handoff prompt, not FAQ/booking. **Hablar secretaria** → private note motivo `solicitud_secretaria` (no dashboard estudio row).
5. From the estudio prompt, type **sacar un turno** (or tap that welcome button). Expect booking, not assign.
6. Confirm a booking → dashboard badge `turno` (DNI column filled). Confirm **Sí, cancelar** mid-booking → badge `cancelar`.
7. Secretaries with assignment notifications enabled should see the new team conversation.
8. Type `quiero cancelar un turno` (or `no voy a poder ir a la consulta`) in an unassigned chat. Expect **¿Quiere cancelar su turno?** with `Sí/No`. Tap `Sí` and send one message with nombre + DNI (e.g. `Juan Pérez 30111222`). Expect patient confirmation, private note to Secretaría, and dashboard badge `cancelar`.
9. Type `quiero reprogramar un turno` (or `quiero cambiar el horario de mi turno`). Expect **¿Quiere reprogramar su turno?** with `Sí/No`. Tap `Sí` and send nombre + DNI in one message. Expect private note and dashboard badge `reprogramar` (orange/warning).

## Chatwoot templates (secretary use)

Create these in Chatwoot at **Settings → Canned Responses** (or Templates). Fill `{{nombre}}`, `{{medico}}`, `{{dia_hora}}` when sending.

### Confirmación de turno (versión A — formal corta)

- Title: `Confirmación turno`

```text
✅ Turno confirmado

Nombre: {{nombre}}
Médico: {{medico}}
Día y hora: {{dia_hora}}

Te esperamos unos minutos antes del horario.
Si necesitás reprogramar o cancelar, escribinos por acá.
Escribí menú para volver.
```

### Confirmación de turno (versión B — pacientes mayores)

- Title: `Confirmación turno (clara)`

```text
Su turno quedó confirmado.

Nombre: {{nombre}}
Médico: {{medico}}
Día y hora: {{dia_hora}}

IMPORTANTE: este mensaje confirma su turno. Por favor no vaya a la clínica hasta tener esta confirmación con día y hora.

Escribí menú para volver.
```

### Reprogramación (versión C)

- Title: `Confirmación reprogramación`

```text
✅ Turno reprogramado

Nombre: {{nombre}}
Médico: {{medico}}
Nuevo día y hora: {{dia_hora}}

Su turno anterior fue cancelado. Agende este nuevo horario.
Escribí menú para volver.
```

### Cancelación

- Title: `Confirmación cancelación turno`

```text
Hola {{nombre}}, confirmamos la cancelación de tu turno.

DNI registrado: {{dni}}.
Si querés reprogramar, respondé por este chat y te ayudamos.
```

### Booking smoke (no día/hora step)

Workflow **03** no longer includes horario prompt nodes (`Ask dia_hora`, `Load hours for prompt`, etc.). After médico selection the flow goes **Save medico state → Load ctx confirm**.

1. Unassigned chat → `Sacar un turno` → nombre → DNI → obra → médico.
2. Expect **confirm summary without día/hora** (no “¿Qué horario preferís?” / doctor schedules).
3. Tap **Confirmar** → patient gets short “Turno solicitado…” (not the ficha). Private note in Chatwoot has full ficha. Dashboard `horario_preferido` = `A confirmar por secretaría`.
4. Outside 8–12 / 16–20 ART → footer about clinic opening hours on the patient ack.

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
