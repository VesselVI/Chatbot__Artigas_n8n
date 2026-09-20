# Deployment and operations

Operational runbook for the Clínica Artigas chatbot. For what the system does and why it is built
this way, see the [README](../README.md).

All domains, numbers and account identifiers below are placeholders. Real values live in `.env` and
in the client's own accounts, never in this repository.

## Prerequisites

- Hostinger KVM2 (2 vCPU / 8 GB) with Ubuntu
- Domain with DNS A records for `n8n`, `chat`, `dash` (and apex optional) → VPS IP
- OpenAI API key (pay-as-you-go on [platform.openai.com](https://platform.openai.com); not ChatGPT Plus)
- WhatsApp Cloud API (clinic Business number via Chatwoot Embedded Signup; not the Meta test sender)
- Docker + Docker Compose plugin

## Quick deploy

```bash
git clone <this-repo> && cd Chatbot__Artigas_n8n
cp .env.example .env
# Edit .env: DOMAIN, passwords, N8N_ENCRYPTION_KEY, CHATWOOT_SECRET_KEY_BASE
# Generate secrets:
#   openssl rand -hex 32   # N8N_ENCRYPTION_KEY / DASHBOARD_SECRET_KEY
#   openssl rand -hex 64   # CHATWOOT_SECRET_KEY_BASE

sudo bash scripts/setup-swap.sh   # 2G swap once

docker compose up -d
bash scripts/prepare-chatwoot.sh  # once: Chatwoot DB migrate
```

Open:

1. `https://chat.YOUR_DOMAIN` — create Chatwoot admin
2. `https://n8n.YOUR_DOMAIN` — create n8n owner
3. `https://dash.YOUR_DOMAIN` — login with `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`

Firewall: allow only `22`, `80`, `443`.

## n8n workflows

See [n8n/workflows/IMPORT.md](../n8n/workflows/IMPORT.md).

Import order: `02` → `03` → `04` → `01`. Create MySQL, OpenAI, and Chatwoot Header Auth credentials. Re-link Execute Workflow nodes. Point Chatwoot Agent Bot to:

```text
https://n8n.YOUR_DOMAIN/webhook/chatwoot-bot
```

## WhatsApp cutover (clinic number)

n8n does **not** store the WhatsApp token or phone number. Cutover is **Meta + a new Chatwoot inbox**, then wipe test rows. **Do not** full-reimport workflow 01.

Connecting a number that is live in the **WhatsApp Business app** to Cloud API **takes it off the phone** unless Meta offers **Coexistence**. Secretaries then use Chatwoot (`https://chat.YOUR_DOMAIN`), not the phone app. Old phone history does not import. Do this in a quiet hour.

If the number is still on the Business app, **do not** “Add phone number” in Meta API Setup. Use Chatwoot **Embedded Signup** (or Coexistence if the wizard shows it).

### 0. Backup MySQL (before wipe)

```bash
cd /opt/Chatbot__Artigas_n8n
set -a && source .env && set +a
bash scripts/backup-mysql.sh ./backups
```

Optional: snapshot the Chatwoot Postgres volume. Keep doctors/hours; only solicitudes and bot state are wiped later.

### 1. Meta prerequisites

Same Facebook app as the test number is fine.

- Business portfolio owns (or will own) the WhatsApp Business Account
- **Display name** = clinic name (Meta must approve it or outbound can fail)
- **App Live** needs a public Privacy Policy URL. After deploying the dashboard: `https://dash.YOUR_DOMAIN/privacidad` (alias `/privacy`). No login. Paste that in App Dashboard → Settings → Basic, then [Sharing Debugger](https://developers.facebook.com/tools/debug/sharing/).
- **Business verification** strongly recommended (unverified WABA has a tiny send limit)
- System user token is only needed for **Manual** inbox setup (`whatsapp_business_messaging` + `whatsapp_business_management`, never expire)

Do **not** change n8n credentials. Chatwoot still uses the Profile `api-access-token`.

### 2. New Chatwoot inbox (clinic number)

In Chatwoot:

1. **Settings → Inboxes → Add Inbox → WhatsApp**
2. **Embedded Signup** / Continue with Facebook (not Manual, not the existing test inbox)
3. Select the clinic number, complete OTP (SMS/call to that SIM)
4. Inbox name e.g. `Artigas WhatsApp`; add secretary agents + **Asistente Virtual**
5. **Do not** auto-assign the inbox to team **Secretaría** (that mutes the bot via `team_id`)
6. Webhook must be `https://chat.YOUR_DOMAIN/webhooks/whatsapp/+54…` (clinic digits, not the Meta test sender number)
7. If Embedded Signup did not register the callback: Meta → WhatsApp → Configuration → Chatwoot URL + verify token; subscribe **`messages`**. One Meta app has **one** callback URL ([Chatwoot FAQ](https://www.chatwoot.com/hc/user-guide/articles/1756799850-how-to-setup-a-whats_app-channel-manual-flow))
8. **Settings → Applications → Agent Bots** → assign the existing bot (`https://n8n.YOUR_DOMAIN/webhook/chatwoot-bot`) to the **new** inbox. Leave 01 active; do not change the webhook path

Leave the test inbox until a staff phone gets the welcome menu on the clinic number.

### 3. Wipe test appointments and bot state

Does **not** delete doctors, weekly hours, or clínica settings. After backup:

```bash
docker compose exec -T mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < mysql/wipe_test_data.sql
```

(`mysql/wipe_test_data.sql` is `TRUNCATE turno_solicitudes` + `TRUNCATE conversation_state`.)

Dashboard → Solicitudes → Actualizar should be empty.

### 4. Retire the Meta test inbox

1. Staff phone messages the **clinic** number and gets the welcome menu
2. Chatwoot: disable or delete the test inbox so the bot is not bound to two senders
3. Meta: leave or remove the test number; production patients will not use it
4. No Meta **allow list** on the real number (that was only the test sender)

Test conversations can stay on the old inbox and disappear with it. Do not bulk-delete Chatwoot Postgres unless the UI delete is not enough.

### 5. Smoke test (unassigned chat)

| Check | Expect |
|-------|--------|
| `Hola` | Welcome menu |
| Horarios / `1` | Clinic hours |
| Full booking + confirm | Dashboard **turno** (green) |
| Mid-booking cancel Sí | **cancelar** (red) |
| `¿cuánto sale un OCT?` → Hablar secretaria | **estudio** (blue) + Equipo Secretaría |
| Audio → Hablar secretaria | No solicitud row; bot mutes |
| Assigned to an agent or team | Bot silent |

If welcome never arrives: bot not on the **new** inbox, Meta webhook still on the test callback, or the number is still on the phone app.

## Backups

```bash
cd /opt/Chatbot__Artigas_n8n
set -a && source .env && set +a
bash scripts/backup-mysql.sh ./backups
```

Also snapshot Chatwoot/n8n Docker volumes periodically.

## Local notes

- First MySQL start runs [mysql/init.sql](../mysql/init.sql) (schema + seed doctors / obras). Existing VPS DBs need [mysql/migrate_shifts.sql](../mysql/migrate_shifts.sql) before the dashboard can save mañana/noche rows, and [mysql/migrate_solicitudes_tipo.sql](../mysql/migrate_solicitudes_tipo.sql) for solicitud labels (`turno` / `cancelar` / `estudio` / `reprogramar`). Before clinic go-live, dump with [scripts/backup-mysql.sh](../scripts/backup-mysql.sh) then [mysql/wipe_test_data.sql](../mysql/wipe_test_data.sql) (solicitudes + conversation_state only).
- Caddy issues Let’s Encrypt certs automatically once DNS points to the VPS.
- Memory limits in `docker-compose.yml` keep Chatwoot + n8n within ~8 GB with swap.
