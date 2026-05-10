"""Catalog of reusable values for free-text fields.

When a producteur fills in fields like "paillage" or "irrigation_fr", the
value is stored as JSONB on the legacy tables AND offered to the catalog so
that another user can pick from a datalist instead of retyping.

The set of categories is fixed: it mirrors the non-numeric (free-text) fields
of "Mon exploitation". Numeric/value fields (surfaces, hectares, scores, etc.)
do not need a catalog. See `EXPLOITATION_CATEGORIES` below.
"""
from __future__ import annotations

from typing import Iterable

from .db import execute


# (key, French label). Order = display order in the dropdown.
EXPLOITATION_CATEGORIES: list[tuple[str, str]] = [
    ("paillage",            "Paillage"),
    ("limitation_plastique","Limitation plastique"),
    ("emballage",           "Emballage"),
    ("analyse_sol",         "Analyse de sol / matière organique"),
    ("formation_sol",       "Formation sol"),
    ("pratique_sol",        "Pratique de conservation des sols"),
    ("irrigation",          "Matériel d'irrigation"),
    ("action_eau",          "Action de limitation eau"),
    ("lutte_achat",         "Lutte intégrée — Achat"),
    ("lutte_favorisation",  "Lutte intégrée — Favorisation"),
    ("lutte_formation",     "Lutte intégrée — Formation"),
]
EXPLOITATION_CATEGORY_KEYS: set[str] = {k for k, _ in EXPLOITATION_CATEGORIES}
_CATEGORY_LABEL: dict[str, str] = {k: v for k, v in EXPLOITATION_CATEGORIES}


def category_label(key: str) -> str:
    """Human-readable label for a category key (or the key itself if unknown)."""
    return _CATEGORY_LABEL.get(key, key)


def is_valid_exploitation_category(key: str) -> bool:
    return key in EXPLOITATION_CATEGORY_KEYS


def list_items(category: str | None = None) -> list[dict]:
    if category:
        rows = execute(
            "SELECT id, category, value, description, usage_count, created_at "
            "FROM catalog_items WHERE category = %s ORDER BY usage_count DESC, value ASC",
            (category,), fetch="all", dict_rows=True,
        ) or []
    else:
        rows = execute(
            "SELECT id, category, value, description, usage_count, created_at "
            "FROM catalog_items ORDER BY category ASC, usage_count DESC, value ASC",
            fetch="all", dict_rows=True,
        ) or []
    return [dict(r) for r in rows]


def values_by_category() -> dict[str, list[str]]:
    rows = execute(
        "SELECT category, value FROM catalog_items ORDER BY category, usage_count DESC, value",
        fetch="all",
    ) or []
    out: dict[str, list[str]] = {}
    for cat, val in rows:
        out.setdefault(cat, []).append(val)
    return out


def add_item(category: str, value: str, *, description: str = "",
             created_by: int | None = None) -> int | None:
    value = (value or "").strip()
    category = (category or "").strip()
    if not value or not category:
        return None
    row = execute(
        "INSERT INTO catalog_items (category, value, description, created_by) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (category, value) DO UPDATE SET description = EXCLUDED.description "
        "RETURNING id",
        (category, value, description or None, created_by),
        fetch="one",
    )
    return row[0] if row else None


def bump_usage(category: str, values: Iterable[str]) -> None:
    """Increment usage_count for any (category,value) pair, inserting if missing."""
    seen: set[str] = set()
    for raw in values:
        v = (raw or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        execute(
            "INSERT INTO catalog_items (category, value, usage_count) "
            "VALUES (%s, %s, 1) "
            "ON CONFLICT (category, value) DO UPDATE SET usage_count = catalog_items.usage_count + 1",
            (category, v),
        )


def update_item(item_id: int, *, value: str, description: str | None,
                category: str | None = None) -> bool:
    """Edit value/description (and optionally category). Returns True if updated."""
    value = (value or "").strip()
    if not value:
        return False
    if category:
        category = category.strip()
        execute(
            "UPDATE catalog_items SET value = %s, description = %s, category = %s "
            "WHERE id = %s",
            (value, description or None, category, item_id),
        )
    else:
        execute(
            "UPDATE catalog_items SET value = %s, description = %s WHERE id = %s",
            (value, description or None, item_id),
        )
    return True


def delete_item(item_id: int) -> None:
    execute("DELETE FROM catalog_items WHERE id = %s", (item_id,))
