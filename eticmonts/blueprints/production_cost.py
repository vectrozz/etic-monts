"""Per-crop production cost — work hours per task, per year, per farm."""
from __future__ import annotations

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session, url_for,
)

from ..production_cost import (
    delete as cost_delete,
    get_crop,
    hours_per_1000m2,
    known_crops,
    list_for_farm,
    total_hours,
    upsert as cost_upsert,
)
from ..security import login_required, get_session_context, producteur_required


bp = Blueprint("production_cost", __name__, url_prefix="/cout-production")


def _f(name: str) -> float | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _i(name: str) -> int | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


@bp.route("/<crop>")
@login_required
def view(crop):
    crop_def = get_crop(crop)
    if crop_def is None:
        abort(404)
    ctx = get_session_context()
    rows = list_for_farm(session["user_id"], crop)
    # enrich with totals
    for r in rows:
        r["total_hours"] = total_hours(r["tasks"], crop_def)
        r["per_1000m2"] = hours_per_1000m2(r["total_hours"], r["surface_m2"])
    return render_template(
        "production_cost/index.html", **ctx, crop=crop, crop_def=crop_def,
        rows=rows, crops=known_crops(),
    )


@bp.route("/<crop>/upsert", methods=["POST"])
@producteur_required
def upsert(crop):
    crop_def = get_crop(crop)
    if crop_def is None:
        abort(404)
    year = _i("year")
    if year is None or year < 2010 or year > 2100:
        flash("Année invalide.", "danger")
        return redirect(url_for("production_cost.view", crop=crop))

    nb_units = _i("nb_units")
    surface_m2 = _f("surface_m2")
    notes = (request.form.get("notes") or "").strip() or None

    tasks = {}
    for key, _label in crop_def["tasks"]:
        v = _f(key)
        if v is not None:
            tasks[key] = v

    cost_upsert(
        farm_id=session["user_id"], crop=crop, year=year,
        nb_units=nb_units, surface_m2=surface_m2,
        tasks=tasks, notes=notes,
    )
    flash(f"Données {crop_def['label']} pour {year} enregistrées.", "success")
    return redirect(url_for("production_cost.view", crop=crop))


@bp.route("/<crop>/<int:cid>/delete", methods=["POST"])
@producteur_required
def delete(crop, cid):
    crop_def = get_crop(crop)
    if crop_def is None:
        abort(404)
    cost_delete(cid, session["user_id"])
    flash("Année supprimée.", "success")
    return redirect(url_for("production_cost.view", crop=crop))
