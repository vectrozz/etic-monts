"""Marketplace: products, stocks, clients, orders, tournées, recurrent deliveries.

Tables are created even when the module is disabled (FEATURES); they stay empty.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import bindparam
from sqlalchemy import text as sa_text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = [
    """CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) NOT NULL UNIQUE,
            category VARCHAR(60),
            unit VARCHAR(20) NOT NULL DEFAULT 'kg',
            unit_weight_kg DECIMAL(10,3),
            unit_volume_l DECIMAL(10,3),
            default_price DECIMAL(10,2),
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );""",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS emoji VARCHAR(10);",
    """CREATE TABLE IF NOT EXISTS stocks (
            id SERIAL PRIMARY KEY,
            producteur_id INT NOT NULL REFERENCES fermes(id) ON DELETE CASCADE,
            product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            cycle_date DATE,
            quantity_available DECIMAL(12,3) NOT NULL DEFAULT 0,
            quantity_reserved DECIMAL(12,3) NOT NULL DEFAULT 0,
            price DECIMAL(10,2),
            notes TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (quantity_available >= 0),
            CHECK (quantity_reserved >= 0)
        );""",
    "CREATE INDEX IF NOT EXISTS idx_stocks_cycle ON stocks(cycle_date);",
    "CREATE INDEX IF NOT EXISTS idx_stocks_producteur ON stocks(producteur_id);",
    "ALTER TABLE stocks ALTER COLUMN cycle_date DROP NOT NULL;",
    "ALTER TABLE stocks DROP CONSTRAINT IF EXISTS stocks_producteur_id_product_id_cycle_date_key;",
    "CREATE UNIQUE INDEX IF NOT EXISTS stocks_cycle_uniq ON stocks (producteur_id, product_id, cycle_date) WHERE cycle_date IS NOT NULL;",
    "CREATE UNIQUE INDEX IF NOT EXISTS stocks_pool_uniq ON stocks (producteur_id, product_id) WHERE cycle_date IS NULL;",
    """CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            contact_name VARCHAR(120),
            email VARCHAR(160),
            phone VARCHAR(40),
            address TEXT,
            postal_code VARCHAR(20),
            city VARCHAR(120),
            lat DECIMAL(9,6),
            lng DECIMAL(9,6),
            order_token VARCHAR(64) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );""",
    """CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            client_id INT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
            cycle_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            notes TEXT,
            total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
            total_weight_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
            total_volume_l DECIMAL(12,3) NOT NULL DEFAULT 0,
            tournee_id INT,
            tournee_position INT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP,
            delivered_at TIMESTAMP,
            CHECK (status IN ('pending','confirmed','prepared','delivered','cancelled'))
        );""",
    "CREATE INDEX IF NOT EXISTS idx_orders_cycle ON orders(cycle_date);",
    "CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_tournee ON orders(tournee_id);",
    """CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            stock_id INT NOT NULL REFERENCES stocks(id) ON DELETE RESTRICT,
            product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            producteur_id INT NOT NULL REFERENCES fermes(id) ON DELETE RESTRICT,
            quantity DECIMAL(12,3) NOT NULL CHECK (quantity > 0),
            unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
            line_total DECIMAL(12,2) NOT NULL DEFAULT 0
        );""",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);",
    """CREATE TABLE IF NOT EXISTS tournees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            delivery_date DATE NOT NULL,
            driver VARCHAR(120),
            vehicle VARCHAR(120),
            start_address TEXT,
            start_lat DECIMAL(9,6),
            start_lng DECIMAL(9,6),
            status VARCHAR(20) NOT NULL DEFAULT 'planned',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (status IN ('planned','in_progress','done','cancelled'))
        );""",
    "CREATE INDEX IF NOT EXISTS idx_tournees_date ON tournees(delivery_date);",
    """CREATE TABLE IF NOT EXISTS recurrent_deliveries (
            id SERIAL PRIMARY KEY,
            name VARCHAR(80) NOT NULL,
            weekday SMALLINT NOT NULL CHECK (weekday >= 0 AND weekday <= 6),
            cutoff_weekday SMALLINT NOT NULL CHECK (cutoff_weekday >= 0 AND cutoff_weekday <= 6),
            cutoff_time TIME NOT NULL DEFAULT '20:00',
            default_driver VARCHAR(120),
            default_vehicle VARCHAR(120),
            vehicle_max_weight_kg DECIMAL(10,2),
            vehicle_max_volume_l DECIMAL(10,2),
            start_address TEXT,
            start_lat DECIMAL(9,6),
            start_lng DECIMAL(9,6),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (weekday)
        );""",
]

FOREIGN_KEYS = [
    """DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'orders_tournee_fk'
            ) THEN
                ALTER TABLE orders
                    ADD CONSTRAINT orders_tournee_fk FOREIGN KEY (tournee_id)
                    REFERENCES tournees(id) ON DELETE SET NULL;
            END IF;
        END $$;""",
]

DEFAULT_SETTINGS = {
    "delivery_cycle": {
        "delivery_weekdays": [
            1,
            4
        ],
        "cutoff_weekdays": [
            0,
            3
        ],
        "cutoff_time": "20:00",
        "min_order_amount": 0,
        "vehicle_max_weight_kg": 800,
        "vehicle_max_volume_l": 3000,
        "client_can_cancel": True
    },
    "client_max_upcoming_slots": {
        "value": 2
    }
}


DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def upgrade() -> None:
    for stmt in TABLES + FOREIGN_KEYS:
        op.execute(stmt)
    for key, value in DEFAULT_SETTINGS.items():
        op.execute(
            sa_text("INSERT INTO app_settings (key, value) VALUES (:k, CAST(:v AS jsonb)) "
                    "ON CONFLICT (key) DO NOTHING").bindparams(k=key, v=json.dumps(value))
        )
    _seed_recurrent_deliveries()


def _seed_recurrent_deliveries() -> None:
    """Seed recurrent_deliveries from the delivery_cycle setting when empty."""
    bind = op.get_bind()
    if bind.execute(sa_text("SELECT COUNT(*) FROM recurrent_deliveries")).scalar():
        return
    row = bind.execute(sa_text("SELECT value FROM app_settings WHERE key = 'delivery_cycle'")).first()
    if not row:
        return
    legacy = row[0]
    delivery_wds = legacy.get("delivery_weekdays") or []
    cutoff_wds = legacy.get("cutoff_weekdays") or []
    for i, wd in enumerate(delivery_wds):
        cw = cutoff_wds[i] if i < len(cutoff_wds) else (wd - 1) % 7
        bind.execute(
            sa_text("INSERT INTO recurrent_deliveries (name, weekday, cutoff_weekday, cutoff_time, "
                    "vehicle_max_weight_kg, vehicle_max_volume_l) "
                    "VALUES (:n, :wd, :cw, :ct, :mw, :mv) ON CONFLICT (weekday) DO NOTHING"),
            {"n": f"Livraison {DAY_NAMES[wd]}", "wd": wd, "cw": cw,
             "ct": legacy.get("cutoff_time") or "20:00",
             "mw": legacy.get("vehicle_max_weight_kg"), "mv": legacy.get("vehicle_max_volume_l")},
        )


def downgrade() -> None:
    for table in ("recurrent_deliveries", "order_items", "orders", "tournees",
                  "clients", "stocks", "products"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute(sa_text("DELETE FROM app_settings WHERE key IN :keys").bindparams(
        bindparam("keys", value=tuple(DEFAULT_SETTINGS), expanding=True)))
