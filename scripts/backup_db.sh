#!/usr/bin/env bash
# Dump the production database to $BACKUP_DIR/db_backup_<timestamp>.sql
#
#   scripts/backup_db.sh              # from the repo root on the server
#   KEEP_DAYS=30 scripts/backup_db.sh # also delete dumps older than 30 days
#
# Crontab (daily at 02:00):
#   0 2 * * * cd /opt/eticmont && scripts/backup_db.sh >> /var/log/eticmont-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

# Read DB settings from .env without exporting everything else.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2-; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-eticmont}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-eticmont}"
BACKUP_DIR="${BACKUP_DIR:-$(env_get BACKUP_DIR)}"; BACKUP_DIR="${BACKUP_DIR:-/home/postgres-backups}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sql"

$COMPOSE exec -T postgres-db pg_dump -U "$DB_USER" "$DB_NAME" > "$FILE.partial"
mv "$FILE.partial" "$FILE"
echo "Backup OK: $FILE ($(du -h "$FILE" | cut -f1))"

if [[ "${KEEP_DAYS:-0}" -gt 0 ]]; then
    find "$BACKUP_DIR" -name 'db_backup_*.sql' -mtime +"$KEEP_DAYS" -print -delete
fi
