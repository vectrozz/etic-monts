"""Module feature flags (see ``config.KNOWN_FEATURES``).

Usage in Python::

    from .features import feature_enabled, require_feature

    @bp.route(...)
    @require_feature("marketplace")
    def view(): ...

Usage in templates::

    {% if feature('marketplace') %} … {% endif %}
"""
from __future__ import annotations

from functools import wraps

from flask import abort, current_app


def feature_enabled(name: str) -> bool:
    cfg = current_app.config.get("APP_CONFIG")
    return bool(cfg and cfg.has(name))


def require_feature(name: str):
    """404 the route when the module is disabled for this deployment."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not feature_enabled(name):
                abort(404)
            return f(*args, **kwargs)
        return decorated
    return decorator
