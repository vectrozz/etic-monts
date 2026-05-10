"""Auth + role-based access decorators."""
from __future__ import annotations

from functools import wraps

from flask import flash, redirect, session, url_for, abort


ROLE_ADMIN = "admin"
ROLE_PRODUCTEUR = "producteur"
ROLE_CLIENT = "client"
ALL_ROLES = (ROLE_ADMIN, ROLE_PRODUCTEUR, ROLE_CLIENT)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles: str):
    """Allow access only to users with at least one of the listed roles."""
    valid = set(roles)

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "username" not in session:
                flash("Veuillez vous connecter.", "warning")
                return redirect(url_for("main.login"))
            user_role = session.get("role", ROLE_PRODUCTEUR)
            if user_role not in valid:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


admin_required = role_required(ROLE_ADMIN)
producteur_required = role_required(ROLE_PRODUCTEUR, ROLE_ADMIN)


def get_session_context() -> dict:
    return {
        "username": session.get("username"),
        "user_id": session.get("user_id"),
        "role": session.get("role", ROLE_PRODUCTEUR),
        "created_date": session.get("created_date"),
        "last_login_date": session.get("last_login_date"),
    }


def is_admin() -> bool:
    return session.get("role") == ROLE_ADMIN
