"""Per-crop production-cost data model (work hours per task per year).

Crops are now driven by the `products` table — adding a product in the
marketplace automatically makes it available under "Coût de production".
The slug used in URLs is the product id (string). The same default task
list applies to every crop; override per-product by extending
`CROP_TASK_OVERRIDES` keyed on product id.

Storage:
    production_cost(linked_id, crop, year, nb_units, surface_m2, tasks JSONB, notes)
    UNIQUE(linked_id, crop, year) — one row per farm × crop × year.
"""
from __future__ import annotations

import json

from .db import execute


# Default task list — works for most market-garden crops.
DEFAULT_TASKS: list[tuple[str, str]] = [
    ("preparation",          "Préparation du sol"),
    ("amendement",           "Amendement"),
    ("paillage",             "Paillage"),
    ("installation_irrigation", "Installation irrigation"),
    ("plantation",           "Plantation"),
    ("couverture",           "Couverture"),
    ("debachage",            "Débachage"),
    ("desherbage",           "Désherbage"),
    ("nettoyage",            "Nettoyage"),
    ("ecoeurage",            "Écœurage"),
    ("effleurage",           "Effleurage, déstolonage, désherbage"),
    ("gestion_climatique",   "Gestion climatique"),
    ("surveillance_phyto",   "Surveillance phytosanitaire"),
    ("traitement_phyto",     "Traitement phytosanitaire"),
    ("recolte",              "Récolte"),
    ("demontage",            "Démontage"),
]


# Optional per-product task overrides (keyed on product id, as string).
# e.g. CROP_TASK_OVERRIDES["12"] = [(...), ...]
CROP_TASK_OVERRIDES: dict[str, list[tuple[str, str]]] = {}


# ---------------------------------------------------------------------------
# Crop registry — sourced from products table
# ---------------------------------------------------------------------------

def known_crops() -> list[dict]:
    """Return active products as crop entries: [{slug, label, unit, emoji}, ...]."""
    from .emoji_map import detect_emoji
    rows = execute(
        "SELECT id, name, unit, category, emoji FROM products WHERE is_active ORDER BY name",
        fetch="all", dict_rows=True,
    ) or []
    return [
        {
            "slug":  str(r["id"]),
            "label": r["name"],
            "unit":  r["unit"] or "unités",
            "emoji": r["emoji"] or detect_emoji(r["name"], r.get("category")),
        }
        for r in rows
    ]


def get_crop(slug: str) -> dict | None:
    """Resolve slug → crop definition. slug = product id (as string)."""
    if not slug:
        return None
    try:
        pid = int(slug)
    except ValueError:
        return None
    row = execute(
        "SELECT name, unit FROM products WHERE id = %s AND is_active",
        (pid,), fetch="one", dict_rows=True,
    )
    if not row:
        return None
    unit = row["unit"] or "unités"
    return {
        "label": row["name"],
        "unit_label": unit,
        "unit_label_full": unit.upper(),
        "tasks": CROP_TASK_OVERRIDES.get(slug, DEFAULT_TASKS),
    }


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def list_for_farm(farm_id: int, crop: str) -> list[dict]:
    rows = execute(
        "SELECT id, year, nb_units, surface_m2, tasks, notes "
        "FROM production_cost WHERE linked_id = %s AND crop = %s ORDER BY year",
        (farm_id, crop), fetch="all", dict_rows=True,
    ) or []
    out = []
    for r in rows:
        d = dict(r)
        d["tasks"] = d.get("tasks") or {}
        d["surface_m2"] = float(d["surface_m2"]) if d["surface_m2"] is not None else None
        out.append(d)
    return out


def upsert(*, farm_id: int, crop: str, year: int, nb_units: int | None,
           surface_m2: float | None, tasks: dict, notes: str | None) -> None:
    payload = json.dumps(tasks)
    execute(
        "INSERT INTO production_cost (linked_id, crop, year, nb_units, surface_m2, "
        "tasks, notes) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) "
        "ON CONFLICT (linked_id, crop, year) DO UPDATE SET "
        "nb_units = EXCLUDED.nb_units, surface_m2 = EXCLUDED.surface_m2, "
        "tasks = EXCLUDED.tasks, notes = EXCLUDED.notes, "
        "updated_at = CURRENT_TIMESTAMP",
        (farm_id, crop, year, nb_units, surface_m2, payload, notes or None),
    )


def delete(cost_id: int, farm_id: int) -> None:
    execute(
        "DELETE FROM production_cost WHERE id = %s AND linked_id = %s",
        (cost_id, farm_id),
    )


def total_hours(tasks: dict, crop_def: dict) -> float:
    total = 0.0
    for key, _ in crop_def["tasks"]:
        v = tasks.get(key)
        if v is None or v == "":
            continue
        try:
            total += float(v)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def hours_per_1000m2(total: float, surface_m2: float | None) -> float | None:
    if surface_m2 is None or surface_m2 <= 0:
        return None
    return round(total / surface_m2 * 1000, 2)
