#!/usr/bin/env bash
# Deploy Etic'Monts on the VPS. Run ON THE SERVER, from anywhere:
#
#   /root/EMB/etic-monts/scripts/deploy.sh
#
# Production only ever runs `main`: work is merged into main (after
# scripts/ci.sh passes locally) and pushed, then this script deploys
# origin/main. It refuses to run from any other branch.
#
# Steps: preflight → backup → git pull main → build → migrate → restart → health check.
# Only touches the `eticmonts` compose project; other sites are not affected.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.prod.yml)
DEPLOY_BRANCH=main
[[ $# -eq 0 ]] || { echo "usage: $0   (no arguments: always deploys $DEPLOY_BRANCH)" >&2; exit 2; }

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
BRANCH="$(git symbolic-ref -q --short HEAD || echo DETACHED)"
[[ "$BRANCH" == "$DEPLOY_BRANCH" ]] \
    || die "production runs $DEPLOY_BRANCH only (checkout is on '$BRANCH') — 'git checkout $DEPLOY_BRANCH' first"
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
git merge --ff-only "origin/$DEPLOY_BRANCH" \
    || die "local $DEPLOY_BRANCH has diverged from origin/$DEPLOY_BRANCH — never commit on the server"
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
LEGACY_NGINX="${COMPOSE_PROJECT_NAME:-eticmonts}-nginx-1"
if docker ps -a --format '{{.Names}}' | grep -qx "$LEGACY_NGINX"; then
    echo "  removing legacy container $LEGACY_NGINX"
    docker rm -f "$LEGACY_NGINX" >/dev/null
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
Rollback (code):      on your machine: git revert --no-edit $BEFORE..$AFTER on main, scripts/ci.sh,
                      git push, then run $0 again (main stays the only thing deployed)
Rollback (database):  scripts/restore_db.sh <dump from the backup step above>
EOF
