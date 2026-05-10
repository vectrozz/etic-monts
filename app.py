"""WSGI entry point.

The application logic now lives in the `eticmonts/` package. This file is
kept thin so existing Dockerfiles / gunicorn configs that reference `app:app`
continue to work.
"""
from __future__ import annotations

import os

from eticmonts import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010,
            debug=os.environ.get("FLASK_ENV") != "production")
