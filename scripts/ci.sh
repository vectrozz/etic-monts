#!/usr/bin/env bash
# Local CI — run before every push (installed as a pre-push hook by
# scripts/install-git-hooks.sh). Needs: python3, docker.
#
#   scripts/ci.sh                  full run (≈1–2 min once the image layers are cached)
#   scripts/ci.sh --fast           skip building/booting the production image
#   scripts/ci.sh --dump FILE.sql  also migrate a restored copy of a real pg_dump
#
# Steps: ruff → shell syntax → compose config → throwaway PostgreSQL 17 →
# pytest (unit + Alembic migrations + app smoke tests) → Android app unit tests
# (when an Android SDK is installed) → production image:
# `alembic upgrade head` on the v2 schema + gunicorn boot + /healthz.
set -euo pipefail
cd "$(dirname "$0")/.."

FAST=0
DUMP=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast) FAST=1 ;;
        --dump) DUMP="${2:?--dump needs a file}"; shift ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
[[ -z "$DUMP" || -f "$DUMP" ]] || { echo "dump not found: $DUMP" >&2; exit 2; }

START=$SECONDS
VENV="${CI_VENV:-.venv-ci}"
PG_NAME="emb-ci-pg-$$"
APP_NAME="emb-ci-app-$$"
IMAGE="eticmonts:ci"

step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✗ CI FAILED: %s\033[0m\n' "$*" >&2; exit 1; }
cleanup() { docker rm -f "$PG_NAME" "$APP_NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
free_port() { "$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }
psql_ci() { docker exec -i "$PG_NAME" psql -q -v ON_ERROR_STOP=1 -U eticmont "$@"; }

# ------------------------------------------------------------------ python
step "Python environment ($VENV)"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -m pip install -q --disable-pip-version-check -r requirements-dev.txt

# ------------------------------------------------------------------ static checks
step "Lint (ruff)"
"$PY" -m ruff check .

step "Shell scripts"
for f in scripts/*.sh; do bash -n "$f"; done
echo "ok"

step "Compose files"
ENV_FILE=.env; [[ -f .env ]] || ENV_FILE=.env.example
docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" config -q 2>/dev/null \
    || { [[ -f .env ]] && fail "docker-compose.prod.yml is invalid"; echo "  (prod compose needs a .env — skipped)"; }
docker compose -f docker-compose.yml config -q || fail "docker-compose.yml is invalid"
echo "ok"

# ------------------------------------------------------------------ database
step "Throwaway PostgreSQL 17"
PG_PORT="$(free_port)"
docker run -d --name "$PG_NAME" -e POSTGRES_USER=eticmont -e POSTGRES_PASSWORD=eticmont \
    -e POSTGRES_DB=eticmont -p "127.0.0.1:$PG_PORT:5432" --tmpfs /var/lib/postgresql/data \
    postgres:17 >/dev/null
for _ in $(seq 1 60); do
    docker logs "$PG_NAME" 2>&1 | grep -q "PostgreSQL init process complete" \
        && docker exec "$PG_NAME" pg_isready -q -U eticmont && break
    sleep 0.5
done
docker exec "$PG_NAME" pg_isready -q -U eticmont || fail "PostgreSQL did not start"
echo "listening on 127.0.0.1:$PG_PORT"

if [[ -n "$DUMP" ]]; then
    step "Restore real dump ($DUMP)"
    psql_ci -d postgres -c "CREATE DATABASE emb_dump"
    psql_ci -d emb_dump < "$DUMP" >/dev/null
    export EMB_TEST_DUMP_DB=emb_dump
fi

# ------------------------------------------------------------------ tests
step "Tests: unit + migrations + smoke"
TEST_POSTGRES_PORT="$PG_PORT" "$PY" -m pytest -q

step "Android app (EMB Relais): unit tests + debug build"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
if [[ -d "$SDK/platforms" ]] && command -v java >/dev/null; then
    (cd android && ANDROID_HOME="$SDK" ./gradlew --console=plain -q :app:testDebugUnitTest :app:assembleDebug)
    echo "ok"
else
    echo "  (no Android SDK in $SDK — skipped)"
fi

# ------------------------------------------------------------------ image
if [[ "$FAST" == 0 ]]; then
    step "Production image"
    docker build -q -t "$IMAGE" . >/dev/null
    echo "built $IMAGE"

    step "Image: migrate the v2 schema, boot gunicorn, /healthz"
    psql_ci -d postgres -c "CREATE DATABASE emb_image"
    psql_ci -d emb_image < tests/fixtures/v2_schema.sql
    psql_ci -d emb_image < tests/fixtures/v2_sample_data.sql
    APP_PORT="$(free_port)"
    ENVS=(-e FLASK_ENV=production -e SECRET_KEY=ci -e SESSION_COOKIE_SECURE=0
          -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_PORT="$PG_PORT" -e POSTGRES_DB=emb_image
          -e POSTGRES_USER=eticmont -e POSTGRES_PASSWORD=eticmont -e FEATURES=cout_revient
          -e BOOTSTRAP_ADMIN_USER=a)
    docker run --rm --network host "${ENVS[@]}" "$IMAGE" alembic upgrade head
    docker run -d --name "$APP_NAME" --network host "${ENVS[@]}" \
        -e GUNICORN_CMD_ARGS="--bind 127.0.0.1:$APP_PORT" "$IMAGE" >/dev/null
    body=""
    for _ in $(seq 1 40); do
        body="$(curl -fsS "http://127.0.0.1:$APP_PORT/healthz" 2>/dev/null)" && break
        sleep 0.5
    done
    [[ -n "$body" ]] || { docker logs "$APP_NAME" | tail -40; fail "image did not become healthy"; }
    echo "  /healthz → $body"
    for path in /login /static/style.css /static/js/app.js; do
        code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$APP_PORT$path")"
        [[ "$code" == 200 ]] || fail "$path → HTTP $code"
        echo "  $path → $code"
    done
    if docker logs "$APP_NAME" 2>&1 | grep -E "Traceback|\[ERROR\]"; then
        fail "errors in gunicorn logs"
    fi
fi

printf '\n\033[1;32m✓ CI passed in %ss\033[0m\n' "$((SECONDS - START))"
