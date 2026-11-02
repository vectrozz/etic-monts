"""Shared test fixtures.

Database tests (marked ``db``) need a PostgreSQL server they may create and
drop databases on — never production. ``scripts/ci.sh`` starts a throwaway
container and sets TEST_POSTGRES_PORT; without it those tests are skipped.

Each database used by a test is created from scratch (``emb_test_<random>``)
and dropped afterwards.
"""
from __future__ import annotations

import os
import pathlib
import uuid

import psycopg2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

PG = {
    "host": os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1"),
    "port": os.environ.get("TEST_POSTGRES_PORT", ""),
    "user": os.environ.get("TEST_POSTGRES_USER", "eticmont"),
    "password": os.environ.get("TEST_POSTGRES_PASSWORD", "eticmont"),
}
HAS_DB = bool(PG["port"])


def pytest_collection_modifyitems(config, items):
    if HAS_DB:
        return
    skip = pytest.mark.skip(reason="no test PostgreSQL (set TEST_POSTGRES_PORT or run scripts/ci.sh)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def connect(dbname: str):
    return psycopg2.connect(dbname=dbname, **PG)


def create_database(prefix: str = "emb_test") -> str:
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    conn = connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()
    return name


def drop_database(name: str) -> None:
    conn = connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    conn.close()


def run_sql(dbname: str, sql: str, params=None) -> None:
    conn = connect(dbname)
    with conn, conn.cursor() as cur:
        cur.execute(sql, params)
    conn.close()


def run_sql_file(dbname: str, path: pathlib.Path) -> None:
    run_sql(dbname, path.read_text())


def query(dbname: str, sql: str, params=None) -> list[tuple]:
    conn = connect(dbname)
    with conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    return rows


def tables(dbname: str) -> set[str]:
    return {r[0] for r in query(dbname, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def columns(dbname: str, table: str) -> set[str]:
    return {r[0] for r in query(
        dbname, "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))}


def alembic_config(dbname: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["skip_logging"] = True
    cfg.attributes["database_url"] = URL.create(
        "postgresql+psycopg2", username=PG["user"], password=PG["password"],
        host=PG["host"], port=int(PG["port"]), database=dbname,
    )
    return cfg


def upgrade(dbname: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(dbname), revision)


def downgrade(dbname: str, revision: str) -> None:
    command.downgrade(alembic_config(dbname), revision)


def revision_of(dbname: str) -> str | None:
    if "alembic_version" not in tables(dbname):
        return None
    rows = query(dbname, "SELECT version_num FROM alembic_version")
    return rows[0][0] if rows else None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_db():
    name = create_database()
    yield name
    drop_database(name)


@pytest.fixture(scope="session")
def migrated_db():
    """The production path: v2 schema + data, then `alembic upgrade head`."""
    name = create_database("emb_app")
    run_sql_file(name, FIXTURES / "v2_schema.sql")
    run_sql_file(name, FIXTURES / "v2_sample_data.sql")
    upgrade(name)
    yield name
    from eticmonts.db import close_pool
    close_pool()
    drop_database(name)


@pytest.fixture(scope="session")
def make_app(migrated_db):
    """Build a Flask app bound to a test database: make_app(features=..., db=...)."""
    def _make(features: str = "cout_revient", db: str | None = None, **env):
        os.environ.update({
            "POSTGRES_HOST": PG["host"], "POSTGRES_PORT": PG["port"],
            "POSTGRES_USER": PG["user"], "POSTGRES_PASSWORD": PG["password"],
            "POSTGRES_DB": db or migrated_db,
            "FEATURES": features, "FLASK_ENV": "development", "SECRET_KEY": "test",
            "BOOTSTRAP_ADMIN_USER": "a",
        })
        os.environ.pop("SKIP_SCHEMA_CHECK", None)
        os.environ.update(env)
        from eticmonts.db import close_pool
        close_pool()
        from eticmonts import create_app
        app = create_app()
        app.testing = True
        return app
    return _make
