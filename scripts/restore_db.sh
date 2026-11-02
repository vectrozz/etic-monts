#!/usr/bin/env bash
# Replace the production database with a pg_dump file.
#
#   scripts/restore_db.sh /home/postgres-backups/db_backup_20260413_000001.sql
#
# DESTRUCTIVE: drops the current database. Take a fresh backup first
# (scripts/backup_db.sh). Asks for confirmation.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <dump.sql>" >&2
    exit 1
fi

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2-; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-eticmont}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-eticmont}"

echo "This will DROP database '$DB_NAME' and restore it from:"
echo "  $BACKUP_FILE"
read -r -p "Type the database name to confirm: " answer
[[ "$answer" == "$DB_NAME" ]] || { echo "Aborted."; exit 1; }

$COMPOSE stop app-flask
$COMPOSE exec -T postgres-db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$DB_NAME\" WITH (FORCE);" \
    -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"
$COMPOSE exec -T postgres-db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q < "$BACKUP_FILE"
$COMPOSE start app-flask

echo "Restore OK. Tables:"
$COMPOSE exec -T postgres-db psql -U "$DB_USER" -d "$DB_NAME" -c '\dt'
