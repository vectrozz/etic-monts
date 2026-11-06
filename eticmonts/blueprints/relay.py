"""WhatsApp relay — JSON API for the Android app + admin inbox."""
from __future__ import annotations

import csv
import io
import os
from urllib.parse import urlencode

from flask import (
    Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for,
)

from .. import relay, relay_auth, stock_board
from ..chat_parser import parse_list
from ..security import admin_required, get_session_context

api = Blueprint("relay_api", __name__, url_prefix="/api/relay")
bp = Blueprint("relay", __name__, url_prefix="/whatsapp")

PAIR_SCHEME = "embrelais"


# ---------------------------------------------------------------------------
# API — JSON only, no cookies. Pairing with a one-time code, then every
# request signed by the phone's hardware key (see relay_auth.py).
# ---------------------------------------------------------------------------

def _json_error(status: int, code: str, message: str, **extra):
    resp = jsonify(error=message, code=code, **extra)
    resp.status_code = status
    if "retry_after" in extra:
        resp.headers["Retry-After"] = str(extra["retry_after"])
    return resp


@api.errorhandler(relay_auth.RelayAuthError)
def _auth_error(e: relay_auth.RelayAuthError):
    return _json_error(e.status, e.code, e.message, **e.extra)


@api.before_request
def _cheap_limits():
    """Reject oversized or unbounded bodies before reading them (nginx caps them too)."""
    if request.method == "POST":
        if request.content_length is None:
            return _json_error(411, "length_required", "Content-Length requis")
        if request.content_length > relay_auth.MAX_BODY_BYTES:
            return _json_error(413, "too_large", "corps de requête trop gros")


def _signed_device() -> dict:
    return relay_auth.verify_request(request.method, request.path, request.headers,
                                     request.get_data(cache=True))


@api.post("/register")
def register():
    auth = request.headers.get("Authorization", "")
    code = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error(400, "bad_json", "objet JSON attendu")
    device = relay_auth.register(code, payload.get("public_key"), payload.get("key_hardware"),
                                 request.headers.get("X-App-Version"))
    return jsonify(ok=True, device_id=device["id"], device=device["name"])


@api.get("/ping")
def ping():
    device = _signed_device()
    return jsonify(ok=True, device=device["name"])


@api.post("/messages")
def receive_messages():
    device = _signed_device()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error(400, "bad_json", "objet JSON attendu")
    try:
        messages = payload.get("messages")
        relay_auth.check_daily_cap(device["id"], len(messages) if isinstance(messages, list) else 0)
        result = relay.ingest(device["id"], messages)
    except relay.InvalidPayload as e:
        return _json_error(400, "bad_payload", str(e))
    return jsonify(ok=True, **result)


# ---------------------------------------------------------------------------
# Admin UI
# ---------------------------------------------------------------------------

def _render(template: str, **kw):
    return render_template(template, **get_session_context(),
                           relay_apk_url=os.environ.get("RELAY_APK_URL", ""), **kw)


def _days(default: int = 7) -> int:
    try:
        return max(1, min(60, int(request.args.get("jours", default))))
    except ValueError:
        return default


@bp.get("/stocks")
@admin_required
def stocks():
    days = _days()
    return _render("whatsapp/stocks.html", board=stock_board.load(days), days=days)


@bp.get("/stocks.csv")
@admin_required
def stocks_csv():
    days = _days()
    board = stock_board.load(days)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["legume", "total"] + [f.name for f in board.farms])
    for r in board.products:
        w.writerow([r.label, r.total_label] + [
            r.cells[f.ferme_id].line.qty_label if f.ferme_id in r.cells else "" for f in board.farms])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=stocks-whatsapp-{days}j.csv"})


@bp.get("/")
@admin_required
def inbox():
    days = _days()
    farms, unmapped = relay.recent_by_farm(days)
    in_stock = stock_board.load(days).used
    for f in farms:
        for m in f["messages"]:
            m["parsed"] = parse_list(m["body"])
            m["in_stock"] = m["id"] in in_stock
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


@bp.post("/fermes/<int:ferme_id>/traite")
@admin_required
def farm_done(ferme_id):
    n = relay.mark_farm_done(ferme_id)
    flash(f"{n} message{'s' if n > 1 else ''} marqué{'s' if n > 1 else ''} comme lu{'s' if n > 1 else ''}.",
          "success")
    return redirect(request.form.get("next") or url_for("relay.inbox"))


@bp.get("/expediteurs")
@admin_required
def senders():
    return _render("whatsapp/senders.html", senders=relay.list_senders(),
                   farm_choices=relay.farms_for_select(), by_farm=relay.senders_by_farm())


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


def _pairing_page(device_id: int, name: str, code: str, group: str):
    server = request.url_root.rstrip("/")
    params = {"server": server, "code": code, "name": name}
    if group:
        params["groups"] = group
    link = f"{PAIR_SCHEME}://pair?{urlencode(params)}"
    return _render("whatsapp/devices.html", devices=relay.list_devices(),
                   created={"id": device_id, "name": name, "code": code, "server": server,
                            "group": group, "link": link, "ttl": relay_auth.PAIRING_TTL_HOURS})


@bp.post("/telephones")
@admin_required
def create_device():
    name = (request.form.get("name") or "").strip() or "Téléphone"
    group = (request.form.get("group") or "").strip()
    device_id, code = relay.create_device(name, session.get("user_id"))
    return _pairing_page(device_id, name, code, group)


@bp.post("/telephones/<int:did>/lien")
@admin_required
def renew_pairing(did):
    """New one-time code (app reinstalled, phone replaced): the previous key stops working."""
    code = relay.new_pairing_code(did)
    if code is None:
        abort(404)
    name = next((d["name"] for d in relay.list_devices() if d["id"] == did), "Téléphone")
    return _pairing_page(did, name, code, (request.form.get("group") or "").strip())


@bp.post("/telephones/<int:did>/revoquer")
@admin_required
def revoke_device(did):
    relay.revoke_device(did)
    flash("Téléphone révoqué : il ne peut plus envoyer de messages.", "success")
    return redirect(url_for("relay.devices"))
