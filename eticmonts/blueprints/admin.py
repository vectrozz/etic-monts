"""Admin overview: monitoring, network synthesis, user management."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import bcrypt
from ..db import cursor, execute
from ..security import admin_required, get_session_context, ROLE_ADMIN, ROLE_PRODUCTEUR, ROLE_CLIENT, ALL_ROLES


bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def dashboard():
    ctx = get_session_context()
    with cursor() as cur:
        cur.execute("SELECT id, name, farmname, adress, integration_year, role, is_active FROM fermes ORDER BY role, farmname")
        ferme = cur.fetchall()

        cur.execute("""
            SELECT year, SUM(surftot), SUM(surffr), SUM(surfgf), SUM(surfleg),
                   SUM(prairie), SUM(culture), SUM(surfautre)
            FROM surface GROUP BY year ORDER BY year;
        """)
        surface_sums = cur.fetchall()

        cur.execute("""
            SELECT year, SUM(haie), SUM(arbrealign), SUM(arbreseul), SUM(bosquet),
                   SUM(mare), SUM(fosse), SUM(bordure), SUM(jachere),
                   SUM(jacheremel), SUM(muret), SUM(biodivscore)
            FROM biodiv GROUP BY year ORDER BY year;
        """)
        biodiv_sum = cur.fetchall()

        cur.execute("""
            SELECT b.year,
                   SUM(b.biodivscore) AS total_biodivscore,
                   SUM(s.surftot) AS total_surftot,
                   CASE WHEN SUM(s.surftot) != 0
                        THEN SUM(b.biodivscore) / SUM(s.surftot) ELSE NULL END AS ratio
            FROM biodiv b
            JOIN surface s ON b.year = s.year AND b.linked_id = s.linked_id
            GROUP BY b.year ORDER BY b.year;
        """)
        biodiv_ratios = cur.fetchall()

        cur.execute(
            "SELECT id, year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, "
            "coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie, description "
            "FROM coefbiodiv ORDER BY year"
        )
        coefbiodiv = cur.fetchall()

        # Marketplace KPIs
        cur.execute("SELECT COUNT(*) FROM products WHERE is_active")
        products_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clients WHERE is_active")
        clients_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*), COALESCE(SUM(total_amount),0) FROM orders WHERE status != 'cancelled'")
        row = cur.fetchone()
        orders_count, orders_total = row[0], float(row[1] or 0)
        cur.execute(
            "SELECT delivery_date, COUNT(*) FROM tournees GROUP BY delivery_date "
            "ORDER BY delivery_date DESC LIMIT 5"
        )
        recent_tournees = cur.fetchall()

    ratios = [{
        "year": r[0],
        "total_biodivscore": float(r[1]) if r[1] is not None else None,
        "total_surftot": float(r[2]) if r[2] is not None else None,
        "ratio": round(float(r[3]), 4) if r[3] is not None else None,
    } for r in biodiv_ratios]

    kpis = {
        "ferme_count": len(ferme),
        "products_count": products_count,
        "clients_count": clients_count,
        "orders_count": orders_count,
        "orders_total": orders_total,
        "recent_tournees": recent_tournees,
    }

    return render_template(
        "admin/dashboard.html",
        **ctx, ferme=ferme, surface_sums=surface_sums, biodiv_sum=biodiv_sum,
        ratios=ratios, coefbiodiv=coefbiodiv, kpis=kpis,
    )


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@bp.route("/coefbiodiv")
@admin_required
def coefbiodiv():
    ctx = get_session_context()
    rows = execute(
        "SELECT id, year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, "
        "coefmare, coeffosse, coefbordure, coefjachere, coefjacheremel, coefmuret, "
        "coefprairie, description FROM coefbiodiv ORDER BY year",
        fetch="all",
    ) or []
    return render_template("admin/coefbiodiv.html", **ctx, coefbiodiv=rows)


@bp.route("/coefbiodiv/<int:cid>/update", methods=["POST"])
@admin_required
def coefbiodiv_update(cid):
    fields = ["coefhaie","coefarbrealign","coefarbreseul","coefbosquet","coefmare",
              "coeffosse","coefbordure","coefjachere","coefjacheremel","coefmuret","coefprairie"]
    try:
        values = [float(request.form[f]) for f in fields]
    except (KeyError, ValueError):
        flash("Valeurs invalides.", "danger")
        return redirect(url_for("admin.coefbiodiv"))
    description = request.form.get("description") or None
    try:
        year = int(request.form["year"])
    except (KeyError, ValueError):
        flash("Année invalide.", "danger")
        return redirect(url_for("admin.coefbiodiv"))
    execute(
        "UPDATE coefbiodiv SET year=%s, coefhaie=%s, coefarbrealign=%s, coefarbreseul=%s, "
        "coefbosquet=%s, coefmare=%s, coeffosse=%s, coefbordure=%s, coefjachere=%s, "
        "coefjacheremel=%s, coefmuret=%s, coefprairie=%s, description=%s WHERE id=%s",
        (year, *values, description, cid),
    )
    flash(f"Coefficients {year} mis à jour.", "success")
    return redirect(url_for("admin.coefbiodiv"))


@bp.route("/coefbiodiv/<int:cid>/delete", methods=["POST"])
@admin_required
def coefbiodiv_delete(cid):
    execute("DELETE FROM coefbiodiv WHERE id = %s", (cid,))
    flash("Coefficients supprimés.", "success")
    return redirect(url_for("admin.coefbiodiv"))


@bp.route("/users")
@admin_required
def users():
    ctx = get_session_context()
    rows = execute(
        "SELECT id, name, farmname, role, is_active, contact_email, contact_phone, "
        "adress, last_login_date FROM fermes ORDER BY role, name",
        fetch="all",
    ) or []
    return render_template("admin/users.html", **ctx, users=rows, roles=ALL_ROLES)


@bp.route("/users/<int:uid>/role", methods=["POST"])
@admin_required
def set_user_role(uid):
    role = request.form.get("role", "").strip()
    if role not in ALL_ROLES:
        flash("Rôle invalide.", "danger")
        return redirect(url_for("admin.users"))
    execute("UPDATE fermes SET role = %s WHERE id = %s", (role, uid))
    flash("Rôle mis à jour.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_user(uid):
    execute("UPDATE fermes SET is_active = NOT is_active WHERE id = %s", (uid,))
    flash("Statut compte mis à jour.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def reset_password(uid):
    new_pw = request.form.get("new_password") or ""
    if len(new_pw) < 8:
        flash("Mot de passe trop court (8 caractères minimum).", "warning")
        return redirect(url_for("admin.users"))
    pwhash = bcrypt.generate_password_hash(new_pw).decode("utf-8")
    execute("UPDATE fermes SET userpass = %s WHERE id = %s", (pwhash, uid))
    flash("Mot de passe réinitialisé.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    name = (request.form.get("name") or "").strip()
    role = (request.form.get("role") or ROLE_PRODUCTEUR).strip()
    farmname = (request.form.get("farmname") or "").strip()
    password = request.form.get("password") or ""
    if not name or len(password) < 8 or role not in ALL_ROLES:
        flash("Nom, mot de passe (>=8) et rôle valides requis.", "warning")
        return redirect(url_for("admin.users"))
    existing = execute("SELECT id FROM fermes WHERE name = %s", (name,), fetch="one")
    if existing:
        flash("Cet identifiant existe déjà.", "warning")
        return redirect(url_for("admin.users"))
    pwhash = bcrypt.generate_password_hash(password).decode("utf-8")
    execute(
        "INSERT INTO fermes (name, userpass, farmname, role) VALUES (%s,%s,%s,%s)",
        (name, pwhash, farmname, role),
    )
    flash(f"Utilisateur {name} créé.", "success")
    return redirect(url_for("admin.users"))
