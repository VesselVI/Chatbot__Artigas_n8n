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
- Booking states: `idle/menu_shown` → nombre → DNI → obra social (list + Otra) → teléfono → médico (Cualquier doctor first) → día/hora → confirmación
- **Cancelar turno** / keywords `cancelar|salir|menu|menú` → confirm → sí clears + welcome / no restores + re-asks
- **Repetir pregunta** re-sends the current step
- Confirm: `INSERT turno_solicitudes` + Chatwoot **private** note + patient message with `volver_menu`
- FAQ (free text on `menu_shown`) loads `clinic_settings` + doctors + current-week availability into Gemini

## Column mapping (legacy → current)

| Legacy (`estado_pacientes`) | Current (`conversation_state`) |
|-----------------------------|--------------------------------|
| `telefono` | `phone` |
| `estado` | `state` |
| `datos_json` | `context` |
