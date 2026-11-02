#!/usr/bin/env bash
# Dump the production database to $BACKUP_DIR/db_backup_<timestamp>.sql
#
#   scripts/backup_db.sh                # from anywhere; uses the repo's .env
#   KEEP_DAYS=90 scripts/backup_db.sh   # also delete VALID dumps older than 90 days
#
# Crontab (daily at 02:00):
#   0 2 * * * /root/EMB/etic-monts/scripts/backup_db.sh >> /var/log/eticmonts-backup.log 2>&1
#
# Targets the `postgres-db` service of THIS compose project (never another
# container whose name merely contains "postgres-db"), refuses to keep an
# empty or truncated dump, and exits non-zero so cron reports the failure.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.prod.yml)

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-eticmont}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-eticmont}"
BACKUP_DIR="${BACKUP_DIR:-$(env_get BACKUP_DIR)}"; BACKUP_DIR="${BACKUP_DIR:-/home/postgres-backups}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sql"
TMP="$FILE.partial"
trap 'rm -f "$TMP"' EXIT

"${COMPOSE[@]}" exec -T postgres-db pg_dump -U "$DB_USER" "$DB_NAME" > "$TMP"

if [[ ! -s "$TMP" ]] || ! tail -n 5 "$TMP" | grep -q "PostgreSQL database dump complete"; then
    echo "$(date -Is) BACKUP FAILED: empty or incomplete dump for $DB_NAME" >&2
    exit 1
fi
mv "$TMP" "$FILE"
echo "$(date -Is) backup OK: $FILE ($(du -h "$FILE" | cut -f1))"

if [[ "${KEEP_DAYS:-0}" -gt 0 ]]; then
    # Only prune when today's dump is good (we just checked), and keep at least 7 files.
    find "$BACKUP_DIR" -maxdepth 1 -name 'db_backup_*.sql' -size +0 -mtime +"$KEEP_DAYS" -print0 \
        | sort -z | head -z -n -7 | xargs -0 -r rm -v --
fi
