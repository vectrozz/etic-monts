"""Relay security: hardware-bound device keys, one-time pairing, replay and rate limits.

The pairing token becomes single-use (it only registers the phone's public
key); every later request is signed with the phone's Android Keystore key.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS public_key TEXT;            -- base64 DER SubjectPublicKeyInfo (EC P-256)
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS key_hardware VARCHAR(20);  -- strongbox | tee | software
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ;
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS pairing_expires_at TIMESTAMPTZ;
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS rate_window_start TIMESTAMPTZ;
    ALTER TABLE relay_devices ADD COLUMN IF NOT EXISTS rate_window_count INT NOT NULL DEFAULT 0;
    -- devices created before this revision never had a key: their pairing code expires now
    UPDATE relay_devices SET pairing_expires_at = now() WHERE public_key IS NULL AND pairing_expires_at IS NULL;

    CREATE TABLE IF NOT EXISTS relay_nonces (
        device_id INT NOT NULL REFERENCES relay_devices(id) ON DELETE CASCADE,
        nonce VARCHAR(64) NOT NULL,
        seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (device_id, nonce)
    );
    CREATE INDEX IF NOT EXISTS idx_relay_nonces_seen ON relay_nonces (seen_at);
    CREATE INDEX IF NOT EXISTS idx_chat_messages_device_received ON chat_messages (device_id, received_at);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS idx_chat_messages_device_received;
    DROP TABLE IF EXISTS relay_nonces;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS rate_window_count;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS rate_window_start;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS pairing_expires_at;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS registered_at;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS key_hardware;
    ALTER TABLE relay_devices DROP COLUMN IF EXISTS public_key;
    """)
