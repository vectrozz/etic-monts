"""Public auth + landing routes."""
from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, session, url_for,
)

from .. import bcrypt
from ..db import execute
from ..security import ROLE_ADMIN, ROLE_PRODUCTEUR, ROLE_CLIENT, login_required


bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    if session.get("username"):
        return redirect(url_for("farm.dashboard"))
    return render_template("index.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    name = (request.form.get("name") or "").strip()
    password = request.form.get("userpass") or ""
    if not name or not password:
        flash("Identifiant et mot de passe requis.", "danger")
        return redirect(url_for("main.login"))

    row = execute(
        "SELECT id, userpass, role, is_active, created_date FROM fermes WHERE name = %s",
        (name,), fetch="one",
    )
    if row is None:
        flash("Utilisateur non trouvé", "danger")
        return redirect(url_for("main.login"))

    user_id, hashed, role, is_active, created_date = row
    if not is_active:
        flash("Ce compte est désactivé.", "danger")
        return redirect(url_for("main.login"))
    if not bcrypt.check_password_hash(hashed, password):
        flash("Mot de passe incorrect", "danger")
        return redirect(url_for("main.login"))

    session.clear()
    session["user_id"] = user_id
    session["username"] = name
    session["role"] = role or ROLE_PRODUCTEUR
    session["created_date"] = created_date
    session["last_login_date"] = datetime.now()
    execute("UPDATE fermes SET last_login_date = %s WHERE id = %s",
            (datetime.now(), user_id))

    flash("Connexion réussie", "success")
    if session["role"] == ROLE_ADMIN:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("farm.dashboard"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    cfg = current_app.config["APP_CONFIG"]
    valid_token = cfg.register_token

    if request.method == "GET" and not session.get("register_authorized"):
        return render_template("register_token.html")

    if request.method == "POST" and "register_token" in request.form:
        if request.form["register_token"] == valid_token and valid_token:
            session["register_authorized"] = True
            return redirect(url_for("main.register"))
        flash("Token invalide.", "danger")
        return redirect(url_for("main.register"))

    if request.method == "GET":
        return render_template("register.html")

    if not session.get("register_authorized"):
        flash("Accès non autorisé.", "danger")
        return redirect(url_for("main.register"))

    name = (request.form.get("name") or "").strip()
    password = request.form.get("userpass") or ""
    confirm = request.form.get("userpass1") or ""
    farmname = (request.form.get("farmname") or "").strip()
    adress = (request.form.get("adress") or "").strip()
    integration_year = (request.form.get("integration_year") or "").strip()

    if not name or not password:
        flash("Identifiant et mot de passe requis.", "danger")
        return redirect(url_for("main.register"))
    if password != confirm:
        flash("Les mots de passe ne correspondent pas", "warning")
        return redirect(url_for("main.register"))
    if len(password) < 8:
        flash("Mot de passe trop court (8 caractères minimum).", "warning")
        return redirect(url_for("main.register"))

    existing = execute("SELECT id FROM fermes WHERE name = %s", (name,), fetch="one")
    if existing is not None:
        flash("Cet utilisateur existe déjà", "warning")
        return redirect(url_for("main.register"))

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    # First-run: if no admin exists yet, the first registered user becomes admin.
    existing_admin = execute(
        "SELECT id FROM fermes WHERE role = 'admin' LIMIT 1", fetch="one",
    )
    role = "producteur" if existing_admin else "admin"
    try:
        execute(
            "INSERT INTO fermes (name, userpass, farmname, adress, integration_year, role) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (name, hashed, farmname, adress, integration_year, role),
        )
    except Exception as e:
        flash(f"Erreur lors de la création du compte : {e}", "danger")
        return redirect(url_for("main.register"))

    session.pop("register_authorized", None)
    if role == "admin":
        flash(f"Compte {name} créé en tant qu'administrateur (premier compte). Connectez-vous.",
              "success")
    else:
        flash(f"Le compte {name} a été créé avec succès ! Connectez-vous.", "success")
    return redirect(url_for("main.login"))


@bp.route("/logout")
def logout():
    next_hint = request.args.get("next")
    session.clear()
    if next_hint == "admin":
        flash("Connectez-vous avec un compte administrateur pour accéder au panneau d'admin.",
              "warning")
        return redirect(url_for("main.login"))
    return redirect(url_for("main.home"))


# ---- Backwards-compatible aliases (so old templates/url_for keep working) --
@bp.route("/__alias_login")
def _alias_login():
    return redirect(url_for("main.login"))
