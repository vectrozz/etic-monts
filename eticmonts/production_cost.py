"""Coût de revient par culture — model, calculation and storage.

One row per farm × crop × campaign year in ``production_cost``:

    nb_units, surface_m2, variety, system,      → the crop itself
    yield_kg, sale_price,                       → what was sold, at what price
    hourly_cost, tasks {task: hours},           → labour
    charges {item: €}                           → inputs + structure costs

The calculation (`compute`) is a pure function so it can be unit-tested and
mirrored 1:1 by the live preview in ``static/js/cout-revient.js``.

Crops are declared in code (``CROPS``). Only strawberries ship for now; adding
a crop = adding a ``CropDef`` with its own task list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

from .db import execute


# ---------------------------------------------------------------------------
# Crop definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    key: str
    label: str
    hint: str = ""


@dataclass(frozen=True)
class CropDef:
    slug: str
    label: str
    emoji: str
    unit_label: str                      # what nb_units counts ("plants")
    systems: tuple[tuple[str, str], ...]
    tasks: tuple[Item, ...]              # labour, in hours
    inputs: tuple[Item, ...]             # charges opérationnelles, in €
    structure: tuple[Item, ...]          # charges de structure, in € / year

    @property
    def charge_keys(self) -> tuple[str, ...]:
        return tuple(i.key for i in self.inputs + self.structure)

    def to_js(self) -> dict:
        return {
            "tasks": [i.key for i in self.tasks],
            "inputs": [i.key for i in self.inputs],
            "structure": [i.key for i in self.structure],
            "harvestTask": "recolte",
        }


FRAISE = CropDef(
    slug="fraise",
    label="Fraise",
    emoji="🍓",
    unit_label="plants",
    systems=(
        ("plein_champ", "Plein champ"),
        ("abri", "Sous abri froid (tunnel)"),
        ("hors_sol", "Hors-sol"),
    ),
    tasks=(
        Item("preparation", "Préparation du sol"),
        Item("amendement", "Amendement"),
        Item("paillage", "Paillage"),
        Item("installation_irrigation", "Installation de l'irrigation"),
        Item("plantation", "Plantation"),
        Item("couverture", "Couverture (voile, bâche)"),
        Item("debachage", "Débâchage"),
        Item("desherbage", "Désherbage"),
        Item("nettoyage", "Nettoyage"),
        Item("ecoeurage", "Écœurage"),
        Item("effleurage", "Effleurage, déstolonnage"),
        Item("gestion_climatique", "Gestion climatique (aération)"),
        Item("surveillance_phyto", "Surveillance sanitaire"),
        Item("traitement_phyto", "Traitements, lâchers d'auxiliaires"),
        Item("recolte", "Récolte", "cueillette + mise en barquette"),
        Item("demontage", "Démontage, fin de culture"),
        Item("autres_travaux", "Autres travaux"),
    ),
    inputs=(
        Item("plants", "Plants", "frigo, mottes, trayplants…"),
        Item("substrat", "Substrat, terreau"),
        Item("fertilisation", "Engrais, amendements"),
        Item("paillage_voiles", "Paillage, voiles, bâches"),
        Item("irrigation", "Irrigation (gaines, eau)"),
        Item("protection", "Protection des cultures", "auxiliaires, produits"),
        Item("pollinisation", "Pollinisation (bourdons)"),
        Item("emballages", "Emballages (barquettes, plateaux)"),
        Item("energie", "Carburant, énergie"),
        Item("autres_intrants", "Autres intrants"),
    ),
    structure=(
        Item("amort_abris", "Amortissement abris, tunnels", "part affectée à la fraise"),
        Item("amort_irrigation", "Amortissement matériel d'irrigation"),
        Item("amort_materiel", "Amortissement autre matériel"),
        Item("commercialisation", "Frais de commercialisation", "transport, commissions"),
        Item("autres_structure", "Autres frais", "assurance, certification, foncier…"),
    ),
)

CROPS: dict[str, CropDef] = {c.slug: c for c in (FRAISE,)}

# Minimum number of farms before network medians are shown (anonymity).
MIN_PEERS = 3


def known_crops() -> list[dict]:
    return [{"slug": c.slug, "label": c.label, "emoji": c.emoji} for c in CROPS.values()]


def get_crop(slug: str) -> CropDef | None:
    return CROPS.get(slug)


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _pos(v: Any) -> float | None:
    f = _num(v)
    return f if f is not None and f > 0 else None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sum(values: Iterable[Any]) -> float:
    return sum(f for f in (_num(v) for v in values) if f is not None)


def compute(entry: dict, crop: CropDef) -> dict:
    """Derive every indicator of a campaign. Missing inputs give ``None``."""
    tasks = entry.get("tasks") or {}
    charges = entry.get("charges") or {}

    plants = _pos(entry.get("nb_units"))
    surface = _pos(entry.get("surface_m2"))
    yield_kg = _pos(entry.get("yield_kg"))
    price = _pos(entry.get("sale_price"))
    rate = _pos(entry.get("hourly_cost"))

    hours = _sum(tasks.get(t.key) for t in crop.tasks)
    harvest_h = _pos(tasks.get("recolte"))
    inputs = _sum(charges.get(i.key) for i in crop.inputs)
    structure = _sum(charges.get(i.key) for i in crop.structure)

    labour = hours * rate if rate is not None else None
    total = (labour or 0.0) + inputs + structure
    revenue = yield_kg * price if (yield_kg is not None and price is not None) else None
    cost_per_kg = _div(total, yield_kg) if total > 0 else None

    def share(part: float | None) -> float | None:
        return part / total * 100 if (part is not None and total > 0) else None

    missing = [label for value, label in (
        (plants, "nombre de plants"),
        (surface, "surface"),
        (yield_kg, "récolte commercialisée"),
        (price, "prix de vente"),
        (rate, "coût horaire"),
    ) if value is None]
    if hours == 0:
        missing.append("temps de travail")

    return {
        "hours_total": hours,
        "hours_per_1000m2": _div(hours * 1000, surface) if hours else None,
        "minutes_per_plant": _div(hours * 60, plants) if hours else None,
        "harvest_kg_per_hour": _div(yield_kg, harvest_h),
        "labour_cost": labour,
        "labour_included": rate is not None,
        "inputs_total": inputs,
        "structure_total": structure,
        "total_cost": total,
        "cost_per_kg": cost_per_kg,
        "cost_per_plant": _div(total, plants) if total > 0 else None,
        "cost_per_m2": _div(total, surface) if total > 0 else None,
        "yield_per_plant_g": _div(yield_kg * 1000, plants) if yield_kg else None,
        "yield_per_m2": _div(yield_kg, surface),
        "revenue": revenue,
        "margin": revenue - total if revenue is not None else None,
        "margin_per_kg": (price - cost_per_kg) if (price is not None and cost_per_kg is not None) else None,
        # What one hour of work actually earned once inputs and structure are paid.
        "hourly_return": _div(revenue - inputs - structure, hours) if (revenue is not None and hours) else None,
        "share_labour": share(labour),
        "share_inputs": share(inputs),
        "share_structure": share(structure),
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_COLUMNS = ("id, linked_id, year, nb_units, surface_m2, variety, system, yield_kg, "
            "sale_price, hourly_cost, tasks, charges, notes, updated_at")


def _row_to_entry(r: dict) -> dict:
    d = dict(r)
    for k in ("surface_m2", "yield_kg", "sale_price", "hourly_cost"):
        d[k] = float(d[k]) if d.get(k) is not None else None
    d["tasks"] = d.get("tasks") or {}
    d["charges"] = d.get("charges") or {}
    return d


def list_for_farm(farm_id: int, crop: str) -> list[dict]:
    rows = execute(
        f"SELECT {_COLUMNS} FROM production_cost "
        "WHERE linked_id = %s AND crop = %s ORDER BY year",
        (farm_id, crop), fetch="all", dict_rows=True,
    ) or []
    return [_row_to_entry(r) for r in rows]


def list_all(crop: str) -> list[dict]:
    rows = execute(
        f"SELECT pc.{_COLUMNS.replace(', ', ', pc.')}, f.farmname, f.name AS login "
        "FROM production_cost pc JOIN fermes f ON f.id = pc.linked_id "
        "WHERE pc.crop = %s ORDER BY pc.year DESC, f.farmname",
        (crop,), fetch="all", dict_rows=True,
    ) or []
    return [_row_to_entry(r) for r in rows]


def upsert(*, farm_id: int, crop: str, year: int, nb_units: int | None,
           surface_m2: float | None, variety: str | None, system: str | None,
           yield_kg: float | None, sale_price: float | None,
           hourly_cost: float | None, tasks: dict, charges: dict,
           notes: str | None) -> bool:
    """Insert or update a campaign. Returns True when a new row was created."""
    row = execute(
        "INSERT INTO production_cost (linked_id, crop, year, nb_units, surface_m2, "
        "variety, system, yield_kg, sale_price, hourly_cost, tasks, charges, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) "
        "ON CONFLICT (linked_id, crop, year) DO UPDATE SET "
        "nb_units = EXCLUDED.nb_units, surface_m2 = EXCLUDED.surface_m2, "
        "variety = EXCLUDED.variety, system = EXCLUDED.system, "
        "yield_kg = EXCLUDED.yield_kg, sale_price = EXCLUDED.sale_price, "
        "hourly_cost = EXCLUDED.hourly_cost, tasks = EXCLUDED.tasks, "
        "charges = EXCLUDED.charges, notes = EXCLUDED.notes, "
        "updated_at = CURRENT_TIMESTAMP "
        "RETURNING (xmax = 0) AS inserted",
        (farm_id, crop, year, nb_units, surface_m2, variety, system, yield_kg,
         sale_price, hourly_cost, json.dumps(tasks), json.dumps(charges), notes),
        fetch="one",
    )
    return bool(row and row[0])


def delete(cost_id: int, farm_id: int) -> bool:
    row = execute(
        "DELETE FROM production_cost WHERE id = %s AND linked_id = %s RETURNING year",
        (cost_id, farm_id), fetch="one",
    )
    return row is not None


# ---------------------------------------------------------------------------
# Network comparison
# ---------------------------------------------------------------------------

BENCHMARK_KEYS = ("cost_per_kg", "hours_per_1000m2", "yield_per_m2",
                  "harvest_kg_per_hour", "hourly_return")


def network_benchmark(crop: CropDef) -> dict[int, dict]:
    """Per year: medians of the key indicators across farms (≥ MIN_PEERS farms)."""
    by_year: dict[int, list[dict]] = {}
    for e in list_all(crop.slug):
        by_year.setdefault(e["year"], []).append(compute(e, crop))
    out: dict[int, dict] = {}
    for year, results in by_year.items():
        if len(results) < MIN_PEERS:
            continue
        stats: dict[str, Any] = {"n": len(results)}
        for k in BENCHMARK_KEYS:
            vals = [r[k] for r in results if r[k] is not None]
            stats[k] = median(vals) if len(vals) >= MIN_PEERS else None
        out[year] = stats
    return out
