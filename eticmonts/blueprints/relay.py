"""WhatsApp relay — JSON API for the Android app + admin inbox."""
from __future__ import annotations

import os
from urllib.parse import urlencode

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for,
)

from .. import relay
from ..chat_parser import parse_list
from ..security import admin_required, get_session_context

api = Blueprint("relay_api", __name__, url_prefix="/api/relay")
bp = Blueprint("relay", __name__, url_prefix="/whatsapp")

PAIR_SCHEME = "embrelais"


# ---------------------------------------------------------------------------
# API (Bearer token, JSON in / JSON out, no cookies)
# ---------------------------------------------------------------------------

def _device_or_401():
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    device = relay.authenticate(token, request.headers.get("X-App-Version"))
    if device is None:
        abort(_json_error(401, "invalid or revoked token"))
    return device


def _json_error(status: int, message: str):
    resp = jsonify(error=message)
    resp.status_code = status
    return resp


@api.get("/ping")
def ping():
    device = _device_or_401()
    return jsonify(ok=True, device=device["name"])


@api.post("/messages")
def receive_messages():
    device = _device_or_401()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error(400, "JSON object expected")
    try:
        result = relay.ingest(device["id"], payload.get("messages"))
    except relay.InvalidPayload as e:
        return _json_error(400, str(e))
    return jsonify(ok=True, **result)


# ---------------------------------------------------------------------------
# Admin UI
# ---------------------------------------------------------------------------

def _render(template: str, **kw):
    return render_template(template, **get_session_context(),
                           relay_apk_url=os.environ.get("RELAY_APK_URL", ""), **kw)


@bp.get("/")
@admin_required
def inbox():
    try:
        days = max(1, min(60, int(request.args.get("jours", 7))))
    except ValueError:
        days = 7
    farms, unmapped = relay.recent_by_farm(days)
    for f in farms:
        for m in f["messages"]:
            m["parsed"] = parse_list(m["body"])
    for m in unmapped:
        m["parsed"] = parse_list(m["body"])
    return _render("whatsapp/inbox.html", farms=farms, unmapped=unmapped, days=days,
                   farm_choices=relay.farms_for_select(),
                   unmapped_senders={s["sender_name"]: s for s in relay.list_senders() if s["ferme_id"] is None})


@bp.get("/messages")
@admin_required
def messages():
    return _render("whatsapp/messages.html", messages=relay.all_messages())


@bp.post("/messages/<int:mid>/statut")
@admin_required
def message_status(mid):
    try:
        relay.set_status(mid, request.form.get("status", ""))
    except ValueError:
        abort(400)
    return redirect(request.form.get("next") or url_for("relay.inbox"))


@bp.get("/expediteurs")
@admin_required
def senders():
    return _render("whatsapp/senders.html", senders=relay.list_senders(),
                   farm_choices=relay.farms_for_select())


@bp.post("/expediteurs/<int:sid>")
@admin_required
def map_sender(sid):
    raw = request.form.get("ferme_id") or ""
    ignored = raw == "ignore"
    ferme_id = int(raw) if raw.isdigit() else None
    relay.map_sender(sid, ferme_id, ignored)
    flash("Expéditeur mis à jour.", "success")
    return redirect(request.form.get("next") or url_for("relay.senders"))


@bp.get("/telephones")
@admin_required
def devices():
    return _render("whatsapp/devices.html", devices=relay.list_devices(), created=None)


@bp.post("/telephones")
@admin_required
def create_device():
    name = (request.form.get("name") or "").strip() or "Téléphone"
    group = (request.form.get("group") or "").strip()
    device_id, token = relay.create_device(name, session.get("user_id"))
    server = request.url_root.rstrip("/")
    params = {"server": server, "token": token, "name": name}
    if group:
        params["groups"] = group
    pair_link = f"{PAIR_SCHEME}://pair?{urlencode(params)}"
    return _render("whatsapp/devices.html", devices=relay.list_devices(),
                   created={"id": device_id, "name": name, "token": token, "server": server,
                            "group": group, "link": pair_link})


@bp.post("/telephones/<int:did>/revoquer")
@admin_required
def revoke_device(did):
    relay.revoke_device(did)
    flash("Téléphone révoqué : il ne peut plus envoyer de messages.", "success")
    return redirect(url_for("relay.devices"))
