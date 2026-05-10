"""Per-producteur stock management.

Each row is (producteur, product, cycle_date) with available + reserved
quantities. Producteurs see/edit their own rows; admins see/edit all.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import cursor, execute
from ..security import (
    producteur_required, admin_required, login_required, is_admin,
    get_session_context,
)
from ..settings_store import get_delivery_cycle
from ..schedule import upcoming_slots
from ..config import load_config


bp = Blueprint("stocks", __name__, url_prefix="/stocks")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _stock_query(where_extra: list[str], params: list) -> list:
    return execute(
        "SELECT s.id, s.producteur_id, f.farmname, p.id, p.name, p.unit, "
        "s.quantity_available, s.quantity_reserved, s.price, s.notes, s.cycle_date "
        "FROM stocks s "
        "JOIN fermes f ON f.id = s.producteur_id "
        "JOIN products p ON p.id = s.product_id "
        "WHERE " + " AND ".join(where_extra) +
        " ORDER BY s.cycle_date NULLS FIRST, f.farmname, p.name",
        params, fetch="all",
    ) or []


@bp.route("/")
@producteur_required
def index():
    ctx = get_session_context()
    cycle = _parse_date(request.args.get("cycle"))
    cfg = load_config()
    slots = upcoming_slots(get_delivery_cycle(), tz_name=cfg.timezone, count=4)
    if cycle is None and slots:
        cycle = slots[0].delivery_date

    # Season pool rows (cycle_date IS NULL)
    pool_where = ["s.cycle_date IS NULL"]
    pool_params: list = []
    if not is_admin():
        pool_where.append("s.producteur_id = %s")
        pool_params.append(session["user_id"])
    pool_rows = _stock_query(pool_where, pool_params)

    # Cycle-specific rows for the selected cycle
    cycle_rows: list = []
    if cycle is not None:
        cw = ["s.cycle_date = %s"]
        cp: list = [cycle]
        if not is_admin():
            cw.append("s.producteur_id = %s")
            cp.append(session["user_id"])
        cycle_rows = _stock_query(cw, cp)

    products = execute(
        "SELECT id, name, unit, default_price FROM products WHERE is_active ORDER BY name",
        fetch="all", dict_rows=True,
    ) or []
    return render_template(
        "stocks/index.html", **ctx,
        pool_stocks=pool_rows, cycle_stocks=cycle_rows,
        products=products, cycle=cycle, slots=[s.to_dict() for s in slots],
    )


@bp.route("/upsert", methods=["POST"])
@producteur_required
def upsert():
    scope = (request.form.get("scope") or "cycle").strip()
    product_id = int(request.form["product_id"])
    qty_raw = request.form.get("quantity_available")
    if qty_raw is None or qty_raw == "":
        flash("Quantité requise.", "danger")
        return redirect(url_for("stocks.index"))
    qty = float(qty_raw)
    price_raw = request.form.get("price") or ""
    notes = (request.form.get("notes") or "").strip() or None

    if qty < 0 or product_id <= 0:
        flash("Données invalides.", "danger")
        return redirect(url_for("stocks.index"))

    target_pid = (
        int(request.form.get("producteur_id"))
        if is_admin() and request.form.get("producteur_id") else session["user_id"]
    )
    price = float(price_raw) if price_raw else None

    if scope == "season":
        # Pool row: one per (producteur, product), no date.
        execute(
            "INSERT INTO stocks (producteur_id, product_id, cycle_date, quantity_available, "
            "price, notes) VALUES (%s,%s,NULL,%s,%s,%s) "
            "ON CONFLICT (producteur_id, product_id) WHERE cycle_date IS NULL DO UPDATE "
            "SET quantity_available = EXCLUDED.quantity_available, "
            "    price = COALESCE(EXCLUDED.price, stocks.price), "
            "    notes = COALESCE(EXCLUDED.notes, stocks.notes), "
            "    updated_at = CURRENT_TIMESTAMP",
            (target_pid, product_id, qty, price, notes),
        )
        flash("Stock saison mis à jour (s'épuise sur toutes les livraisons).", "success")
        return redirect(url_for("stocks.index"))

    # Cycle-specific
    cycle = _parse_date(request.form.get("cycle_date"))
    if cycle is None:
        flash("Date de cycle requise pour un stock par livraison.", "danger")
        return redirect(url_for("stocks.index"))
    execute(
        "INSERT INTO stocks (producteur_id, product_id, cycle_date, quantity_available, "
        "price, notes) VALUES (%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (producteur_id, product_id, cycle_date) WHERE cycle_date IS NOT NULL DO UPDATE "
        "SET quantity_available = EXCLUDED.quantity_available, "
        "    price = COALESCE(EXCLUDED.price, stocks.price), "
        "    notes = COALESCE(EXCLUDED.notes, stocks.notes), "
        "    updated_at = CURRENT_TIMESTAMP",
        (target_pid, product_id, cycle, qty, price, notes),
    )
    flash(f"Stock pour le {cycle} mis à jour.", "success")
    return redirect(url_for("stocks.index", cycle=cycle.isoformat()))


@bp.route("/<int:sid>/delete", methods=["POST"])
@producteur_required
def delete(sid):
    if is_admin():
        execute("DELETE FROM stocks WHERE id = %s", (sid,))
    else:
        execute("DELETE FROM stocks WHERE id = %s AND producteur_id = %s",
                (sid, session["user_id"]))
    flash("Stock supprimé.", "success")
    return redirect(url_for("stocks.index"))
