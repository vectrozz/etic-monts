"""End-to-end smoke tests: the Flask app against a migrated copy of the v2 schema."""
from __future__ import annotations

import re

import pytest

from conftest import create_database, drop_database, query, upgrade

pytestmark = pytest.mark.db


def login_as(client, dbname, role="admin"):
    row = query(dbname, "SELECT id, name FROM fermes WHERE role = %s ORDER BY id LIMIT 1", (role,))
    assert row, f"no {role} in fixture data"
    uid, name = row[0]
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = uid, name, role
    return uid


@pytest.fixture(scope="module")
def prod_app(make_app):
    return make_app("cout_revient")


def test_bootstrap_admin_promotes_existing_user(prod_app, migrated_db):
    assert query(migrated_db, "SELECT role FROM fermes WHERE name = 'a'") == [("admin",)]


def test_healthz(prod_app):
    r = prod_app.test_client().get("/healthz")
    assert r.status_code == 200
    body = r.get_json()
    from eticmonts.schema_version import expected_head
    assert body["status"] == "ok" and body["schema"] == expected_head() and body["features"] == ["cout_revient"]


def test_login_with_password(prod_app):
    c = prod_app.test_client()
    r = c.post("/login", data={"name": "lucie", "userpass": "motdepasse-test"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    assert c.get("/dashboard").status_code == 200
    r = c.post("/login", data={"name": "lucie", "userpass": "wrong"}, follow_redirects=True)
    assert "Mot de passe incorrect" in r.get_data(as_text=True)


def test_core_pages_render(prod_app, migrated_db):
    c = prod_app.test_client()
    for path in ("/", "/login", "/register"):
        assert c.get(path).status_code in (200, 302), path
    uid = login_as(c, migrated_db, "admin")
    for path in ("/dashboard", f"/fiche/{uid}", f"/biodiv-detail/{uid}", "/admin/",
                 "/admin/coefbiodiv", "/admin/users", "/settings/", "/settings/exploitation",
                 "/catalog/", "/cout-de-revient/fraise", "/cout-de-revient/fraise?annee=nouvelle",
                 "/cout-de-revient/fraise/reseau", "/cout-de-revient/fraise/reseau.csv"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)


def test_static_assets_cached_and_versioned(prod_app, migrated_db):
    c = prod_app.test_client()
    login_as(c, migrated_db)
    page = c.get("/dashboard").get_data(as_text=True)
    m = re.search(r"/static/style\.css\?v=([0-9a-f]{10})", page)
    assert m, "style.css should carry a content fingerprint"
    r = c.get("/static/style.css")
    assert r.status_code == 200 and "max-age=2592000" in r.headers.get("Cache-Control", "")


def test_marketplace_disabled_in_prod_profile(prod_app, migrated_db):
    c = prod_app.test_client()
    login_as(c, migrated_db)
    assert c.get("/products/").status_code == 404
    assert c.get("/orders/").status_code == 404
    assert c.post("/settings/delivery-cycle").status_code == 404
    assert "Marketplace" not in c.get("/dashboard").get_data(as_text=True)


def test_campaign_roundtrip(prod_app, migrated_db):
    c = prod_app.test_client()
    uid = login_as(c, migrated_db, "producteur")
    form = {
        "year": "2099", "nb_units": "4000", "surface_m2": "1000", "yield_kg": "2000",
        "sale_price": "8,50", "hourly_cost": "15", "task_recolte": "300", "task_plantation": "100",
        "charge_plants": "1200", "charge_amort_abris": "800", "variety": "Gariguette", "system": "abri",
    }
    r = c.post("/cout-de-revient/fraise", data=form)
    assert r.status_code == 302 and "annee=2099" in r.headers["Location"]
    page = c.get("/cout-de-revient/fraise?annee=2099").get_data(as_text=True)
    # (400 h × 15 €) + 1200 + 800 = 8 000 € / 2 000 kg = 4,00 €/kg
    assert re.search(r'data-out="cost_per_kg">4,00<', page)
    assert "Gariguette" in page
    cid = query(migrated_db, "SELECT id FROM production_cost WHERE linked_id = %s AND year = 2099", (uid,))[0][0]
    assert c.post(f"/cout-de-revient/fraise/{cid}/supprimer").status_code == 302
    assert not query(migrated_db, "SELECT 1 FROM production_cost WHERE id = %s", (cid,))


def test_producer_cannot_open_other_farm_or_admin(prod_app, migrated_db):
    c = prod_app.test_client()
    uid = login_as(c, migrated_db, "producteur")
    other = query(migrated_db, "SELECT id FROM fermes WHERE id <> %s LIMIT 1", (uid,))[0][0]
    assert c.get(f"/fiche/{other}").status_code == 403
    assert c.get("/admin/").status_code == 403
    assert c.post("/addcoefbiodiv", data={"year": "2030"}).status_code == 403


def test_full_profile_renders_marketplace(make_app, migrated_db):
    app = make_app("all")
    c = app.test_client()
    login_as(c, migrated_db)
    for path in ("/dashboard", "/admin/", "/settings/", "/products/", "/stocks/",
                 "/clients/", "/orders/", "/tournees/", "/cout-de-revient/fraise"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)


def test_app_refuses_to_start_on_outdated_schema(make_app):
    from eticmonts.schema_version import SchemaOutOfDate
    db = create_database()
    try:
        upgrade(db, "0003")
        with pytest.raises(SchemaOutOfDate):
            make_app("cout_revient", db=db)
    finally:
        from eticmonts.db import close_pool
        close_pool()
        drop_database(db)
