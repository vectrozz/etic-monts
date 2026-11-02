"""v3 core: roles and profile columns on fermes, UNIQUE(fermes.name) when
possible, app_settings and catalog_items, default branding settings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text as sa_text

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ALTERS = [
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'producteur';",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS contact_email VARCHAR(160);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(40);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS lat DECIMAL(9,6);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS lng DECIMAL(9,6);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS photo_path VARCHAR(255);",
    """DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'fermes'::regclass AND contype = 'u'
                  AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                      WHERE attrelid = 'fermes'::regclass
                                        AND attname = 'name')]::smallint[]
            ) AND NOT EXISTS (
                SELECT 1 FROM fermes GROUP BY name HAVING COUNT(*) > 1
            ) THEN
                ALTER TABLE fermes ADD CONSTRAINT fermes_name_key UNIQUE (name);
            END IF;
        END $$;""",
]

TABLES = [
    """CREATE TABLE IF NOT EXISTS catalog_items (
            id SERIAL PRIMARY KEY,
            category VARCHAR(60) NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            usage_count INTEGER NOT NULL DEFAULT 0,
            created_by INT REFERENCES fermes(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (category, value)
        );""",
    "CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog_items(category);",
    """CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(80) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );""",
]

DEFAULT_SETTINGS = {
    "branding": {
        "name": "Etic'Monts",
        "subtitle": "Coopérative de producteurs",
        "support_email": ""
    },
    "catalog_categories": {
        "items": [
            "paillage",
            "limitation_plastique",
            "emballage",
            "irrigation",
            "pratique_sol",
            "formation_sol",
            "lutte_achat",
            "lutte_favorisation",
            "lutte_formation",
            "action_eau",
            "analyse_sol",
            "produit_categorie"
        ]
    }
}


def upgrade() -> None:
    for stmt in ALTERS + TABLES:
        op.execute(stmt)
    for key, value in DEFAULT_SETTINGS.items():
        op.execute(
            sa_text("INSERT INTO app_settings (key, value) VALUES (:k, CAST(:v AS jsonb)) "
                    "ON CONFLICT (key) DO NOTHING").bindparams(k=key, v=json.dumps(value))
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog_items")
    op.execute("DROP TABLE IF EXISTS app_settings")
    # fermes_name_key is kept: fresh databases get it from the 0001 baseline.
    for col in ("photo_path", "lng", "lat", "contact_phone", "contact_email", "is_active", "role"):
        op.execute(f"ALTER TABLE fermes DROP COLUMN IF EXISTS {col}")
