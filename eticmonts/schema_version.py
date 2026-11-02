"""Database schema version guard (Alembic).

The schema is owned by Alembic (``migrations/``). The app never changes the
schema itself: at start-up it only checks that the database is at the head
revision shipped with the code, and refuses to start otherwise — a clear
error beats a 500 on the first page that touches a missing column.
"""
from __future__ import annotations

import os
from functools import lru_cache

from alembic.config import Config
from alembic.script import ScriptDirectory

from .db import execute

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ALEMBIC_INI = os.path.join(ROOT, "alembic.ini")


class SchemaOutOfDate(RuntimeError):
    pass


@lru_cache(maxsize=1)
def expected_head() -> str:
    script = ScriptDirectory.from_config(Config(ALEMBIC_INI))
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Alembic must have exactly one head, found {heads}")
    return heads[0]


def current_revision() -> str | None:
    exists = execute("SELECT to_regclass('public.alembic_version') IS NOT NULL", fetch="one")
    if not exists or not exists[0]:
        return None
    row = execute("SELECT version_num FROM alembic_version", fetch="one")
    return row[0] if row else None


def check_schema() -> str:
    """Return the current revision, or raise SchemaOutOfDate."""
    current, head = current_revision(), expected_head()
    if current != head:
        raise SchemaOutOfDate(
            f"Database schema is at {current or 'no Alembic revision'}, this code expects {head}. "
            "Run `alembic upgrade head` (prod: `docker compose -f docker-compose.prod.yml run --rm "
            "app-flask alembic upgrade head`)."
        )
    return current
