"""Product (vegetables) catalog management."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute
from ..security import login_required, admin_required, producteur_required, get_session_context
from ..catalog_service import bump_usage, values_by_category


bp = Blueprint("products", __name__, url_prefix="/products")


def _form_decimal(name: str) -> float | None:
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
    from ..emoji_map import detect_emoji
    ctx = get_session_context()
    rows = execute(
        "SELECT id, name, category, unit, unit_weight_kg, unit_volume_l, default_price, "
        "is_active, description, emoji FROM products ORDER BY is_active DESC, name",
        fetch="all", dict_rows=True,
    ) or []
    products_list = []
    for r in rows:
        d = dict(r)
        d["emoji_effective"] = d.get("emoji") or detect_emoji(d["name"], d.get("category"))
        products_list.append(d)
    categories = sorted(values_by_category().get("produit_categorie", []))
    return render_template("products/index.html", **ctx, products=products_list, categories=categories)


@bp.route("/create", methods=["POST"])
@producteur_required
def create():
    from ..emoji_map import detect_emoji
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Nom du produit requis.", "warning")
        return redirect(url_for("products.index"))
    category = (request.form.get("category") or "").strip() or None
    unit = (request.form.get("unit") or "kg").strip()
    description = (request.form.get("description") or "").strip() or None
    weight = _form_decimal("unit_weight_kg")
    volume = _form_decimal("unit_volume_l")
    price = _form_decimal("default_price")
    emoji = (request.form.get("emoji") or "").strip() or detect_emoji(name, category)
    try:
        execute(
            "INSERT INTO products (name, category, unit, unit_weight_kg, unit_volume_l, "
            "default_price, description, emoji) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (name, category, unit, weight, volume, price, description, emoji),
        )
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
        return redirect(url_for("products.index"))
    if category:
        bump_usage("produit_categorie", [category])
    flash(f"Produit {emoji} {name} créé.", "success")
    return redirect(url_for("products.index"))


@bp.route("/<int:pid>/update", methods=["POST"])
@producteur_required
def update(pid):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Nom requis.", "warning")
        return redirect(url_for("products.index"))
    category = (request.form.get("category") or "").strip() or None
    unit = (request.form.get("unit") or "kg").strip()
    description = (request.form.get("description") or "").strip() or None
    weight = _form_decimal("unit_weight_kg")
    volume = _form_decimal("unit_volume_l")
    price = _form_decimal("default_price")
    emoji = (request.form.get("emoji") or "").strip() or None
    is_active = request.form.get("is_active") == "on"
    execute(
        "UPDATE products SET name=%s, category=%s, unit=%s, unit_weight_kg=%s, "
        "unit_volume_l=%s, default_price=%s, description=%s, is_active=%s, "
        "emoji=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (name, category, unit, weight, volume, price, description, is_active, emoji, pid),
    )
    if category:
        bump_usage("produit_categorie", [category])
    flash("Produit mis à jour.", "success")
    return redirect(url_for("products.index"))


@bp.route("/<int:pid>/delete", methods=["POST"])
@admin_required
def delete(pid):
    try:
        execute("DELETE FROM products WHERE id = %s", (pid,))
        flash("Produit supprimé.", "success")
    except Exception as e:
        flash(f"Suppression impossible : {e}", "danger")
    return redirect(url_for("products.index"))
