"""End-to-end smoke tests against a real PostgreSQL database.

Skipped unless TEST_POSTGRES_PORT is set. Typical run (throwaway container,
optionally restored from a production dump):

    docker run -d --name emb-test -e POSTGRES_USER=eticmont \
        -e POSTGRES_PASSWORD=eticmont -e POSTGRES_DB=eticmont \
        -p 127.0.0.1:55432:5432 postgres:17
    TEST_POSTGRES_PORT=55432 python -m pytest tests -q

Never point this at production: it writes and deletes a test campaign.
"""
from __future__ import annotations

import os
import re

import pytest

PORT = os.environ.get("TEST_POSTGRES_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="TEST_POSTGRES_PORT not set")


def _make_app(features: str):
    os.environ.update({
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": PORT or "",
        "POSTGRES_PASSWORD": os.environ.get("TEST_POSTGRES_PASSWORD", "eticmont"),
        "FEATURES": features,
        "FLASK_ENV": "development",
        "SECRET_KEY": "test",
    })
    import eticmonts.db as db
    db._pool = None  # fresh pool per app
    from eticmonts import create_app
    app = create_app()
    app.testing = True
    return app


def _login(client, role="admin"):
    from eticmonts.db import execute
    row = execute(
        "SELECT id, name FROM fermes WHERE role = %s ORDER BY id LIMIT 1", (role,), fetch="one",
    )
    if row is None:
        execute(
            "INSERT INTO fermes (name, userpass, farmname, role) VALUES (%s, 'x', %s, %s)",
            (f"smoke_{role}"[:20], f"Smoke {role}", role),
        )
        row = execute("SELECT id, name FROM fermes WHERE name = %s", (f"smoke_{role}"[:20],), fetch="one")
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = row[0], row[1], role
    return row[0]


@pytest.fixture(scope="module")
def prod_app():
    return _make_app("cout_revient")


def test_core_pages_render(prod_app):
    c = prod_app.test_client()
    for path in ("/", "/login", "/register"):
        assert c.get(path).status_code in (200, 302), path
    uid = _login(c)
    for path in ("/dashboard", f"/fiche/{uid}", f"/biodiv-detail/{uid}", "/admin/",
                 "/admin/coefbiodiv", "/admin/users", "/settings/", "/settings/exploitation",
                 "/catalog/", "/cout-de-revient/fraise", "/cout-de-revient/fraise?annee=nouvelle",
                 "/cout-de-revient/fraise/reseau", "/cout-de-revient/fraise/reseau.csv"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)


def test_marketplace_disabled_in_prod_profile(prod_app):
    c = prod_app.test_client()
    _login(c)
    assert c.get("/products/").status_code == 404
    assert c.get("/orders/").status_code == 404
    assert c.post("/settings/delivery-cycle").status_code == 404
    body = c.get("/dashboard").get_data(as_text=True)
    assert "Marketplace" not in body


def test_campaign_roundtrip(prod_app):
    c = prod_app.test_client()
    uid = _login(c, "producteur")
    form = {
        "year": "2099", "nb_units": "4000", "surface_m2": "1000", "yield_kg": "2000",
        "sale_price": "8,50", "hourly_cost": "15", "task_recolte": "300", "task_plantation": "100",
        "charge_plants": "1200", "charge_amort_abris": "800", "variety": "Gariguette",
        "system": "abri",
    }
    r = c.post("/cout-de-revient/fraise", data=form)
    assert r.status_code == 302 and "annee=2099" in r.headers["Location"]
    page = c.get("/cout-de-revient/fraise?annee=2099").get_data(as_text=True)
    # (400 h × 15 €) + 1200 + 800 = 8 000 € / 2 000 kg = 4,00 €/kg
    assert re.search(r'data-out="cost_per_kg">4,00<', page), "cost per kg not rendered"
    assert "Gariguette" in page

    from eticmonts.db import execute
    cid = execute("SELECT id FROM production_cost WHERE linked_id = %s AND year = 2099",
                  (uid,), fetch="one")[0]
    assert c.post(f"/cout-de-revient/fraise/{cid}/supprimer").status_code == 302
    assert execute("SELECT 1 FROM production_cost WHERE id = %s", (cid,), fetch="one") is None


def test_other_farm_fiche_forbidden(prod_app):
    c = prod_app.test_client()
    uid = _login(c, "producteur")
    from eticmonts.db import execute
    other = execute("SELECT id FROM fermes WHERE id <> %s LIMIT 1", (uid,), fetch="one")
    if other:
        assert c.get(f"/fiche/{other[0]}").status_code == 403


def test_full_profile_boots_and_renders():
    app = _make_app("all")
    c = app.test_client()
    _login(c)
    for path in ("/dashboard", "/admin/", "/settings/", "/products/", "/stocks/",
                 "/clients/", "/orders/", "/tournees/", "/cout-de-revient/fraise"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)
