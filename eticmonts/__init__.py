"""Application factory."""
from __future__ import annotations

from flask import Flask
from flask_bcrypt import Bcrypt

from .config import load_config
from .db import init_pool
from .schema import bootstrap_schema

bcrypt = Bcrypt()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    cfg = load_config()
    app.secret_key = cfg.secret_key
    app.config["APP_CONFIG"] = cfg

    bcrypt.init_app(app)
    init_pool(cfg)
    bootstrap_schema()
    _maybe_bootstrap_admin(cfg)

    # ---- blueprints ----
    from .blueprints.main import bp as main_bp
    from .blueprints.farm import bp as farm_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.catalog import bp as catalog_bp
    from .blueprints.products import bp as products_bp
    from .blueprints.stocks import bp as stocks_bp
    from .blueprints.clients import bp as clients_bp
    from .blueprints.orders import bp as orders_bp
    from .blueprints.tournees import bp as tournees_bp
    from .blueprints.settings_bp import bp as settings_bp
    from .blueprints.public import bp as public_bp
    from .blueprints.production_cost import bp as production_cost_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(farm_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(tournees_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(production_cost_bp)

    # ---- template helpers ----
    from .security import is_admin
    from .settings_store import get_branding

    import os, time
    # Compute static-asset mtimes once at startup so the URL cache-busts
    # whenever style.css is rebuilt (the prod image is rebuilt on each deploy).
    _static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    try:
        _css_mtime = str(int(os.path.getmtime(os.path.join(_static_dir, "style.css"))))
    except OSError:
        _css_mtime = str(int(time.time()))

    from flask import session

    @app.context_processor
    def inject_globals():
        crops: list[dict] = []
        user_photo = None
        try:
            from .production_cost import known_crops
            crops = known_crops()
        except Exception:
            pass
        try:
            uid = session.get("user_id")
            if uid:
                from .db import execute as _exec
                row = _exec("SELECT photo_path FROM fermes WHERE id = %s",
                            (uid,), fetch="one")
                user_photo = row[0] if row and row[0] else None
        except Exception:
            pass
        return {
            "is_admin": is_admin,
            "branding": get_branding(),
            "static_version": _css_mtime,
            "production_crops": crops,
            "user_photo": user_photo,
        }

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("404.html"), 404

    return app


def _maybe_bootstrap_admin(cfg) -> None:
    """If BOOTSTRAP_ADMIN_USER/PASSWORD are set and no admin exists, create one."""
    if not cfg.bootstrap_admin_user or not cfg.bootstrap_admin_password:
        return
    from .db import execute
    existing = execute("SELECT id FROM fermes WHERE role = 'admin' LIMIT 1", fetch="one")
    if existing:
        return
    pwhash = bcrypt.generate_password_hash(cfg.bootstrap_admin_password).decode("utf-8")
    execute(
        "INSERT INTO fermes (name, userpass, farmname, role, integration_year) "
        "VALUES (%s, %s, %s, 'admin', %s) "
        "ON CONFLICT (name) DO UPDATE SET role = 'admin'",
        (cfg.bootstrap_admin_user, pwhash, "Administrateur", "2024"),
    )
