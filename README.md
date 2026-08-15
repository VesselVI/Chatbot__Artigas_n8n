# Clínica Artigas — Chatbot (n8n + Chatwoot + Dashboard)

WhatsApp clinic bot on Hostinger **KVM2**: Chatwoot owns the channel, n8n runs the bot, MySQL stores state and doctor weekly availability, secretaries use a Bootstrap dashboard.

## Architecture

```
Patient (WhatsApp)
    → Chatwoot (inbox + human takeover)
        → n8n Agent Bot webhook
            → MySQL + Gemini
        ← replies / buttons
Secretaries → dash.DOMAIN (horarios por semana) + Chatwoot UI
```

## Stack

| Service | URL |
|---------|-----|
| Dashboard | `https://dash.YOUR_DOMAIN` |
| n8n | `https://n8n.YOUR_DOMAIN` |
| Chatwoot | `https://chat.YOUR_DOMAIN` |
| MySQL | internal only (`mysql:3306`) |

## Prerequisites

- Hostinger KVM2 (2 vCPU / 8 GB) with Ubuntu
- Domain with DNS A records for `n8n`, `chat`, `dash` (and apex optional) → VPS IP
- Gemini API key
- WhatsApp Cloud API number (same number you use today)
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

## Dashboard (secretaries)

- **Horarios**: pick doctor → navigate weeks → select days → **turno mañana** (09:00–12:00) and/or **turno noche** (16:00–19:00) → **Guardar horarios**, or **Marcar no disponible**. Saving again overwrites.
- **Solicitudes**: confirmed booking requests from the bot.
- **Clínica**: address, clinic hours (for “Mi médico de cabecera”), welcome text, obras sociales list.

## n8n workflows

See [n8n/workflows/IMPORT.md](n8n/workflows/IMPORT.md).

Import order: `02` → `03` → `04` → `01`. Create MySQL, Gemini, and Chatwoot Header Auth credentials. Re-link Execute Workflow nodes. Point Chatwoot Agent Bot to:

```text
https://n8n.YOUR_DOMAIN/webhook/chatwoot-bot
```

### Booking UX

1. Nombre → DNI → obra social (list + Otra) → médico (WhatsApp number saved automatically)  
2. Médico list: **Mi médico de cabecera** first, then doctors (WhatsApp interactive list)  
3. Horario free text with that doctor’s **current week** hours (or clinic hours)  
4. Confirm → Chatwoot private note + row in `turno_solicitudes`  
5. Cancel anytime (button/keywords) with “¿Seguro?” confirmation  
6. **Repetir pregunta** on each step (except the doctor list)  

Human handoff: if a Chatwoot agent is assigned, the bot stops replying.

## WhatsApp cutover

1. Finish Chatwoot WhatsApp channel setup (same WABA / phone number id).
2. Activate n8n workflows and Agent Bot webhook.
3. Test with a staff phone: menu, horarios, FAQ, full booking, cancel, week hours in dashboard, agent takeover.
4. Only then point Meta’s webhook fully to Chatwoot (this disconnects the old PC n8n trigger).

## Backups

```bash
export $(grep -v '^#' .env | xargs)
bash scripts/backup-mysql.sh ./backups
```

Also snapshot Chatwoot/n8n Docker volumes periodically.

## Local notes

- First MySQL start runs [mysql/init.sql](mysql/init.sql) (schema + seed doctors / obras). Existing VPS DBs need [mysql/migrate_shifts.sql](mysql/migrate_shifts.sql) before the dashboard can save mañana/noche rows.
- Caddy issues Let’s Encrypt certs automatically once DNS points to the VPS.
- Memory limits in `docker-compose.yml` keep Chatwoot + n8n within ~8 GB with swap.
