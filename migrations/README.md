# Migrations (Alembic)

Hand-written SQL migrations — the app uses psycopg2 directly, there are no
ORM models and no autogenerate.

```bash
alembic upgrade head            # apply pending migrations
alembic current                 # revision of the database
alembic history --verbose
alembic revision -m "add xyz"   # new file in migrations/versions/, numbered by hand (0005_…)
alembic upgrade head --sql      # print the SQL without running it
```

Production: `docker compose -f docker-compose.prod.yml run --rm app-flask alembic upgrade head`
(done by `scripts/deploy.sh`). The app refuses to start when the database is not at
the head revision (`SKIP_SCHEMA_CHECK=1` to bypass, e.g. for a one-off shell).

## Rules

1. **Never edit a migration that has run in production.** Add a new one.
2. Keep `upgrade()` idempotent when it is cheap (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
3. Always write `downgrade()`; `scripts/ci.sh` runs upgrade → downgrade → upgrade.
4. Name files `NNNN_short_slug.py` with `revision = "NNNN"` to keep history readable.

## History

| Rev | Content |
|---|---|
| 0001 | v2 baseline — legacy MAEC tables (`CREATE TABLE IF NOT EXISTS`: no-op on the v2 prod DB) |
| 0002 | v3 core — roles/profile columns on `fermes`, UNIQUE(`fermes.name`), `app_settings`, `catalog_items` |
| 0003 | coût de revient — `production_cost` |
| 0004 | marketplace — products, stocks, clients, orders, tournées, recurrent deliveries |

Databases created before Alembic (the v2 production database, early v3 dev
databases) have no `alembic_version` table: `alembic upgrade head` runs every
revision from 0001, and the idempotent statements adopt them in place.
