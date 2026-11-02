"""Alembic environment.

* Connection settings come from the POSTGRES_* environment variables (the
  same ones the app reads), so `alembic upgrade head` works identically in
  development, in CI and in the production container.
* Migrations are hand-written SQL (`op.execute`): the app has no ORM models,
  so there is no autogenerate.
* The whole upgrade runs in one transaction (PostgreSQL has transactional
  DDL) behind an advisory lock: a failing migration leaves the database
  untouched, and two concurrent `upgrade` calls cannot interleave.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text
from sqlalchemy.engine import URL

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

_LOCK_KEY = 7651_4129_0420_2026  # same key the app used for its old schema bootstrap


def database_url() -> URL:
    explicit = config.attributes.get("database_url")
    if explicit is not None:
        return explicit
    return URL.create(
        "postgresql+psycopg2",
        username=os.environ.get("POSTGRES_USER", "eticmont"),
        password=os.environ.get("POSTGRES_PASSWORD", "eticmont"),
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        database=os.environ.get("POSTGRES_DB", "eticmont"),
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(url=database_url().render_as_string(hide_password=True),
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None,
                          transaction_per_migration=False)
        with context.begin_transaction():
            connection.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
