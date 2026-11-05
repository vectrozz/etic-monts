"""WhatsApp relay: messages forwarded by the « EMB Relais » Android app.

The app runs on a phone that is a member of the farms' WhatsApp group. It
reads the notifications of that group only and POSTs them here, signed with
a key held in the phone's secure hardware (see relay_auth.py). Nothing talks
to WhatsApp itself.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from .db import cursor, execute
from .relay_auth import PAIRING_TTL_HOURS, hash_code

MAX_BATCH = 200
MAX_TEXT = 4000
MAX_NAME = 160


# ---------------------------------------------------------------------------
# Devices (relay phones)
# ---------------------------------------------------------------------------

def _new_code() -> str:
    return "embr_" + secrets.token_urlsafe(32)


def create_device(name: str, created_by: int | None) -> tuple[int, str]:
    """Return (device id, one-time pairing code valid 24 h). Only its hash is stored."""
    code = _new_code()
    row = execute(
        "INSERT INTO relay_devices (name, token_hash, created_by, pairing_expires_at) "
        f"VALUES (%s, %s, %s, now() + interval '{PAIRING_TTL_HOURS} hours') RETURNING id",
        (name.strip()[:80] or "Téléphone", hash_code(code), created_by), fetch="one",
    )
    return row[0], code


def new_pairing_code(device_id: int) -> str | None:
    """New one-time code for an existing phone (reinstall, new phone); the old key stops working."""
    code = _new_code()
    row = execute(
        "UPDATE relay_devices SET token_hash = %s, public_key = NULL, key_hardware = NULL, "
        f"registered_at = NULL, pairing_expires_at = now() + interval '{PAIRING_TTL_HOURS} hours' "
        "WHERE id = %s AND revoked_at IS NULL RETURNING name",
        (hash_code(code), device_id), fetch="one",
    )
    return code if row else None


def revoke_device(device_id: int) -> None:
    execute("UPDATE relay_devices SET revoked_at = now(), public_key = NULL "
            "WHERE id = %s AND revoked_at IS NULL", (device_id,))


def list_devices() -> list[dict]:
    rows = execute(
        "SELECT d.id, d.name, d.created_at, d.last_seen_at, d.last_app_version, d.revoked_at, "
        "d.public_key IS NOT NULL AS paired, d.key_hardware, d.registered_at, d.pairing_expires_at, "
        "d.pairing_expires_at < now() AS pairing_expired, "
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
    """(farms with their messages of the last `days` days, messages of unmapped senders).

    Several senders can belong to the same farm (GAEC associates): their
    messages are merged into one farm entry. Each farm gets:
      messages  all messages of the period, newest first
      pending   the ones still to process (status 'new'), newest first
      history   the others
      senders   distinct people who wrote, most recent first
    """
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
    for f in farms.values():
        f["pending"] = [m for m in f["messages"] if m["status"] == "new"]
        f["history"] = [m for m in f["messages"] if m["status"] != "new"]
        f["senders"] = list(dict.fromkeys(m["sender_name"] for m in f["messages"]))
    # farms with something to process first, then by most recent message
    ordered = sorted(farms.values(), key=lambda f: (bool(f["pending"]), f["messages"][0]["posted_at"]),
                     reverse=True)
    return ordered, unmapped


def mark_farm_done(ferme_id: int) -> int:
    """Mark every pending message of a farm (all its senders) as processed."""
    row = execute(
        "WITH done AS (UPDATE chat_messages m SET status = 'done' FROM chat_senders s "
        "WHERE s.sender_name = m.sender_name AND s.ferme_id = %s AND m.status = 'new' RETURNING 1) "
        "SELECT COUNT(*) FROM done",
        (ferme_id,), fetch="one",
    )
    return row[0] if row else 0


def senders_by_farm() -> list[dict]:
    """Farms that have at least one linked sender, with the list of their senders."""
    rows = execute(
        "SELECT f.id, COALESCE(NULLIF(f.farmname, ''), f.name) AS farm, "
        "array_agg(s.sender_name ORDER BY s.sender_name) AS senders "
        "FROM chat_senders s JOIN fermes f ON f.id = s.ferme_id "
        "WHERE NOT s.ignored GROUP BY f.id ORDER BY 2",
        fetch="all", dict_rows=True,
    ) or []
    return [dict(r) for r in rows]


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
        "SELECT s.id, s.sender_name, s.ferme_id, s.ignored, "
        "COALESCE(NULLIF(f.farmname, ''), f.name) AS farmname, "
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
