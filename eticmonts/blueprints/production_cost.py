"""Coût de revient — one page per crop, one campaign (year) at a time."""
from __future__ import annotations

import csv
import io
from datetime import date

from flask import (
    Blueprint, Response, abort, flash, redirect, render_template, request,
    session, url_for,
)

from ..production_cost import (
    CROPS, MIN_PEERS, compute, delete as cost_delete, get_crop, list_all,
    list_for_farm, network_benchmark, upsert as cost_upsert,
)
from ..security import (
    admin_required, get_session_context, login_required, producteur_required,
)


bp = Blueprint("production_cost", __name__, url_prefix="/cout-de-revient")

NEW = "nouvelle"


def _crop_or_404(slug: str):
    crop = get_crop(slug)
    if crop is None:
        abort(404)
    return crop


def _number(name: str, errors: list[str], label: str) -> float | None:
    """Parse a non-negative number; accepts French decimal commas."""
    raw = (request.form.get(name) or "").strip().replace(" ", "").replace(" ", "")
    if not raw:
        return None
    try:
        v = float(raw.replace(",", "."))
    except ValueError:
        errors.append(label)
        return None
    if v < 0:
        errors.append(label)
        return None
    return v


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    first = next(iter(CROPS))
    return redirect(url_for("production_cost.view", crop=first))


@bp.route("/<crop>")
@login_required
def view(crop):
    crop_def = _crop_or_404(crop)
    ctx = get_session_context()
    entries = list_for_farm(session["user_id"], crop)
    for e in entries:
        e["calc"] = compute(e, crop_def)

    years = [e["year"] for e in entries]
    wanted = request.args.get("annee")
    if wanted == NEW or not entries:
        current = None
    else:
        try:
            wanted_year = int(wanted) if wanted else years[-1]
        except ValueError:
            wanted_year = years[-1]
        current = next((e for e in entries if e["year"] == wanted_year), entries[-1])

    # Suggest the next free campaign year for a new entry.
    this_year = date.today().year
    suggested = this_year if this_year not in years else max(years) + 1
    previous = entries[-1] if entries else None

    # €/kg split per campaign, for the history chart.
    history = []
    for e in entries:
        c, kg = e["calc"], e.get("yield_kg")
        if not kg:
            continue
        history.append({
            "year": e["year"],
            "labour": (c["labour_cost"] or 0) / kg,
            "inputs": c["inputs_total"] / kg,
            "structure": c["structure_total"] / kg,
            "price": e.get("sale_price"),
        })

    return render_template(
        "production_cost/index.html", **ctx,
        crop=crop_def, entries=entries, current=current,
        calc=current["calc"] if current else compute({}, crop_def),
        suggested_year=suggested, previous=previous,
        benchmark=network_benchmark(crop_def), min_peers=MIN_PEERS,
        mine={e["year"]: e["calc"] for e in entries},
        history_series=history, new_key=NEW,
    )


@bp.route("/<crop>", methods=["POST"])
@producteur_required
def save(crop):
    crop_def = _crop_or_404(crop)
    errors: list[str] = []

    year_raw = (request.form.get("year") or "").strip()
    try:
        year = int(year_raw)
    except ValueError:
        year = 0
    if not 2010 <= year <= 2100:
        flash("Indiquez une année de campagne valide (2010–2100).", "danger")
        return redirect(url_for("production_cost.view", crop=crop, annee=NEW))

    nb = _number("nb_units", errors, f"nombre de {crop_def.unit_label}")
    system = request.form.get("system") or None
    if system not in {k for k, _ in crop_def.systems}:
        system = None

    tasks = {}
    for t in crop_def.tasks:
        v = _number(f"task_{t.key}", errors, t.label)
        if v is not None:
            tasks[t.key] = v
    charges = {}
    for c in crop_def.inputs + crop_def.structure:
        v = _number(f"charge_{c.key}", errors, c.label)
        if v is not None:
            charges[c.key] = v

    created = cost_upsert(
        farm_id=session["user_id"], crop=crop, year=year,
        nb_units=int(nb) if nb is not None else None,
        surface_m2=_number("surface_m2", errors, "surface"),
        variety=(request.form.get("variety") or "").strip()[:120] or None,
        system=system,
        yield_kg=_number("yield_kg", errors, "récolte commercialisée"),
        sale_price=_number("sale_price", errors, "prix de vente"),
        hourly_cost=_number("hourly_cost", errors, "coût horaire"),
        tasks=tasks, charges=charges,
        notes=(request.form.get("notes") or "").strip() or None,
    )
    if errors:
        flash("Valeurs ignorées (nombre positif attendu) : " + ", ".join(errors) + ".", "warning")
    verb = "créée" if created else "mise à jour"
    flash(f"Campagne {year} {verb}.", "success")
    return redirect(url_for("production_cost.view", crop=crop, annee=year))


@bp.route("/<crop>/<int:cid>/supprimer", methods=["POST"])
@producteur_required
def delete(crop, cid):
    _crop_or_404(crop)
    if cost_delete(cid, session["user_id"]):
        flash("Campagne supprimée.", "success")
    return redirect(url_for("production_cost.view", crop=crop))


# ---------------------------------------------------------------------------
# Admin — every farm, every campaign
# ---------------------------------------------------------------------------

@bp.route("/<crop>/reseau")
@admin_required
def network(crop):
    crop_def = _crop_or_404(crop)
    ctx = get_session_context()
    entries = list_all(crop)
    for e in entries:
        e["calc"] = compute(e, crop_def)
    return render_template(
        "production_cost/network.html", **ctx, crop=crop_def, entries=entries,
        benchmark=network_benchmark(crop_def), min_peers=MIN_PEERS,
    )


@bp.route("/<crop>/reseau.csv")
@admin_required
def network_csv(crop):
    crop_def = _crop_or_404(crop)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    head = ["ferme", "annee", "variete", "systeme", crop_def.unit_label, "surface_m2",
            "recolte_kg", "prix_vente_eur_kg", "cout_horaire_eur_h", "heures_total",
            "heures_1000m2", "cout_mo_eur", "intrants_eur", "structure_eur",
            "cout_total_eur", "cout_revient_eur_kg", "marge_eur_kg", "remuneration_horaire_eur_h"]
    head += [f"h_{t.key}" for t in crop_def.tasks]
    head += [f"eur_{c.key}" for c in crop_def.inputs + crop_def.structure]
    w.writerow(head)

    def n(v):
        return "" if v is None else str(round(v, 4)).replace(".", ",")

    for e in list_all(crop):
        c = compute(e, crop_def)
        row = [e["farmname"] or e["login"], e["year"], e.get("variety") or "",
               e.get("system") or "", n(e.get("nb_units")), n(e.get("surface_m2")),
               n(e.get("yield_kg")), n(e.get("sale_price")), n(e.get("hourly_cost")),
               n(c["hours_total"]), n(c["hours_per_1000m2"]), n(c["labour_cost"]),
               n(c["inputs_total"]), n(c["structure_total"]), n(c["total_cost"]),
               n(c["cost_per_kg"]), n(c["margin_per_kg"]), n(c["hourly_return"])]
        row += [n(e["tasks"].get(t.key)) for t in crop_def.tasks]
        row += [n(e["charges"].get(k.key)) for k in crop_def.inputs + crop_def.structure]
        w.writerow(row)
    # BOM so Excel opens accents correctly.
    return Response(
        "﻿" + buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cout-revient-{crop}.csv"},
    )
