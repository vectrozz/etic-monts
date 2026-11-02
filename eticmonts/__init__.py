"""Application factory."""
from __future__ import annotations

import logging
import os
import time

from flask import Flask, render_template, session
from flask_bcrypt import Bcrypt

from .config import load_config
from .db import init_pool
from .schema import bootstrap_schema

bcrypt = Bcrypt()
log = logging.getLogger(__name__)

APP_VERSION = "3.1"

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app() -> Flask:
    if not logging.getLogger().handlers:  # gunicorn leaves the root logger bare
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [%(process)d] [%(levelname)s] %(name)s: %(message)s")
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )
    cfg = load_config()
    app.secret_key = cfg.secret_key
    app.config["APP_CONFIG"] = cfg
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if cfg.is_production:
        # HTTPS in prod; set SESSION_COOKIE_SECURE=0 to test a prod build over plain HTTP.
        app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"
        if cfg.secret_key == "dev-secret-change-me":
            log.warning("SECRET_KEY is not set — sessions are signed with the dev key.")

    bcrypt.init_app(app)
    init_pool(cfg)
    bootstrap_schema(cfg.features)
    _maybe_bootstrap_admin(cfg)

    _register_blueprints(app, cfg)
    _register_template_helpers(app, cfg)
    return app


def _register_blueprints(app: Flask, cfg) -> None:
    # ---- core: auth, MAEC dashboard, admin, settings, shared catalog ----
    from .blueprints.main import bp as main_bp
    from .blueprints.farm import bp as farm_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.catalog import bp as catalog_bp
    from .blueprints.settings_bp import bp as settings_bp

    for bp in (main_bp, farm_bp, admin_bp, catalog_bp, settings_bp):
        app.register_blueprint(bp)

    # ---- coût de revient ----
    if cfg.has("cout_revient"):
        from .blueprints.production_cost import bp as production_cost_bp
        app.register_blueprint(production_cost_bp)

    # ---- marketplace: products, stocks, clients, orders, public links, rounds ----
    if cfg.has("marketplace"):
        from .blueprints.products import bp as products_bp
        from .blueprints.stocks import bp as stocks_bp
        from .blueprints.clients import bp as clients_bp
        from .blueprints.orders import bp as orders_bp
        from .blueprints.tournees import bp as tournees_bp
        from .blueprints.public import bp as public_bp

        for bp in (products_bp, stocks_bp, clients_bp, orders_bp, tournees_bp, public_bp):
            app.register_blueprint(bp)


def _register_template_helpers(app: Flask, cfg) -> None:
    from .security import is_admin
    from .settings_store import get_branding
    from .formatting import fr_num, fr_money, input_num

    app.add_template_filter(fr_num, "fr_num")
    app.add_template_filter(fr_money, "fr_money")
    app.add_template_filter(input_num, "input_num")

    # Cache-bust static assets on every deploy (the prod image is rebuilt).
    try:
        css_mtime = str(int(os.path.getmtime(os.path.join(app.static_folder, "style.css"))))
    except OSError:
        css_mtime = str(int(time.time()))

    @app.context_processor
    def inject_globals():
        crops: list[dict] = []
        user_photo = None
        if cfg.has("cout_revient"):
            from .production_cost import known_crops
            crops = known_crops()
        uid = session.get("user_id")
        if uid:
            try:
                from .db import execute
                row = execute("SELECT photo_path FROM fermes WHERE id = %s", (uid,), fetch="one")
                user_photo = row[0] if row and row[0] else None
            except Exception:  # never break page rendering on an avatar lookup
                log.exception("photo lookup failed")
        return {
            "is_admin": is_admin,
            "feature": cfg.has,
            "branding": get_branding(),
            "static_version": css_mtime,
            "app_version": APP_VERSION,
            "production_crops": crops,
            "user_photo": user_photo,
        }

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404


def _maybe_bootstrap_admin(cfg) -> None:
    """Ensure an admin exists when BOOTSTRAP_ADMIN_USER is set.

    * If no admin exists and the user already exists → promote it to admin
      (its password is left untouched).
    * If no admin exists and the user does not exist → create it with
      BOOTSTRAP_ADMIN_PASSWORD.

    Written without ``ON CONFLICT (name)`` because v2 databases may lack the
    UNIQUE constraint on fermes.name.
    """
    if not cfg.bootstrap_admin_user:
        return
    from .db import execute
    if execute("SELECT 1 FROM fermes WHERE role = 'admin' LIMIT 1", fetch="one"):
        return
    promoted = execute(
        "UPDATE fermes SET role = 'admin' WHERE name = %s RETURNING id",
        (cfg.bootstrap_admin_user,), fetch="one",
    )
    if promoted:
        log.info("Promoted existing user %r to admin", cfg.bootstrap_admin_user)
        return
    if not cfg.bootstrap_admin_password:
        log.warning("BOOTSTRAP_ADMIN_USER %r not found and no BOOTSTRAP_ADMIN_PASSWORD set",
                    cfg.bootstrap_admin_user)
        return
    pwhash = bcrypt.generate_password_hash(cfg.bootstrap_admin_password).decode("utf-8")
    execute(
        "INSERT INTO fermes (name, userpass, farmname, role, integration_year) "
        "VALUES (%s, %s, %s, 'admin', %s)",
        (cfg.bootstrap_admin_user, pwhash, "Administrateur", "2024"),
    )
    log.info("Created admin user %r", cfg.bootstrap_admin_user)
