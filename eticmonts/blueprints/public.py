"""Public client ordering page.

Authenticated by an opaque token in the URL — no login required.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import execute
from ..order_service import LineRequest, OrderError, place_order
from ..schedule import upcoming_slots, is_ordering_open
from ..settings_store import (
    get_delivery_cycle, get_branding, get_client_max_upcoming_slots,
)
from ..config import load_config


bp = Blueprint("public", __name__)


def _client_by_token(token: str) -> dict | None:
    row = execute(
        "SELECT id, name, contact_name, email, phone, address, postal_code, city, "
        "is_active FROM clients WHERE order_token = %s", (token,),
        fetch="one", dict_rows=True,
    )
    return dict(row) if row else None


@bp.route("/order/<token>")
def order_form(token):
    client = _client_by_token(token)
    if client is None or not client["is_active"]:
        abort(404)

    cfg = load_config()
    max_slots = get_client_max_upcoming_slots()
    slots = upcoming_slots(get_delivery_cycle(), tz_name=cfg.timezone, count=max_slots)
    cycle_iso = request.args.get("cycle")
    cycle_date = None
    if cycle_iso:
        try:
            cycle_date = date.fromisoformat(cycle_iso)
        except ValueError:
            cycle_date = None
    if cycle_date is None and slots:
        # default to first OPEN slot
        for s in slots:
            if s.is_open:
                cycle_date = s.delivery_date
                break
        if cycle_date is None:
            cycle_date = slots[0].delivery_date

    available = []
    if cycle_date:
        # Pick cycle-specific row if present, otherwise fall back to season pool
        # for the same (producer, product). DISTINCT ON with NULLS LAST puts
        # the cycle-specific row first when both exist.
        rows = execute(
            "SELECT DISTINCT ON (s.producteur_id, s.product_id) "
            "       s.id, s.product_id, s.cycle_date, "
            "       (s.quantity_available - s.quantity_reserved) AS remaining, "
            "       COALESCE(s.price, p.default_price) AS price, "
            "       p.name, p.unit, p.category, p.description, "
            "       f.farmname AS producteur, "
            "       (s.cycle_date IS NULL) AS is_pool "
            "FROM stocks s "
            "JOIN products p ON p.id = s.product_id "
            "JOIN fermes f ON f.id = s.producteur_id "
            "WHERE (s.cycle_date = %s OR s.cycle_date IS NULL) "
            "  AND p.is_active "
            "  AND (s.quantity_available - s.quantity_reserved) > 0 "
            "ORDER BY s.producteur_id, s.product_id, s.cycle_date NULLS LAST",
            (cycle_date,), fetch="all", dict_rows=True,
        ) or []
        available = sorted(
            (dict(r) for r in rows),
            key=lambda r: (r["category"] or "", r["name"] or "", r["producteur"] or ""),
        )

    return render_template(
        "public/order.html",
        client=client, slots=[s.to_dict() for s in slots],
        cycle_date=cycle_date, products=available, branding=get_branding(),
    )


@bp.route("/order/<token>", methods=["POST"])
def submit_order(token):
    client = _client_by_token(token)
    if client is None or not client["is_active"]:
        abort(404)
    cycle_iso = request.form.get("cycle_date")
    try:
        cycle_date = date.fromisoformat(cycle_iso)
    except (TypeError, ValueError):
        flash("Date de livraison invalide.", "danger")
        return redirect(url_for("public.order_form", token=token))

    # Enforce: chosen cycle must be within the client's allowed horizon
    cfg = load_config()
    max_slots = get_client_max_upcoming_slots()
    allowed = {s.delivery_date for s in upcoming_slots(
        get_delivery_cycle(), tz_name=cfg.timezone, count=max_slots,
    )}
    if cycle_date not in allowed:
        flash("Cette date de livraison n'est pas disponible aux commandes.", "danger")
        return redirect(url_for("public.order_form", token=token))

    lines: list[LineRequest] = []
    for key, val in request.form.items():
        if not key.startswith("qty_"):
            continue
        try:
            stock_id = int(key[4:])
            qty = float(val or 0)
        except ValueError:
            continue
        if qty > 0:
            lines.append(LineRequest(stock_id=stock_id, quantity=qty))
    notes = (request.form.get("notes") or "").strip() or None

    try:
        placed = place_order(
            client_id=client["id"], cycle_date=cycle_date, lines=lines, notes=notes,
        )
    except OrderError as e:
        flash(str(e), "danger")
        return redirect(url_for("public.order_form", token=token, cycle=cycle_iso))

    return render_template(
        "public/order_confirmed.html",
        client=client, order_id=placed.order_id, cycle_date=cycle_date,
        total_amount=placed.total_amount, total_weight_kg=placed.total_weight_kg,
        total_volume_l=placed.total_volume_l, branding=get_branding(),
    )
