"""Catalog of reusable values."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..catalog_service import (
    EXPLOITATION_CATEGORIES, add_item, category_label, delete_item,
    is_valid_exploitation_category, list_items, update_item,
)
from ..security import (
    login_required, get_session_context, producteur_required,
)


bp = Blueprint("catalog", __name__, url_prefix="/catalog")


@bp.route("/")
@login_required
def index():
    ctx = get_session_context()
    items = list_items()
    for it in items:
        it["category_label"] = category_label(it["category"])
    return render_template(
        "catalog/index.html", **ctx, items=items,
        categories=EXPLOITATION_CATEGORIES,
    )


@bp.route("/add", methods=["POST"])
@login_required
def create():
    category = (request.form.get("category") or "").strip()
    value = (request.form.get("value") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not category or not value:
        flash("Catégorie et valeur requises.", "warning")
        return redirect(url_for("catalog.index"))
    if not is_valid_exploitation_category(category):
        flash("Catégorie invalide.", "danger")
        return redirect(url_for("catalog.index"))
    add_item(category, value, description=description, created_by=session.get("user_id"))
    flash("Entrée ajoutée au catalogue.", "success")
    return redirect(url_for("catalog.index"))


@bp.route("/<int:item_id>/update", methods=["POST"])
@producteur_required
def update(item_id):
    value = (request.form.get("value") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "").strip()
    if not value:
        flash("La valeur ne peut pas être vide.", "warning")
        return redirect(url_for("catalog.index"))
    if category and not is_valid_exploitation_category(category):
        flash("Catégorie invalide.", "danger")
        return redirect(url_for("catalog.index"))
    ok = update_item(item_id, value=value, description=description or None,
                     category=category or None)
    flash("Entrée mise à jour." if ok else "Aucune modification.", "success" if ok else "warning")
    return redirect(url_for("catalog.index"))


@bp.route("/<int:item_id>/delete", methods=["POST"])
@producteur_required
def remove(item_id):
    delete_item(item_id)
    flash("Entrée supprimée.", "success")
    return redirect(url_for("catalog.index"))
