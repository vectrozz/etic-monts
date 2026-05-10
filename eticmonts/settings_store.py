"""Read/write JSONB-backed settings."""
from __future__ import annotations

import json
from typing import Any

from .db import execute


def get_setting(key: str, default: Any = None) -> Any:
    row = execute("SELECT value FROM app_settings WHERE key = %s", (key,), fetch="one")
    if row is None:
        return default
    return row[0]


def set_setting(key: str, value: Any) -> None:
    payload = json.dumps(value)
    execute(
        "INSERT INTO app_settings (key, value, updated_at) "
        "VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP",
        (key, payload),
    )


def all_settings() -> dict[str, Any]:
    rows = execute("SELECT key, value FROM app_settings ORDER BY key", fetch="all") or []
    return {k: v for k, v in rows}


def get_delivery_cycle() -> dict:
    return get_setting("delivery_cycle", {}) or {}


def get_branding() -> dict:
    return get_setting("branding", {}) or {}


def get_catalog_categories() -> list[str]:
    s = get_setting("catalog_categories", {}) or {}
    return list(s.get("items", []))


def get_client_max_upcoming_slots(default: int = 2) -> int:
    """Maximum number of upcoming deliveries shown to clients on the public order page."""
    s = get_setting("client_max_upcoming_slots", {}) or {}
    try:
        n = int(s.get("value", default))
    except (TypeError, ValueError):
        n = default
    return max(1, n)
