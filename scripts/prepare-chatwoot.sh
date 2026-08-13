#!/usr/bin/env bash
# First-time Chatwoot DB prepare (run once after compose is up)
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose run --rm chatwoot-rails bundle exec rails db:chatwoot_prepare
echo "Chatwoot DB ready. Open https://chat.\${DOMAIN} and create the admin account."
