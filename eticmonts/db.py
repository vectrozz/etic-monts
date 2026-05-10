"""Database connection helpers.

Uses a small psycopg2 connection pool so handlers don't open/close raw
connections on every request. The pool is created lazily on first use.
"""
from __future__ import annotations

import contextlib
import threading
from typing import Any, Iterable, Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from .config import Config

_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def init_pool(config: Config, minconn: int = 1, maxconn: int = 10) -> None:
    """Initialise the global connection pool. Idempotent."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            return
        _pool = ThreadedConnectionPool(
            minconn,
            maxconn,
            database=config.db_name,
            host=config.db_host,
            user=config.db_user,
            password=config.db_password,
            port=config.db_port,
        )


def _get_pool() -> ThreadedConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised; call init_pool() at app startup")
    return _pool


@contextlib.contextmanager
def get_conn():
    """Context manager that yields a pooled connection and returns it after use."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextlib.contextmanager
def cursor(dict_rows: bool = False, commit: bool = True):
    """Yield a cursor inside a transaction. Commits on success, rolls back on error."""
    with get_conn() as conn:
        factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def execute(query: str, params: Optional[Iterable[Any]] = None,
            fetch: Optional[str] = None, dict_rows: bool = False):
    """Single-shot helper. fetch in {None, 'one', 'all'}."""
    with cursor(dict_rows=dict_rows) as cur:
        cur.execute(query, params or ())
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        return None


def execute_many(query: str, seq_of_params: Iterable[Iterable[Any]]) -> None:
    with cursor() as cur:
        cur.executemany(query, list(seq_of_params))
