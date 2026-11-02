"""Coût de revient: production_cost (one row per farm × crop × campaign year).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS production_cost (
            id SERIAL PRIMARY KEY,
            linked_id INT NOT NULL REFERENCES fermes(id) ON DELETE CASCADE,
            crop VARCHAR(40) NOT NULL,
            year INTEGER NOT NULL CHECK (year >= 2010 AND year <= 2100),
            nb_units INTEGER,
            surface_m2 DECIMAL(10,2),
            tasks JSONB NOT NULL DEFAULT '{}',
            notes TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (linked_id, crop, year)
        );""",
    "CREATE INDEX IF NOT EXISTS idx_prodcost_farm_crop ON production_cost(linked_id, crop);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS variety VARCHAR(120);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS system VARCHAR(30);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS yield_kg DECIMAL(12,2);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS sale_price DECIMAL(10,2);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS hourly_cost DECIMAL(10,2);",
    "ALTER TABLE production_cost ADD COLUMN IF NOT EXISTS charges JSONB NOT NULL DEFAULT '{}';",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS production_cost")
