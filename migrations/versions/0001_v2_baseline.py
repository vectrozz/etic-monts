"""v2 baseline: legacy MAEC tables (fermes, surface, biodiv, coefbiodiv, …).

Uses CREATE TABLE IF NOT EXISTS so that running it on the existing v2
production database (created before Alembic) is a no-op.

Revision ID: 0001
Revises: None
Create Date: 2026-11-02
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = [
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


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)


def downgrade() -> None:
    raise RuntimeError("0001 is the baseline: refusing to drop the legacy MAEC tables.")
