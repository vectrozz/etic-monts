"""WhatsApp relay: messages forwarded by the « EMB Relais » Android app.

The app runs on a phone that is a member of the farms' WhatsApp group. It
reads the notifications of that group only and POSTs them here with a device
token. Nothing talks to WhatsApp itself.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from .db import cursor, execute

MAX_BATCH = 200
MAX_TEXT = 4000
MAX_NAME = 160


# ---------------------------------------------------------------------------
# Devices (relay phones)
# ---------------------------------------------------------------------------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_device(name: str, created_by: int | None) -> tuple[int, str]:
    """Return (device id, clear token). Only the hash is stored."""
    token = "embr_" + secrets.token_urlsafe(32)
    row = execute(
        "INSERT INTO relay_devices (name, token_hash, created_by) VALUES (%s, %s, %s) RETURNING id",
        (name.strip()[:80] or "Téléphone", hash_token(token), created_by), fetch="one",
    )
    return row[0], token


def authenticate(token: str, app_version: str | None = None) -> dict | None:
    if not token:
        return None
    row = execute(
        "UPDATE relay_devices SET last_seen_at = now(), "
        "last_app_version = COALESCE(%s, last_app_version) "
        "WHERE token_hash = %s AND revoked_at IS NULL RETURNING id, name",
        ((app_version or None) and app_version[:40], hash_token(token)), fetch="one", dict_rows=True,
    )
    return dict(row) if row else None


def revoke_device(device_id: int) -> None:
    execute("UPDATE relay_devices SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (device_id,))


def list_devices() -> list[dict]:
    rows = execute(
        "SELECT d.id, d.name, d.created_at, d.last_seen_at, d.last_app_version, d.revoked_at, "
        "(SELECT COUNT(*) FROM chat_messages m WHERE m.device_id = d.id) AS messages "
        "FROM relay_devices d ORDER BY d.revoked_at IS NOT NULL, d.created_at DESC",
        fetch="all", dict_rows=True,
    ) or []
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class InvalidPayload(ValueError):
    pass


def dedup_key(chat: str, sender: str, posted_ms: int, text: str) -> str:
    return hashlib.sha256(f"{chat}\x1f{sender}\x1f{posted_ms}\x1f{text}".encode("utf-8")).hexdigest()


def _validate(messages) -> list[tuple[str, str, str, int]]:
    if not isinstance(messages, list) or not messages:
        raise InvalidPayload("'messages' must be a non-empty list")
    if len(messages) > MAX_BATCH:
        raise InvalidPayload(f"at most {MAX_BATCH} messages per request")
    out = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise InvalidPayload(f"messages[{i}] must be an object")
        chat, sender, text, posted = m.get("chat"), m.get("sender"), m.get("text"), m.get("posted_at")
        if not all(isinstance(v, str) and v.strip() for v in (chat, sender, text)):
            raise InvalidPayload(f"messages[{i}]: chat, sender and text are required strings")
        if not isinstance(posted, int) or isinstance(posted, bool) or posted <= 0:
            raise InvalidPayload(f"messages[{i}]: posted_at must be epoch milliseconds")
        out.append((chat.strip()[:MAX_NAME], sender.strip()[:MAX_NAME], text.strip()[:MAX_TEXT], posted))
    return out


def ingest(device_id: int, messages) -> dict:
    """Store new messages; duplicates (same chat/sender/time/text) are skipped."""
    rows = _validate(messages)
    accepted = 0
    with cursor() as cur:
        for chat, sender, text, posted_ms in rows:
            posted = datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc)
            cur.execute(
                "INSERT INTO chat_messages (device_id, chat_title, sender_name, body, posted_at, dedup_key) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (dedup_key) DO NOTHING RETURNING id",
                (device_id, chat, sender, text, posted, dedup_key(chat, sender, posted_ms, text)),
            )
            if cur.fetchone():
                accepted += 1
                cur.execute("INSERT INTO chat_senders (sender_name) VALUES (%s) "
                            "ON CONFLICT (sender_name) DO NOTHING", (sender,))
    return {"accepted": accepted, "duplicates": len(rows) - accepted}


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

_MSG_COLS = ("m.id, m.chat_title, m.sender_name, m.body, m.posted_at, m.received_at, m.status, "
             "s.ferme_id, s.ignored, f.farmname, f.name AS login")
_MSG_FROM = ("FROM chat_messages m LEFT JOIN chat_senders s ON s.sender_name = m.sender_name "
             "LEFT JOIN fermes f ON f.id = s.ferme_id")


def recent_by_farm(days: int = 7) -> tuple[list[dict], list[dict]]:
    """(farms with their messages of the last `days` days, messages of unmapped senders)."""
    rows = execute(
        f"SELECT {_MSG_COLS} {_MSG_FROM} "
        "WHERE m.posted_at >= now() - make_interval(days => %s) AND NOT COALESCE(s.ignored, FALSE) "
        "ORDER BY m.posted_at DESC",
        (days,), fetch="all", dict_rows=True,
    ) or []
    farms: dict[int, dict] = {}
    unmapped: list[dict] = []
    for r in rows:
        r = dict(r)
        if r["ferme_id"] is None:
            unmapped.append(r)
            continue
        f = farms.setdefault(r["ferme_id"], {"ferme_id": r["ferme_id"],
                                             "name": r["farmname"] or r["login"], "messages": []})
        f["messages"].append(r)
    ordered = sorted(farms.values(), key=lambda f: f["messages"][0]["posted_at"], reverse=True)
    return ordered, unmapped


def all_messages(limit: int = 200) -> list[dict]:
    rows = execute(f"SELECT {_MSG_COLS} {_MSG_FROM} ORDER BY m.posted_at DESC LIMIT %s",
                   (limit,), fetch="all", dict_rows=True) or []
    return [dict(r) for r in rows]


def set_status(message_id: int, status: str) -> None:
    if status not in ("new", "done", "ignored"):
        raise ValueError(status)
    execute("UPDATE chat_messages SET status = %s WHERE id = %s", (status, message_id))


def new_count() -> int:
    row = execute(
        "SELECT COUNT(*) FROM chat_messages m LEFT JOIN chat_senders s ON s.sender_name = m.sender_name "
        "WHERE m.status = 'new' AND NOT COALESCE(s.ignored, FALSE)", fetch="one")
    return row[0] if row else 0


def list_senders() -> list[dict]:
    rows = execute(
        "SELECT s.id, s.sender_name, s.ferme_id, s.ignored, f.farmname, "
        "(SELECT COUNT(*) FROM chat_messages m WHERE m.sender_name = s.sender_name) AS messages, "
        "(SELECT MAX(posted_at) FROM chat_messages m WHERE m.sender_name = s.sender_name) AS last_at "
        "FROM chat_senders s LEFT JOIN fermes f ON f.id = s.ferme_id "
        "ORDER BY s.ferme_id IS NOT NULL, s.ignored, s.sender_name",
        fetch="all", dict_rows=True,
    ) or []
    return [dict(r) for r in rows]


def map_sender(sender_id: int, ferme_id: int | None, ignored: bool) -> None:
    execute("UPDATE chat_senders SET ferme_id = %s, ignored = %s, updated_at = now() WHERE id = %s",
            (ferme_id, ignored, sender_id))


def farms_for_select() -> list[dict]:
    rows = execute("SELECT id, COALESCE(NULLIF(farmname, ''), name) AS label FROM fermes "
                   "WHERE is_active ORDER BY 2", fetch="all", dict_rows=True) or []
    return [dict(r) for r in rows]
