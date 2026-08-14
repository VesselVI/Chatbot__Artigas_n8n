#!/usr/bin/env bash
# First-time Chatwoot DB prepare (run once after postgres is up)
# The mid-run ERROR about installation_configs is a known Chatwoot warning and
# is usually harmless if the command ends with "Loading Installation config".
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Stopping Chatwoot app containers (postgres/redis stay up)..."
docker compose stop chatwoot-rails chatwoot-sidekiq || true

echo "Ensuring Postgres extensions exist..."
docker compose exec -T chatwoot-postgres \
  psql -U chatwoot -d chatwoot -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" || true
docker compose exec -T chatwoot-postgres \
  psql -U chatwoot -d chatwoot -c "CREATE EXTENSION IF NOT EXISTS vector;" || true

echo "Running db:chatwoot_prepare (creates tables + seeds)..."
docker compose run --rm --no-deps \
  --entrypoint "" \
  chatwoot-rails \
  bundle exec rails db:chatwoot_prepare

echo "Checking installation_configs table..."
docker compose exec -T chatwoot-postgres \
  psql -U chatwoot -d chatwoot -c "\\dt installation_configs"

echo "Starting Chatwoot again..."
docker compose up -d chatwoot-rails chatwoot-sidekiq

echo "Done. Open https://chat.\${DOMAIN:-YOUR_DOMAIN} and create the admin account."
