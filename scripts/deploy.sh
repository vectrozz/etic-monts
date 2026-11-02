#!/usr/bin/env bash
# Deploy Etic'Monts on the VPS. Run ON THE SERVER, from anywhere:
#
#   /root/EMB/etic-monts/scripts/deploy.sh            # update the current branch
#   /root/EMB/etic-monts/scripts/deploy.sh main       # switch to / update a branch or tag
#
# Steps: preflight → backup → git pull → build → migrate → restart → health check.
# Only touches the `eticmonts` compose project; other sites are not affected.
# Run scripts/ci.sh locally before pushing what you deploy.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.prod.yml)
REF="${1:-}"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

# ---------------------------------------------------------------- preflight
say "Preflight"
[[ -f .env ]] || die ".env missing (copy .env.example and fill it)"
for k in SECRET_KEY POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REGISTER_TOKEN; do
    [[ -n "$(env_get "$k")" ]] || die "$k is empty in .env"
done
[[ -n "$(env_get FEATURES)" ]] || echo "  note: FEATURES not set in .env → defaults to cout_revient"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    git status --short --untracked-files=no
    die "tracked files are modified on the server — 'git stash push -m server-edits' first"
fi
APP_PORT="$(env_get APP_PORT)"; APP_PORT="${APP_PORT:-8085}"
BEFORE="$(git rev-parse --short HEAD)"
echo "  current: $(git rev-parse --abbrev-ref HEAD) @ $BEFORE, app port 127.0.0.1:$APP_PORT"

# ---------------------------------------------------------------- backup
say "Backup"
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx postgres-db; then
    scripts/backup_db.sh
else
    echo "  postgres-db not running yet — nothing to back up"
fi

# ---------------------------------------------------------------- code
say "Code"
git fetch --prune origin
[[ -n "$REF" ]] && git checkout "$REF"
if git symbolic-ref -q HEAD >/dev/null; then git pull --ff-only; fi   # tags: detached, nothing to pull
AFTER="$(git rev-parse --short HEAD)"
echo "  $BEFORE → $AFTER"
git --no-pager log --oneline "$BEFORE..$AFTER" | head -20 || true

# ---------------------------------------------------------------- build
say "Build"
"${COMPOSE[@]}" build app-flask
mkdir -p static/uploads/profile
chown -R 1000:1000 static/uploads          # the container runs as uid 1000

# ---------------------------------------------------------------- database
say "Database + migrations"
"${COMPOSE[@]}" up -d --wait postgres-db
"${COMPOSE[@]}" run --rm --no-deps app-flask alembic upgrade head
"${COMPOSE[@]}" run --rm --no-deps app-flask alembic current

# ---------------------------------------------------------------- restart
say "Restart"
# v2 → v3: the old loopback nginx container of this project held 127.0.0.1:8085.
if docker ps -a --format '{{.Names}}' | grep -qx eticmonts-nginx-1; then
    echo "  removing legacy container eticmonts-nginx-1"
    docker rm -f eticmonts-nginx-1 >/dev/null
fi
"${COMPOSE[@]}" up -d --remove-orphans app-flask

# ---------------------------------------------------------------- health
say "Health check"
for _ in $(seq 1 30); do
    if body="$(curl -fsS "http://127.0.0.1:$APP_PORT/healthz" 2>/dev/null)"; then
        echo "  $body"
        break
    fi
    sleep 2
done
[[ -n "${body:-}" ]] || { "${COMPOSE[@]}" logs --tail=60 app-flask; die "app did not become healthy"; }
curl -fsS -o /dev/null -w "  public: https://emb.boblabs.eu/login → %{http_code}\n" https://emb.boblabs.eu/login || true
"${COMPOSE[@]}" ps

say "Done ($BEFORE → $AFTER)"
cat <<EOF
Rollback (code only):   git checkout $BEFORE && $0
Rollback (database):    scripts/restore_db.sh <dump from the backup step above>
EOF
