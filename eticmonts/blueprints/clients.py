"""Client management."""
from __future__ import annotations

import secrets

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute
from ..security import login_required, admin_required, producteur_required, get_session_context


bp = Blueprint("clients", __name__, url_prefix="/clients")


def _new_token() -> str:
    return secrets.token_urlsafe(24)


def _decimal_or_none(name: str) -> float | None:
    raw = request.form.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@bp.route("/")
@login_required
def index():
    ctx = get_session_context()
    rows = execute(
        "SELECT id, name, contact_name, email, phone, address, postal_code, city, "
        "lat, lng, order_token, is_active, notes FROM clients ORDER BY is_active DESC, name",
        fetch="all", dict_rows=True,
    ) or []
    return render_template("clients/index.html", **ctx, clients=rows)


@bp.route("/create", methods=["POST"])
@producteur_required
def create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Nom du client requis.", "warning")
        return redirect(url_for("clients.index"))
    token = _new_token()
    execute(
        "INSERT INTO clients (name, contact_name, email, phone, address, postal_code, "
        "city, lat, lng, order_token, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            name,
            (request.form.get("contact_name") or "").strip() or None,
            (request.form.get("email") or "").strip() or None,
            (request.form.get("phone") or "").strip() or None,
            (request.form.get("address") or "").strip() or None,
            (request.form.get("postal_code") or "").strip() or None,
            (request.form.get("city") or "").strip() or None,
            _decimal_or_none("lat"),
            _decimal_or_none("lng"),
            token,
            (request.form.get("notes") or "").strip() or None,
        ),
    )
    flash(f"Client {name} créé.", "success")
    return redirect(url_for("clients.index"))


@bp.route("/<int:cid>/update", methods=["POST"])
@producteur_required
def update(cid):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Nom requis.", "warning")
        return redirect(url_for("clients.index"))
    is_active = request.form.get("is_active") == "on"
    execute(
        "UPDATE clients SET name=%s, contact_name=%s, email=%s, phone=%s, address=%s, "
        "postal_code=%s, city=%s, lat=%s, lng=%s, is_active=%s, notes=%s, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (
            name,
            (request.form.get("contact_name") or "").strip() or None,
            (request.form.get("email") or "").strip() or None,
            (request.form.get("phone") or "").strip() or None,
            (request.form.get("address") or "").strip() or None,
            (request.form.get("postal_code") or "").strip() or None,
            (request.form.get("city") or "").strip() or None,
            _decimal_or_none("lat"),
            _decimal_or_none("lng"),
            is_active,
            (request.form.get("notes") or "").strip() or None,
            cid,
        ),
    )
    flash("Client mis à jour.", "success")
    return redirect(url_for("clients.index"))


@bp.route("/<int:cid>/regenerate-token", methods=["POST"])
@producteur_required
def regenerate_token(cid):
    execute("UPDATE clients SET order_token = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (_new_token(), cid))
    flash("Lien de commande régénéré.", "success")
    return redirect(url_for("clients.index"))


@bp.route("/<int:cid>/delete", methods=["POST"])
@admin_required
def delete(cid):
    try:
        execute("DELETE FROM clients WHERE id = %s", (cid,))
        flash("Client supprimé.", "success")
    except Exception as e:
        flash(f"Suppression impossible (commandes liées ?) : {e}", "danger")
    return redirect(url_for("clients.index"))
