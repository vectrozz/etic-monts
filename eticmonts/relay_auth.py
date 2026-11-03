"""Authentication of the « EMB Relais » Android app.

1. Pairing (once): the admin page gives a one-time code (24 h). The app
   creates an EC P-256 key pair inside the phone's secure hardware (Android
   Keystore: StrongBox or TEE — the private key can never be exported) and
   registers the PUBLIC key with that code. The code is then burnt.

2. Every request is signed with that hardware key:

       X-Relay-Device:    <device id>
       X-Relay-Timestamp: <unix epoch, milliseconds>
       X-Relay-Nonce:     <32 hex chars, random>
       X-Relay-Signature: base64(ECDSA-SHA256(canonical))

       canonical = METHOD \n PATH \n TIMESTAMP \n NONCE \n sha256_hex(BODY)

   The server rejects: malformed headers, a timestamp more than 5 minutes
   off, an unknown/revoked device, a bad signature, a nonce already seen
   (replay), and more than RELAY_RATE_PER_MIN requests per minute per phone.
   Cheap checks run first: garbage never reaches the database.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .db import execute

CLOCK_SKEW_MS = 5 * 60 * 1000
NONCE_TTL = "15 minutes"            # > 2 × clock window: older replays fail on the timestamp
PAIRING_TTL_HOURS = 24
MAX_BODY_BYTES = 512 * 1024


def rate_per_minute() -> int:
    return int(os.environ.get("RELAY_RATE_PER_MIN", "30"))


def daily_message_cap() -> int:
    return int(os.environ.get("RELAY_DAILY_CAP", "3000"))


_RE_ID = re.compile(r"^[1-9]\d{0,8}$")
_RE_TS = re.compile(r"^\d{13}$")
_RE_NONCE = re.compile(r"^[0-9a-f]{32}$")
_RE_B64 = re.compile(r"^[A-Za-z0-9+/=]{40,200}$")
_HARDWARE = {"strongbox", "tee", "software"}


class RelayAuthError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def canonical(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    """String signed by the app — must match android/.../RequestSigner.kt."""
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()


def _load_public_key(b64: str) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(base64.b64decode(b64, validate=True))
    except (ValueError, binascii.Error, TypeError):
        raise RelayAuthError(400, "bad_key", "clé publique illisible")
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise RelayAuthError(400, "bad_key", "clé EC P-256 attendue")
    return key


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def register(code: str, public_key_b64: str, key_hardware: str | None, app_version: str | None) -> dict:
    """Burn the one-time pairing code and attach the phone's public key."""
    if not code or len(code) > 100:
        raise RelayAuthError(401, "bad_code", "code d'association manquant")
    if not isinstance(public_key_b64, str) or not _RE_B64.match(public_key_b64):
        raise RelayAuthError(400, "bad_key", "clé publique manquante")
    _load_public_key(public_key_b64)
    hw = key_hardware if key_hardware in _HARDWARE else "software"
    burnt = hash_code(os.urandom(32).hex())      # the code can never be used again
    row = execute(
        "UPDATE relay_devices SET public_key = %s, key_hardware = %s, registered_at = now(), "
        "pairing_expires_at = NULL, token_hash = %s, last_seen_at = now(), "
        "last_app_version = COALESCE(%s, last_app_version) "
        "WHERE token_hash = %s AND revoked_at IS NULL AND public_key IS NULL "
        "AND pairing_expires_at > now() RETURNING id, name",
        (public_key_b64, hw, burnt, (app_version or "")[:40] or None, hash_code(code)),
        fetch="one", dict_rows=True,
    )
    if not row:
        raise RelayAuthError(401, "bad_code", "code d'association invalide, expiré ou déjà utilisé")
    return dict(row)


# ---------------------------------------------------------------------------
# Signed requests
# ---------------------------------------------------------------------------

def verify_request(method: str, path: str, headers, body: bytes, now_ms: int | None = None) -> dict:
    device_id = headers.get("X-Relay-Device", "")
    ts = headers.get("X-Relay-Timestamp", "")
    nonce = headers.get("X-Relay-Nonce", "")
    signature = headers.get("X-Relay-Signature", "")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)

    # 1. shape — no database access for garbage
    if not (_RE_ID.match(device_id) and _RE_TS.match(ts) and _RE_NONCE.match(nonce) and _RE_B64.match(signature)):
        raise RelayAuthError(401, "unsigned", "requête non signée")
    # 2. freshness
    if abs(now_ms - int(ts)) > CLOCK_SKEW_MS:
        raise RelayAuthError(401, "clock", "horodatage hors délai", server_time=now_ms)
    # 3. device + signature
    row = execute(
        "SELECT id, name, public_key FROM relay_devices "
        "WHERE id = %s AND revoked_at IS NULL AND public_key IS NOT NULL",
        (int(device_id),), fetch="one", dict_rows=True,
    )
    if not row:
        raise RelayAuthError(401, "unknown_device", "téléphone inconnu ou révoqué")
    try:
        _load_public_key(row["public_key"]).verify(
            base64.b64decode(signature), canonical(method, path, ts, nonce, body), ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, binascii.Error):
        raise RelayAuthError(401, "bad_signature", "signature invalide")
    # 4. replay
    fresh = execute(
        "INSERT INTO relay_nonces (device_id, nonce) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING 1",
        (row["id"], nonce), fetch="one",
    )
    if not fresh:
        raise RelayAuthError(401, "replay", "requête déjà reçue")
    execute(f"DELETE FROM relay_nonces WHERE device_id = %s AND seen_at < now() - interval '{NONCE_TTL}'",
            (row["id"],))
    # 5. per-phone rate limit (fixed one-minute window)
    count = execute(
        "UPDATE relay_devices SET "
        "rate_window_count = CASE WHEN rate_window_start IS NULL OR rate_window_start < now() - interval '1 minute' "
        "THEN 1 ELSE rate_window_count + 1 END, "
        "rate_window_start = CASE WHEN rate_window_start IS NULL OR rate_window_start < now() - interval '1 minute' "
        "THEN now() ELSE rate_window_start END, "
        "last_seen_at = now(), last_app_version = COALESCE(%s, last_app_version) "
        "WHERE id = %s RETURNING rate_window_count",
        ((headers.get("X-App-Version") or "")[:40] or None, row["id"]), fetch="one",
    )[0]
    if count > rate_per_minute():
        raise RelayAuthError(429, "rate_limited", "trop de requêtes", retry_after=60)
    return {"id": row["id"], "name": row["name"]}


def check_daily_cap(device_id: int, incoming: int) -> None:
    received = execute(
        "SELECT COUNT(*) FROM chat_messages WHERE device_id = %s AND received_at > now() - interval '24 hours'",
        (device_id,), fetch="one",
    )[0]
    if received + incoming > daily_message_cap():
        raise RelayAuthError(429, "daily_cap", "quota quotidien de messages atteint", retry_after=3600)
