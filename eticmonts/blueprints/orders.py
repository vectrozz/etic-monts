"""Orders / commands management.

Internal admin views. The public client-facing form lives in `public.py`.
The order placement logic (stock locking + deadline enforcement) is shared
across both — see `services_order.place_order`.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import cursor, execute
from ..security import (
    login_required, admin_required, producteur_required, get_session_context,
)


bp = Blueprint("orders", __name__, url_prefix="/orders")


@bp.route("/")
@producteur_required
def index():
    ctx = get_session_context()
    status = request.args.get("status") or ""
    cycle = request.args.get("cycle") or ""

    where = ["1=1"]
    params: list = []
    if status:
        where.append("o.status = %s"); params.append(status)
    if cycle:
        where.append("o.cycle_date = %s"); params.append(cycle)

    rows = execute(
        "SELECT o.id, c.name, o.cycle_date, o.status, o.total_amount, o.total_weight_kg, "
        "o.tournee_id, o.created_at, o.confirmed_at "
        "FROM orders o JOIN clients c ON c.id = o.client_id "
        "WHERE " + " AND ".join(where) +
        " ORDER BY o.cycle_date DESC, o.created_at DESC",
        params, fetch="all",
    ) or []

    cycles = execute("SELECT DISTINCT cycle_date FROM orders ORDER BY cycle_date DESC LIMIT 12",
                     fetch="all") or []
    return render_template(
        "orders/index.html", **ctx, orders=rows, cycles=[r[0] for r in cycles],
        status=status, cycle=cycle,
    )


@bp.route("/<int:oid>")
@producteur_required
def detail(oid):
    ctx = get_session_context()
    order = execute(
        "SELECT o.id, o.client_id, c.name, c.address, c.postal_code, c.city, c.phone, "
        "c.email, o.cycle_date, o.status, o.total_amount, o.total_weight_kg, "
        "o.total_volume_l, o.notes, o.tournee_id, o.created_at, o.confirmed_at "
        "FROM orders o JOIN clients c ON c.id = o.client_id WHERE o.id = %s",
        (oid,), fetch="one", dict_rows=True,
    )
    if order is None:
        flash("Commande introuvable.", "danger")
        return redirect(url_for("orders.index"))
    items = execute(
        "SELECT oi.id, p.name AS product_name, p.unit, f.farmname AS producteur, "
        "oi.quantity, oi.unit_price, oi.line_total "
        "FROM order_items oi "
        "JOIN products p ON p.id = oi.product_id "
        "JOIN fermes f ON f.id = oi.producteur_id "
        "WHERE oi.order_id = %s ORDER BY p.name",
        (oid,), fetch="all", dict_rows=True,
    ) or []
    tournees = execute(
        "SELECT id, name, delivery_date FROM tournees WHERE delivery_date = %s ORDER BY name",
        (order["cycle_date"],), fetch="all", dict_rows=True,
    ) or []
    return render_template("orders/detail.html", **ctx, order=order, items=items, tournees=tournees)


@bp.route("/<int:oid>/status", methods=["POST"])
@producteur_required
def update_status(oid):
    new_status = request.form.get("status", "").strip()
    if new_status not in {"pending", "confirmed", "prepared", "delivered", "cancelled"}:
        flash("Statut invalide.", "danger")
        return redirect(url_for("orders.detail", oid=oid))
    if new_status == "cancelled":
        # release reserved stock back to availability
        with cursor() as cur:
            cur.execute(
                "UPDATE stocks s SET quantity_reserved = GREATEST(0, s.quantity_reserved - oi.quantity) "
                "FROM order_items oi WHERE oi.order_id = %s AND oi.stock_id = s.id",
                (oid,))
            cur.execute(
                "UPDATE orders SET status='cancelled' WHERE id = %s", (oid,))
    elif new_status == "confirmed":
        execute("UPDATE orders SET status='confirmed', confirmed_at = CURRENT_TIMESTAMP WHERE id = %s",
                (oid,))
    elif new_status == "delivered":
        execute("UPDATE orders SET status='delivered', delivered_at = CURRENT_TIMESTAMP WHERE id = %s",
                (oid,))
    else:
        execute("UPDATE orders SET status=%s WHERE id = %s", (new_status, oid))
    flash("Statut mis à jour.", "success")
    return redirect(url_for("orders.detail", oid=oid))


@bp.route("/<int:oid>/assign", methods=["POST"])
@producteur_required
def assign_tournee(oid):
    tournee_id = request.form.get("tournee_id") or None
    tournee_id = int(tournee_id) if tournee_id else None
    execute("UPDATE orders SET tournee_id = %s WHERE id = %s", (tournee_id, oid))
    flash("Affectation tournée enregistrée.", "success")
    return redirect(url_for("orders.detail", oid=oid))
