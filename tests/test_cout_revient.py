"""Unit tests for the coût de revient calculation (no database needed)."""
from __future__ import annotations

import pytest

from eticmonts.production_cost import FRAISE, compute


def _entry(**kw):
    base = {
        "nb_units": 4000, "surface_m2": 1000, "yield_kg": 2000, "sale_price": 8.5,
        "hourly_cost": 15,
        "tasks": {"recolte": 300, "plantation": 100},
        "charges": {"plants": 1200, "emballages": 400, "amort_abris": 800},
    }
    base.update(kw)
    return base


def test_full_campaign():
    r = compute(_entry(), FRAISE)
    assert r["hours_total"] == 400
    assert r["labour_cost"] == 6000
    assert r["inputs_total"] == 1600
    assert r["structure_total"] == 800
    assert r["total_cost"] == 8400
    assert r["cost_per_kg"] == pytest.approx(4.2)
    assert r["margin_per_kg"] == pytest.approx(4.3)
    assert r["hours_per_1000m2"] == pytest.approx(400)
    assert r["cost_per_plant"] == pytest.approx(2.1)
    assert r["yield_per_plant_g"] == pytest.approx(500)
    assert r["yield_per_m2"] == pytest.approx(2.0)
    assert r["harvest_kg_per_hour"] == pytest.approx(2000 / 300)
    # (17 000 € revenue − 1 600 − 800) / 400 h
    assert r["hourly_return"] == pytest.approx(36.5)
    assert r["share_labour"] + r["share_inputs"] + r["share_structure"] == pytest.approx(100)
    assert r["missing"] == []


def test_without_hourly_cost_excludes_labour():
    r = compute(_entry(hourly_cost=None), FRAISE)
    assert r["labour_included"] is False
    assert r["labour_cost"] is None
    assert r["cost_per_kg"] == pytest.approx(2400 / 2000)
    assert "coût horaire" in r["missing"]


def test_empty_entry_is_safe():
    r = compute({}, FRAISE)
    assert r["cost_per_kg"] is None
    assert r["hours_per_1000m2"] is None
    assert r["hourly_return"] is None
    assert r["total_cost"] == 0
    assert "temps de travail" in r["missing"]


def test_zero_and_garbage_values_ignored():
    r = compute(_entry(surface_m2=0, yield_kg="", nb_units="abc",
                       tasks={"recolte": "x", "plantation": 10}), FRAISE)
    assert r["hours_total"] == 10
    assert r["hours_per_1000m2"] is None
    assert r["cost_per_kg"] is None
    assert r["yield_per_plant_g"] is None


def test_unknown_task_keys_not_counted():
    r = compute(_entry(tasks={"recolte": 10, "not_a_task": 999}), FRAISE)
    assert r["hours_total"] == 10


def test_negative_margin():
    r = compute(_entry(sale_price=3), FRAISE)
    assert r["margin_per_kg"] < 0
    assert r["margin"] < 0
