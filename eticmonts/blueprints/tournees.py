"""Delivery tournées (rounds): plan, optimise, dispatch."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import cursor, execute
from ..routing import plan_route
from ..security import producteur_required, get_session_context
from ..settings_store import get_delivery_cycle


bp = Blueprint("tournees", __name__, url_prefix="/tournees")


def _decimal_or_none(name: str, form=None) -> float | None:
    src = form if form is not None else request.form
    raw = src.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@bp.route("/")
@producteur_required
def index():
    ctx = get_session_context()
    rows = execute(
        "SELECT t.id, t.name, t.delivery_date, t.driver, t.vehicle, t.status, "
        "(SELECT COUNT(*) FROM orders o WHERE o.tournee_id = t.id) AS stop_count, "
        "(SELECT COALESCE(SUM(o.total_weight_kg),0) FROM orders o WHERE o.tournee_id = t.id) AS weight, "
        "(SELECT COALESCE(SUM(o.total_volume_l),0) FROM orders o WHERE o.tournee_id = t.id) AS volume "
        "FROM tournees t ORDER BY t.delivery_date DESC, t.name",
        fetch="all", dict_rows=True,
    ) or []
    cycle_cfg = get_delivery_cycle()
    return render_template(
        "tournees/index.html", **ctx, tournees=rows,
        max_weight=cycle_cfg.get("vehicle_max_weight_kg"),
        max_volume=cycle_cfg.get("vehicle_max_volume_l"),
    )


@bp.route("/create", methods=["POST"])
@producteur_required
def create():
    name = (request.form.get("name") or "").strip()
    delivery_iso = request.form.get("delivery_date") or ""
    if not name or not delivery_iso:
        flash("Nom et date de livraison requis.", "warning")
        return redirect(url_for("tournees.index"))
    try:
        delivery_date = date.fromisoformat(delivery_iso)
    except ValueError:
        flash("Date invalide.", "danger")
        return redirect(url_for("tournees.index"))
    execute(
        "INSERT INTO tournees (name, delivery_date, driver, vehicle, start_address, "
        "start_lat, start_lng, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            name, delivery_date,
            (request.form.get("driver") or "").strip() or None,
            (request.form.get("vehicle") or "").strip() or None,
            (request.form.get("start_address") or "").strip() or None,
            _decimal_or_none("start_lat"),
            _decimal_or_none("start_lng"),
            (request.form.get("notes") or "").strip() or None,
        ),
    )
    flash("Tournée créée.", "success")
    return redirect(url_for("tournees.index"))


@bp.route("/<int:tid>")
@producteur_required
def detail(tid):
    ctx = get_session_context()
    tournee = execute(
        "SELECT id, name, delivery_date, driver, vehicle, start_address, "
        "start_lat, start_lng, status, notes FROM tournees WHERE id = %s",
        (tid,), fetch="one", dict_rows=True,
    )
    if tournee is None:
        flash("Tournée introuvable.", "danger")
        return redirect(url_for("tournees.index"))

    stops = execute(
        "SELECT o.id AS order_id, o.tournee_position, c.id AS client_id, c.name, "
        "c.address, c.postal_code, c.city, c.lat, c.lng, c.phone, "
        "o.total_weight_kg, o.total_volume_l, o.total_amount, o.status "
        "FROM orders o JOIN clients c ON c.id = o.client_id "
        "WHERE o.tournee_id = %s ORDER BY o.tournee_position NULLS LAST, c.name",
        (tid,), fetch="all", dict_rows=True,
    ) or []
    stops = [dict(s) for s in stops]

    candidate_orders = execute(
        "SELECT o.id, c.name, c.postal_code, c.city, o.total_weight_kg, o.cycle_date "
        "FROM orders o JOIN clients c ON c.id = o.client_id "
        "WHERE o.tournee_id IS NULL AND o.status IN ('pending','confirmed','prepared') "
        "AND o.cycle_date = %s ORDER BY c.postal_code, c.name",
        (tournee["delivery_date"],), fetch="all", dict_rows=True,
    ) or []

    totals = {
        "weight": sum(float(s["total_weight_kg"] or 0) for s in stops),
        "volume": sum(float(s["total_volume_l"] or 0) for s in stops),
        "amount": sum(float(s["total_amount"] or 0) for s in stops),
    }
    cycle_cfg = get_delivery_cycle()
    return render_template(
        "tournees/detail.html", **ctx, tournee=tournee, stops=stops,
        candidates=candidate_orders, totals=totals, cycle_cfg=cycle_cfg,
    )


@bp.route("/<int:tid>/add-orders", methods=["POST"])
@producteur_required
def add_orders(tid):
    ids = request.form.getlist("order_ids")
    if not ids:
        flash("Aucune commande sélectionnée.", "warning")
        return redirect(url_for("tournees.detail", tid=tid))
    execute(
        "UPDATE orders SET tournee_id = %s WHERE id = ANY(%s::int[])",
        (tid, [int(i) for i in ids]),
    )
    flash(f"{len(ids)} commande(s) ajoutée(s) à la tournée.", "success")
    return redirect(url_for("tournees.detail", tid=tid))


@bp.route("/<int:tid>/optimize", methods=["POST"])
@producteur_required
def optimize(tid):
    """Run the routing planner to set tournee_position on each stop."""
    with cursor() as cur:
        cur.execute("SELECT start_lat, start_lng, start_address FROM tournees WHERE id = %s",
                    (tid,))
        t = cur.fetchone()
        if t is None:
            flash("Tournée introuvable.", "danger")
            return redirect(url_for("tournees.index"))
        depot = {"lat": t[0], "lng": t[1]} if t[0] is not None else None
        cur.execute(
            "SELECT o.id, c.lat, c.lng, c.postal_code, c.city "
            "FROM orders o JOIN clients c ON c.id = o.client_id "
            "WHERE o.tournee_id = %s",
            (tid,))
        rows = cur.fetchall()
        stops = [
            {"id": r[0], "lat": r[1], "lng": r[2],
             "postal_code": r[3], "city": r[4]}
            for r in rows
        ]
        if not stops:
            flash("Aucune commande à ordonner.", "warning")
            return redirect(url_for("tournees.detail", tid=tid))
        ordered = plan_route(stops, depot)
        for s in ordered:
            cur.execute("UPDATE orders SET tournee_position = %s WHERE id = %s",
                        (s["position"], s["id"]))
    flash(f"Tournée optimisée ({len(ordered)} arrêts).", "success")
    return redirect(url_for("tournees.detail", tid=tid))


@bp.route("/<int:tid>/remove-order/<int:oid>", methods=["POST"])
@producteur_required
def remove_order(tid, oid):
    execute("UPDATE orders SET tournee_id = NULL, tournee_position = NULL "
            "WHERE id = %s AND tournee_id = %s", (oid, tid))
    flash("Commande retirée de la tournée.", "success")
    return redirect(url_for("tournees.detail", tid=tid))


@bp.route("/<int:tid>/status", methods=["POST"])
@producteur_required
def update_status(tid):
    status = request.form.get("status", "")
    if status not in {"planned","in_progress","done","cancelled"}:
        flash("Statut invalide.", "danger")
        return redirect(url_for("tournees.detail", tid=tid))
    execute("UPDATE tournees SET status = %s WHERE id = %s", (status, tid))
    flash("Statut tournée mis à jour.", "success")
    return redirect(url_for("tournees.detail", tid=tid))


@bp.route("/<int:tid>/delete", methods=["POST"])
@producteur_required
def delete(tid):
    execute("UPDATE orders SET tournee_id = NULL, tournee_position = NULL WHERE tournee_id = %s",
            (tid,))
    execute("DELETE FROM tournees WHERE id = %s", (tid,))
    flash("Tournée supprimée.", "success")
    return redirect(url_for("tournees.index"))
