#!/usr/bin/env bash
# Delete solicitudes + bot state for one WhatsApp phone (e.g. a test handset).
# Does NOT touch other patients, doctors, hours, or clinic_settings.
#
# Usage (on the VPS, from the repo root):
#   bash scripts/wipe-phone-tests.sh 3816224165
#   bash scripts/wipe-phone-tests.sh 5493816224165 --yes
#
# Matches phone / telefono_contacto with LIKE '%<digits>%'.
set -euo pipefail

cd "$(dirname "$0")/.."

DIGITS_RAW="${1:-}"
YES=0
for arg in "${@:2}"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: bash scripts/wipe-phone-tests.sh <phone-digits> [--yes]" >&2
      exit 2
      ;;
  esac
done

DIGITS="$(printf '%s' "$DIGITS_RAW" | tr -cd '0-9')"
if [[ -z "$DIGITS" || ${#DIGITS} -lt 6 ]]; then
  echo "Usage: bash scripts/wipe-phone-tests.sh <phone-digits> [--yes]" >&2
  echo "Example: bash scripts/wipe-phone-tests.sh 3816224165" >&2
  exit 2
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
: "${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env or the environment}"
MYSQL_USER="${MYSQL_USER:-artigas}"
MYSQL_DATABASE="${MYSQL_DATABASE:-artigas_bot}"

mysql_q() {
  docker compose exec -T mysql mysql \
    -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
    --batch --raw -e "$1"
}

echo "==> Matching rows for *${DIGITS}*"
mysql_q "
SELECT id, phone, telefono_contacto, nombre, created_at, status
FROM turno_solicitudes
WHERE phone LIKE '%${DIGITS}%'
   OR telefono_contacto LIKE '%${DIGITS}%';
SELECT phone, state FROM conversation_state
WHERE phone LIKE '%${DIGITS}%';
"

if [[ "$YES" -ne 1 ]]; then
  printf 'Delete these rows? [y/N] '
  read -r ans || true
  case "$ans" in
    y|Y|yes|YES) ;;
    *)
      echo "Aborted."
      exit 0
      ;;
  esac
fi

echo "==> Deleting"
mysql_q "
DELETE FROM turno_solicitudes
WHERE phone LIKE '%${DIGITS}%'
   OR telefono_contacto LIKE '%${DIGITS}%';
DELETE FROM conversation_state
WHERE phone LIKE '%${DIGITS}%';
"

echo "==> Left for this phone"
mysql_q "
SELECT COUNT(*) AS left_solicitudes FROM turno_solicitudes
WHERE phone LIKE '%${DIGITS}%' OR telefono_contacto LIKE '%${DIGITS}%';
SELECT COUNT(*) AS left_state FROM conversation_state
WHERE phone LIKE '%${DIGITS}%';
"

# Best-effort: clear Phase 2 accumulation keys for common AR WhatsApp forms.
if docker compose ps --status running bot-redis >/dev/null 2>&1; then
  variants=("$DIGITS")
  if [[ "$DIGITS" != 54* ]]; then
    variants+=("54${DIGITS}" "549${DIGITS}")
  fi
  for p in "${variants[@]}"; do
    docker compose exec -T bot-redis redis-cli DEL "acc:frags:${p}" "acc:ver:${p}" >/dev/null || true
  done
  echo "==> Cleared bot-redis acc keys (best effort)"
fi

echo "Done. Hard-refresh the dashboard (Ctrl+Shift+R)."
