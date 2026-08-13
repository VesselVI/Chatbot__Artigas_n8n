#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d_%H%M%S)
OUT=${1:-./backups}
mkdir -p "$OUT"
docker compose exec -T mysql mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" > "$OUT/mysql_${STAMP}.sql"
echo "MySQL dump: $OUT/mysql_${STAMP}.sql"
