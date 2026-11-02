"""WhatsApp relay: phones that forward group messages, raw messages, sender → farm.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""
from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS relay_devices (
        id SERIAL PRIMARY KEY,
        name VARCHAR(80) NOT NULL,
        token_hash CHAR(64) NOT NULL UNIQUE,          -- sha256 hex of the bearer token
        created_by INT REFERENCES fermes(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ,
        last_app_version VARCHAR(40),
        revoked_at TIMESTAMPTZ
    );

    -- How a sender appears on the relay phone (contact name or number) → farm.
    CREATE TABLE IF NOT EXISTS chat_senders (
        id SERIAL PRIMARY KEY,
        sender_name VARCHAR(160) NOT NULL UNIQUE,
        ferme_id INT REFERENCES fermes(id) ON DELETE SET NULL,
        ignored BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id BIGSERIAL PRIMARY KEY,
        device_id INT REFERENCES relay_devices(id) ON DELETE SET NULL,
        source VARCHAR(20) NOT NULL DEFAULT 'whatsapp',
        chat_title VARCHAR(160) NOT NULL,
        sender_name VARCHAR(160) NOT NULL,
        body TEXT NOT NULL,
        posted_at TIMESTAMPTZ NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        dedup_key CHAR(64) NOT NULL UNIQUE,
        status VARCHAR(20) NOT NULL DEFAULT 'new',
        CHECK (status IN ('new', 'done', 'ignored'))
    );
    CREATE INDEX IF NOT EXISTS idx_chat_messages_posted ON chat_messages (posted_at DESC);
    CREATE INDEX IF NOT EXISTS idx_chat_messages_sender ON chat_messages (sender_name, posted_at DESC);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS chat_messages;
    DROP TABLE IF EXISTS chat_senders;
    DROP TABLE IF EXISTS relay_devices;
    """)
