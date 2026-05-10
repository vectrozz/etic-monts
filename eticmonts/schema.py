"""Database schema bootstrap. Idempotent CREATE TABLE / ALTER TABLE statements.

Existing tables (fermes, surface, biodiv, plastique, soil, water, lutte,
coefbiodiv) are preserved. New marketplace tables are added.
"""
from __future__ import annotations

from .db import cursor

LEGACY_TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS fermes (
        id SERIAL PRIMARY KEY,
        name VARCHAR(40) UNIQUE,
        userpass VARCHAR(200),
        farmname VARCHAR(120),
        adress VARCHAR(200),
        integration_year VARCHAR(8),
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_date TIMESTAMP
    );""",
    """CREATE TABLE IF NOT EXISTS surface (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        surftot DECIMAL(10,4),
        surffr DECIMAL(10,4),
        surfgf DECIMAL(10,4),
        surfleg DECIMAL(10,4),
        prairie DECIMAL(10,4),
        culture DECIMAL(10,4),
        surfautre DECIMAL(10,4)
    );""",
    """CREATE TABLE IF NOT EXISTS biodiv (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        haie DECIMAL(10,4),
        arbrealign DECIMAL(10,4),
        arbreseul DECIMAL(10,4),
        bosquet DECIMAL(10,4),
        mare DECIMAL(10,4),
        fosse DECIMAL(10,4),
        bordure DECIMAL(10,4),
        jachere DECIMAL(10,4),
        jacheremel DECIMAL(10,4),
        muret DECIMAL(10,4),
        description TEXT,
        biodivscore DECIMAL(10,4)
    );""",
    """CREATE TABLE IF NOT EXISTS coefbiodiv (
        id SERIAL PRIMARY KEY,
        year INTEGER CHECK (year >= 2010 AND year <= 2100) UNIQUE,
        coefhaie DECIMAL(10,4),
        coefarbrealign DECIMAL(10,4),
        coefarbreseul DECIMAL(10,4),
        coefbosquet DECIMAL(10,4),
        coefmare DECIMAL(10,4),
        coeffosse DECIMAL(10,4),
        coefbordure DECIMAL(10,4),
        coefjachere DECIMAL(10,4),
        coefjacheremel DECIMAL(10,4),
        coefmuret DECIMAL(10,4),
        coefprairie DECIMAL(10,4),
        description TEXT
    );""",
    """CREATE TABLE IF NOT EXISTS plastique (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        surftotplast DECIMAL(10,2),
        surftottoile DECIMAL(10,2),
        paillagefr JSONB,
        paillagegf JSONB,
        paillageleg JSONB,
        limitation JSONB,
        embplast JSONB,
        embplastpourcent DECIMAL(5,2) CHECK (embplastpourcent >= 0 AND embplastpourcent <= 100),
        embfr JSONB,
        embgf JSONB,
        embleg JSONB
    );""",
    """CREATE TABLE IF NOT EXISTS soil (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        soilanalyse JSONB,
        connaissance INTEGER CHECK (connaissance >= 0 AND connaissance <= 10),
        formation JSONB,
        pratique JSONB
    );""",
    """CREATE TABLE IF NOT EXISTS water (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        matosirrigfr JSONB,
        matosirriggf JSONB,
        matosirrigleg JSONB,
        consoeau DECIMAL(10,4),
        actions JSONB
    );""",
    """CREATE TABLE IF NOT EXISTS lutte (
        id SERIAL PRIMARY KEY,
        linked_id INT REFERENCES fermes(id) ON DELETE CASCADE,
        year INTEGER CHECK (year >= 2010 AND year <= 2100),
        achat JSONB,
        favorisation JSONB,
        formation JSONB
    );""",
]

LEGACY_ALTERS_SQL = [
    # Add role + active status to fermes (which is the user table). Defaults
    # keep legacy installs functional without disruption.
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'producteur';",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS contact_email VARCHAR(160);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(40);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS lat DECIMAL(9,6);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS lng DECIMAL(9,6);",
    "ALTER TABLE fermes ADD COLUMN IF NOT EXISTS photo_path VARCHAR(255);",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS emoji VARCHAR(10);",
]

MARKETPLACE_TABLES_SQL = [
    # ---------------- catalog: reusable values for free-text fields ---------
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

    # ---------------- products (vegetables) ---------------------------------
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

    # ---------------- stocks: producer x product, per delivery cycle --------
    # cycle_date NULL = season pool (drains across all upcoming deliveries).
    # Partial unique indexes keep one row per (producer, product) for pool,
    # and one per (producer, product, cycle_date) for cycle-specific stock.
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
    # Drop legacy NOT NULL + UNIQUE if they came from an older deploy
    "ALTER TABLE stocks ALTER COLUMN cycle_date DROP NOT NULL;",
    "ALTER TABLE stocks DROP CONSTRAINT IF EXISTS stocks_producteur_id_product_id_cycle_date_key;",
    "CREATE UNIQUE INDEX IF NOT EXISTS stocks_cycle_uniq "
    "ON stocks (producteur_id, product_id, cycle_date) WHERE cycle_date IS NOT NULL;",
    "CREATE UNIQUE INDEX IF NOT EXISTS stocks_pool_uniq "
    "ON stocks (producteur_id, product_id) WHERE cycle_date IS NULL;",

    # ---------------- clients ----------------------------------------------
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

    # ---------------- orders + order lines ----------------------------------
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

    # ---------------- tournees (delivery rounds) ----------------------------
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

    # ---------------- settings (key/value, JSON) ----------------------------
    """CREATE TABLE IF NOT EXISTS app_settings (
        key VARCHAR(80) PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );""",

    # ---------------- production cost (per crop, per year) -----------------
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

    # ---------------- recurrent deliveries (e.g. Mardi, Vendredi) -----------
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

ORDERS_FK_SQL = [
    # tournee_id FK is added after table creation to avoid forward reference issues
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
    END $$;"""
]


DEFAULT_SETTINGS = {
    # Legacy fallback when no recurrent_deliveries rows exist. Vehicle
    # capacity, client_can_cancel, min_order_amount stay here as global
    # cooperative-wide defaults.
    "delivery_cycle": {
        "delivery_weekdays": [1, 4],            # Mardi, Vendredi (fallback)
        "cutoff_weekdays": [0, 3],              # Lundi, Jeudi (fallback)
        "cutoff_time": "20:00",
        "min_order_amount": 0,
        "vehicle_max_weight_kg": 800,
        "vehicle_max_volume_l": 3000,
        "client_can_cancel": True,
    },
    # How many upcoming deliveries clients see in the public order page.
    "client_max_upcoming_slots": {"value": 2},
    "branding": {
        "name": "Etic'Monts",
        "subtitle": "Coopérative de producteurs",
        "support_email": "",
    },
    "catalog_categories": {
        "items": [
            "paillage", "limitation_plastique", "emballage",
            "irrigation", "pratique_sol", "formation_sol",
            "lutte_achat", "lutte_favorisation", "lutte_formation",
            "action_eau", "analyse_sol",
            "produit_categorie",
        ],
    },
}


# Arbitrary 64-bit constant for pg_advisory_lock — must be unique to this app.
_BOOTSTRAP_LOCK_KEY = 7651_4129_0420_2026


def bootstrap_schema() -> None:
    """Create tables and ensure default settings exist.

    Acquires a Postgres session-level advisory lock so that, when the app
    starts behind gunicorn with multiple workers, exactly one worker runs the
    DDL. The others wait, then no-op (every statement is idempotent).
    """
    import json

    with cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (_BOOTSTRAP_LOCK_KEY,))
        try:
            for stmt in LEGACY_TABLES_SQL:
                cur.execute(stmt)
            for stmt in LEGACY_ALTERS_SQL:
                cur.execute(stmt)
            for stmt in MARKETPLACE_TABLES_SQL:
                cur.execute(stmt)
            for stmt in ORDERS_FK_SQL:
                cur.execute(stmt)
            for key, value in DEFAULT_SETTINGS.items():
                cur.execute(
                    "INSERT INTO app_settings (key, value) VALUES (%s, %s::jsonb) "
                    "ON CONFLICT (key) DO NOTHING",
                    (key, json.dumps(value)),
                )
            # Seed recurrent_deliveries from legacy delivery_cycle if empty
            cur.execute("SELECT COUNT(*) FROM recurrent_deliveries")
            if cur.fetchone()[0] == 0:
                cur.execute("SELECT value FROM app_settings WHERE key = 'delivery_cycle'")
                row = cur.fetchone()
                if row:
                    legacy = row[0]
                    delivery_wds = legacy.get("delivery_weekdays") or []
                    cutoff_wds = legacy.get("cutoff_weekdays") or []
                    cutoff_time = legacy.get("cutoff_time") or "20:00"
                    max_w = legacy.get("vehicle_max_weight_kg")
                    max_v = legacy.get("vehicle_max_volume_l")
                    day_names = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
                    for i, wd in enumerate(delivery_wds):
                        cw = cutoff_wds[i] if i < len(cutoff_wds) else (wd - 1) % 7
                        cur.execute(
                            "INSERT INTO recurrent_deliveries (name, weekday, cutoff_weekday, "
                            "cutoff_time, vehicle_max_weight_kg, vehicle_max_volume_l) "
                            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (weekday) DO NOTHING",
                            (f"Livraison {day_names[wd]}", wd, cw, cutoff_time, max_w, max_v),
                        )
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_BOOTSTRAP_LOCK_KEY,))
