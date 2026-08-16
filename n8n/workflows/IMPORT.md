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

n8n blocks `$env` unless compose sets:

- `N8N_BLOCK_ENV_ACCESS_IN_EXPRESSIONS=false`
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`

Then recreate: `docker compose up -d n8n`

Example URL built by workflows:

`https://chat.YOUR_DOMAIN/api/v1/accounts/{{account_id}}/conversations/{{conversation_id}}/messages`

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

## Behaviour checklist

- Bot **skips** replies when `conversation.assignee_id` is set (human handoff)
- Booking states: `idle/menu_shown` → nombre → DNI → obra social (**Particular/Sin Obra Social** first, then dashboard obras, then **Otras**) → médico (**Mi médico de cabecera** first, WhatsApp list) → día/hora → confirmación. Phone is the WhatsApp number from Normalize (no phone question).
- **Cancelar turno** / keywords `cancelar|salir|menu|menú` → confirm → sí clears + welcome / no restores + re-asks
- **Repetir pregunta** re-sends the current step
- Confirm: `INSERT turno_solicitudes` + Chatwoot **private** note + patient message with `volver_menu`. For **Particular / Sin Obra Social** with a **named** doctor, confirmation and the solicitud ficha add `Precio de consulta: 70 mil pesos` (Adrián Artigas) or `40 mil pesos` (other doctors). **Mi médico de cabecera** does not show a price. Other obras never show a price.
- Typed `particular` / `sin obra` / `sin obra social` / `no tengo obra social` / `soy particular` / `como particular` (and close variants, case-insensitive) save as `Particular / Sin Obra Social` and skip the Otras prompt. `otra` / `otras` still open the free-text obra step.
- FAQ (free text on `menu_shown` that is not a turno/horarios/`menú`/greeting intent) loads `clinic_settings` + doctors + current-week availability into Gemini. Typed `menú` / `menu` / `hola` return to the welcome menu. `turni` and similar typos still start booking.
- WhatsApp allows **max 3 reply buttons**. Obra social stays as text (`Escribí una opción`) plus Cancelar/Repetir. The doctor picker sends **all** rows as Chatwoot `input_select` (more than 3 items → Meta **list**). WhatsApp lists allow at most 10 rows; n8n cannot set the list button label (Chatwoot I18n / locale controls that).
- Confirmation and horarios replies are **plain text** (Meta test numbers often drop buttons). Type `confirmar` / `sí` / `cancelar` / `repetir`. The confirm step must not end without an HTTP send.
- Chatwoot inbound often sends the button **title** (and WhatsApp may quote the previous message). The router uses the **last line** for Horarios/Turno and only scans earlier lines for nav titles (Repetir/Cancelar/menú), so a quoted welcome cannot steal the tap. Doctor replies must match `medico_*` ids (typed names are ignored and the list is sent again).

## Updating live n8n (do not full-reimport 01)

Re-importing **01** breaks Execute Workflow links. After changing booking:

1. Re-import **03 - Booking Flow** (re-attach MySQL + Chatwoot credentials and Execute Workflow links).
2. Paste only these **01** Code nodes from the repo: **Normalize Message** (`titleMap`) and **Merge Context** (`PREV_STEP`).
3. On the VPS, run `mysql/migrate_shifts.sql` **before** using the new dashboard save (adds `shift` and classifies existing rows).

```bash
docker compose exec -T mysql mysql -uartigas -p"$MYSQL_PASSWORD" artigas_bot < mysql/migrate_shifts.sql
```

## Column mapping (legacy → current)

| Legacy (`estado_pacientes`) | Current (`conversation_state`) |
|-----------------------------|--------------------------------|
| `telefono` | `phone` |
| `estado` | `state` |
| `datos_json` | `context` |
