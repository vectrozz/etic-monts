"""Alembic migrations: fresh install, upgrade of the real v2 schema, round-trips."""
from __future__ import annotations

import os

import pytest

from conftest import (
    FIXTURES, columns, downgrade, query, revision_of, run_sql, run_sql_file, tables, upgrade,
)
from eticmonts.schema_version import expected_head


def test_single_linear_head():
    assert expected_head() == "0004"


@pytest.mark.db
def test_fresh_database_upgrade_downgrade_upgrade(fresh_db):
    upgrade(fresh_db)
    assert revision_of(fresh_db) == expected_head()
    assert {"fermes", "surface", "biodiv", "app_settings", "catalog_items",
            "production_cost", "products", "orders", "tournees"} <= tables(fresh_db)
    assert {"variety", "yield_kg", "sale_price", "hourly_cost", "charges"} <= columns(fresh_db, "production_cost")

    downgrade(fresh_db, "0001")
    assert revision_of(fresh_db) == "0001"
    assert not {"app_settings", "production_cost", "products"} & tables(fresh_db)
    assert "role" not in columns(fresh_db, "fermes")

    upgrade(fresh_db)
    assert revision_of(fresh_db) == expected_head()


@pytest.mark.db
def test_upgrade_from_v2_production_schema_keeps_data(fresh_db):
    run_sql_file(fresh_db, FIXTURES / "v2_schema.sql")
    run_sql_file(fresh_db, FIXTURES / "v2_sample_data.sql")
    before = {t: query(fresh_db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("fermes", "surface", "biodiv")}

    upgrade(fresh_db)

    assert revision_of(fresh_db) == expected_head()
    after = {t: query(fresh_db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in before}
    assert after == before
    assert query(fresh_db, "SELECT DISTINCT role, is_active FROM fermes") == [("producteur", True)]
    assert query(fresh_db, "SELECT conname FROM pg_constraint WHERE conname = 'fermes_name_key'")
    assert query(fresh_db, "SELECT value->>'name' FROM app_settings WHERE key = 'branding'") == [("Etic'Monts",)]

    upgrade(fresh_db)  # re-running is a no-op
    assert revision_of(fresh_db) == expected_head()


@pytest.mark.db
def test_unique_name_not_forced_when_duplicates_exist(fresh_db):
    run_sql_file(fresh_db, FIXTURES / "v2_schema.sql")
    run_sql(fresh_db, "INSERT INTO fermes (name) VALUES ('doublon'), ('doublon')")
    upgrade(fresh_db)
    assert revision_of(fresh_db) == expected_head()
    assert not query(fresh_db, "SELECT 1 FROM pg_constraint WHERE conname = 'fermes_name_key'")


@pytest.mark.db
def test_adopts_pre_alembic_v3_dev_database(fresh_db):
    """Early v3 dev databases were built by the old start-up bootstrap: older
    production_cost/products shapes and a customised branding row."""
    run_sql_file(fresh_db, FIXTURES / "v2_schema.sql")
    run_sql(fresh_db, """
        CREATE TABLE app_settings (key VARCHAR(80) PRIMARY KEY, value JSONB NOT NULL,
                                   updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO app_settings VALUES ('branding', '{"name": "Mon réseau"}');
        CREATE TABLE production_cost (
            id SERIAL PRIMARY KEY, linked_id INT NOT NULL REFERENCES fermes(id) ON DELETE CASCADE,
            crop VARCHAR(40) NOT NULL, year INTEGER NOT NULL, nb_units INTEGER,
            surface_m2 DECIMAL(10,2), tasks JSONB NOT NULL DEFAULT '{}', notes TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (linked_id, crop, year));
        CREATE TABLE products (id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE,
            category VARCHAR(60), unit VARCHAR(20) NOT NULL DEFAULT 'kg', unit_weight_kg DECIMAL(10,3),
            unit_volume_l DECIMAL(10,3), default_price DECIMAL(10,2), description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)
    upgrade(fresh_db)
    assert revision_of(fresh_db) == expected_head()
    assert {"charges", "yield_kg"} <= columns(fresh_db, "production_cost")
    assert "emoji" in columns(fresh_db, "products")
    assert query(fresh_db, "SELECT value->>'name' FROM app_settings WHERE key = 'branding'") == [("Mon réseau",)]


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("EMB_TEST_DUMP_DB"),
                    reason="set EMB_TEST_DUMP_DB (scripts/ci.sh --dump <file.sql>)")
def test_upgrade_real_production_dump():
    """Run by `scripts/ci.sh --dump backups/prod.sql` on a restored copy of prod."""
    db = os.environ["EMB_TEST_DUMP_DB"]
    data_tables = sorted(tables(db) - {"alembic_version"})
    before = {t: query(db, f'SELECT COUNT(*) FROM "{t}"')[0][0] for t in data_tables}
    upgrade(db)
    assert revision_of(db) == expected_head()
    after = {t: query(db, f'SELECT COUNT(*) FROM "{t}"')[0][0] for t in data_tables}
    assert after == before, "row counts changed during migration"
