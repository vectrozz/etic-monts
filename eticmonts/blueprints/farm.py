"""Existing farm dashboard (surface / biodiv / plastique / soil / water / lutte)."""
from __future__ import annotations

import json

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)
from psycopg2 import errors

from ..db import cursor, execute
from ..security import login_required, get_session_context, producteur_required
from ..catalog_service import (
    EXPLOITATION_CATEGORIES, bump_usage, values_by_category,
)
from ..settings_store import get_delivery_cycle
from ..schedule import upcoming_slots
from ..config import load_config


bp = Blueprint("farm", __name__)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_farm_data(farm_id: int) -> dict:
    queries = {
        "ferme": ("SELECT id, farmname, adress, integration_year FROM fermes WHERE id = %s",
                  (farm_id,)),
        "surfaces": ("SELECT id, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre "
                     "FROM surface WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
        "biodiv": ("SELECT id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, "
                   "jachere, jacheremel, muret, description, biodivscore FROM biodiv "
                   "WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
        "plastique": ("SELECT id, year, surftotplast, surftottoile, paillagefr, paillagegf, "
                      "paillageleg, limitation, embplast, embplastpourcent, embfr, embgf, embleg "
                      "FROM plastique WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
        "soil": ("SELECT id, year, soilanalyse, connaissance, formation, pratique FROM soil "
                 "WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
        "water": ("SELECT id, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions "
                  "FROM water WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
        "lutte": ("SELECT id, year, achat, favorisation, formation FROM lutte "
                  "WHERE linked_id = %s ORDER BY year ASC", (farm_id,)),
    }
    out: dict = {}
    with cursor() as cur:
        for k, (q, p) in queries.items():
            cur.execute(q, p)
            out[k] = cur.fetchall() if k != "ferme" else cur.fetchall()
    # ferme returned as a list of rows for backwards-compat with existing templates
    return out


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/dashboard")
@login_required
def dashboard():
    ctx = get_session_context()
    data = fetch_farm_data(ctx["user_id"])
    catalog = values_by_category()
    catalog_labels = {k: l for k, l in EXPLOITATION_CATEGORIES}
    cfg = load_config()
    slots = [s.to_dict() for s in upcoming_slots(get_delivery_cycle(), tz_name=cfg.timezone, count=3)]
    return render_template("dashboard.html", **ctx, **data, catalog=catalog,
                           catalog_labels=catalog_labels, upcoming_slots=slots)


@bp.route("/fiche/<int:idferme>")
@login_required
def fiche(idferme):
    ctx = get_session_context()
    data = fetch_farm_data(idferme)
    return render_template("fiche.html", **ctx, **data)


@bp.route("/biodiv-detail/<int:idferme>")
@login_required
def biodiv_page(idferme):
    """Kept for backwards compatibility — same view, but biodiv graph also
    appears inline on dashboard now."""
    ctx = get_session_context()
    with cursor() as cur:
        cur.execute("SELECT id, farmname, adress, integration_year FROM fermes WHERE id = %s", (idferme,))
        ferme = cur.fetchall()
        cur.execute(
            "SELECT id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, "
            "jachere, jacheremel, muret, description, biodivscore FROM biodiv "
            "WHERE linked_id = %s ORDER BY year ASC", (idferme,))
        biodiv = cur.fetchall()
    return render_template("biodiv.html", **ctx, ferme=ferme, biodiv=biodiv)


# ---------------------------------------------------------------------------
# Form posts
# ---------------------------------------------------------------------------

def _f(name: str, default: float = 0.0) -> float:
    raw = request.form.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


@bp.route("/addsurf", methods=["POST"])
@producteur_required
def addsurf():
    uid = session["user_id"]
    year = int(request.form["year"])
    surffr = _f("surffr"); surfgf = _f("surfgf"); surfleg = _f("surfleg")
    prairie = _f("prairie"); culture = _f("culture"); surfautre = _f("surfautre")
    surftot = round(surffr + surfgf + surfleg + prairie + culture + surfautre, 4)
    execute(
        "INSERT INTO surface (linked_id, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uid, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre),
    )
    flash(f"Surface pour l'année {year} ajoutée", "success")
    return redirect(url_for("farm.dashboard"))


@bp.route("/addbiodiv", methods=["POST"])
@producteur_required
def addbiodiv():
    uid = session["user_id"]
    year = int(request.form["year"])
    fields = ["haie","arbrealign","arbreseul","bosquet","mare","fosse",
              "bordure","jachere","jacheremel","muret"]
    vals = {f: _f(f) for f in fields}
    description = request.form.get("description", "")

    coef = execute(
        "SELECT coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, "
        "coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie "
        "FROM coefbiodiv WHERE year = %s", (year,), fetch="one",
    )
    surfprairie = execute(
        "SELECT prairie FROM surface WHERE year = %s AND linked_id = %s",
        (year, uid), fetch="one",
    )

    if coef is None or surfprairie is None:
        biodivscore = 0
        msg = "Score indisponible (coefficients manquants)" if coef is None else "Score indisponible (pas de surface prairie)"
        flash(f"Biodiv {year} ajoutée — {msg}", "warning")
    else:
        ch, ca, cas, cb, cm, cf, cbd, cj, cjm, cmu, cp = [float(x) for x in coef]
        pr = float(surfprairie[0])
        biodivscore = (10000*cp*pr + ch*vals["haie"] + ca*vals["arbrealign"] +
                       cas*vals["arbreseul"] + cb*vals["bosquet"] + cm*vals["mare"] +
                       cf*vals["fosse"] + cbd*vals["bordure"] + cj*vals["jachere"] +
                       cjm*vals["jacheremel"] + cmu*vals["muret"])
        flash(f"Biodiv pour l'année {year} ajoutée", "success")

    execute(
        "INSERT INTO biodiv (linked_id, year, haie, arbrealign, arbreseul, bosquet, mare, "
        "fosse, bordure, jachere, jacheremel, muret, description, biodivscore) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uid, year, vals["haie"], vals["arbrealign"], vals["arbreseul"], vals["bosquet"],
         vals["mare"], vals["fosse"], vals["bordure"], vals["jachere"],
         vals["jacheremel"], vals["muret"], description, biodivscore),
    )
    return redirect(url_for("farm.dashboard"))


@bp.route("/addcoefbiodiv", methods=["POST"])
@producteur_required
def addcoefbiodiv():
    year = int(request.form["year"])
    fields = ["coefhaie","coefarbrealign","coefarbreseul","coefbosquet","coefmare",
              "coeffosse","coefbordure","coefjachere","coefjacheremel","coefmuret","coefprairie"]
    values = [float(request.form[f]) for f in fields]
    description = request.form.get("description", "")
    execute(
        "INSERT INTO coefbiodiv (year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, "
        "coefmare, coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie, description) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (year) DO UPDATE SET "
        "coefhaie=EXCLUDED.coefhaie, coefarbrealign=EXCLUDED.coefarbrealign, "
        "coefarbreseul=EXCLUDED.coefarbreseul, coefbosquet=EXCLUDED.coefbosquet, "
        "coefmare=EXCLUDED.coefmare, coeffosse=EXCLUDED.coeffosse, "
        "coefbordure=EXCLUDED.coefbordure, coefjachere=EXCLUDED.coefjachere, "
        "coefjacheremel=EXCLUDED.coefjacheremel, coefmuret=EXCLUDED.coefmuret, "
        "coefprairie=EXCLUDED.coefprairie, description=EXCLUDED.description",
        (year, *values, description),
    )
    flash(f"Coefficients biodiv {year} ajoutés", "success")
    return redirect(url_for("admin.coefbiodiv"))


def _catalog_text(name: str, category: str) -> str:
    raw = (request.form.get(name) or "").strip()
    if raw:
        bump_usage(category, [raw])
    return raw


@bp.route("/addplastic", methods=["POST"])
@producteur_required
def addplastic():
    uid = session["user_id"]
    try:
        year = int(request.form["year"])
        surftotplast = _f("surftotplast")
        surftottoile = _f("surftottoile")
        paillagefr = json.dumps(_catalog_text("paillagefr", "paillage"))
        paillagegf = json.dumps(_catalog_text("paillagegf", "paillage"))
        paillageleg = json.dumps(_catalog_text("paillageleg", "paillage"))
        limitation = json.dumps(_catalog_text("limitation", "limitation_plastique"))
        embplast = json.dumps(_catalog_text("embplast", "emballage"))
        embplastpourcent = request.form.get("embplastpourcent") or 0
        embfr = json.dumps(_catalog_text("embfr", "emballage"))
        embgf = json.dumps(_catalog_text("embgf", "emballage"))
        embleg = json.dumps(_catalog_text("embleg", "emballage"))
        execute(
            "INSERT INTO plastique (linked_id, year, surftotplast, surftottoile, paillagefr, "
            "paillagegf, paillageleg, limitation, embplast, embplastpourcent, embfr, embgf, embleg) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, year, surftotplast, surftottoile, paillagefr, paillagegf, paillageleg,
             limitation, embplast, embplastpourcent, embfr, embgf, embleg),
        )
        flash(f"Plastique pour l'année {year} ajouté", "success")
    except errors.CheckViolation:
        flash("Erreur de validation : vérifiez vos données.", "danger")
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("farm.dashboard"))


@bp.route("/addsoil", methods=["POST"])
@producteur_required
def addsoil():
    uid = session["user_id"]
    year = int(request.form["year"])
    analyse = json.dumps(_catalog_text("analyse", "analyse_sol"))
    connaissance = int(request.form.get("connaissance") or 0)
    formation = json.dumps(_catalog_text("formation", "formation_sol"))
    pratique = json.dumps(_catalog_text("pratique", "pratique_sol"))
    execute(
        "INSERT INTO soil (linked_id, year, soilanalyse, connaissance, formation, pratique) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (uid, year, analyse, connaissance, formation, pratique),
    )
    flash(f"Données sol {year} ajoutées", "success")
    return redirect(url_for("farm.dashboard"))


@bp.route("/addwater", methods=["POST"])
@producteur_required
def addwater():
    uid = session["user_id"]
    year = int(request.form["year"])
    matosirrigfr = json.dumps(_catalog_text("matosirrigfr", "irrigation"))
    matosirriggf = json.dumps(_catalog_text("matosirriggf", "irrigation"))
    matosirrigleg = json.dumps(_catalog_text("matosirrigleg", "irrigation"))
    consoeau = int(request.form.get("consoeau") or 0)
    actions = json.dumps(_catalog_text("actions", "action_eau"))
    execute(
        "INSERT INTO water (linked_id, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (uid, year, matosirrigfr, matosirriggf, matosirrigleg, consoeau, actions),
    )
    flash(f"Données eau {year} ajoutées", "success")
    return redirect(url_for("farm.dashboard"))


@bp.route("/addlutte", methods=["POST"])
@producteur_required
def addlutte():
    uid = session["user_id"]
    year = int(request.form["year"])
    achat = json.dumps(_catalog_text("achat", "lutte_achat"))
    favorisation = json.dumps(_catalog_text("favorisation", "lutte_favorisation"))
    formation = json.dumps(_catalog_text("formation", "lutte_formation"))
    execute(
        "INSERT INTO lutte (linked_id, year, achat, favorisation, formation) "
        "VALUES (%s,%s,%s,%s,%s)",
        (uid, year, achat, favorisation, formation),
    )
    flash(f"Lutte intégrée {year} ajoutée", "success")
    return redirect(url_for("farm.dashboard"))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

DELETABLE_TABLES = {
    "surface": "DELETE FROM surface WHERE id = %s",
    "biodiv": "DELETE FROM biodiv WHERE id = %s",
    "coefbiodiv": "DELETE FROM coefbiodiv WHERE id = %s",
    "plastique": "DELETE FROM plastique WHERE id = %s",
    "soil": "DELETE FROM soil WHERE id = %s",
    "water": "DELETE FROM water WHERE id = %s",
    "lutte": "DELETE FROM lutte WHERE id = %s",
}


@bp.route("/delete/<table>/<int:idtodel>")
@producteur_required
def delete_row(table, idtodel):
    if table not in DELETABLE_TABLES:
        flash("Table invalide", "danger")
        return redirect(url_for("farm.dashboard"))
    execute(DELETABLE_TABLES[table], (idtodel,))
    flash("Ligne supprimée avec succès.", "success")
    if table == "coefbiodiv":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("farm.dashboard"))
