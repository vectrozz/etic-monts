"""WhatsApp relay: API used by the Android app + admin inbox."""
from __future__ import annotations

import re
import time

import pytest

from conftest import query, run_sql

pytestmark = pytest.mark.db

NOW_MS = int(time.time() * 1000)


def login_as(client, dbname, role="admin"):
    uid, name = query(dbname, "SELECT id, name FROM fermes WHERE role = %s ORDER BY id LIMIT 1", (role,))[0]
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = uid, name, role
    return uid


@pytest.fixture(scope="module")
def app(make_app, migrated_db):
    a = make_app("cout_revient,whatsapp")
    run_sql(migrated_db, "TRUNCATE chat_messages, chat_senders, relay_devices RESTART IDENTITY")
    return a


@pytest.fixture(scope="module")
def token(app, migrated_db):
    """Create a relay phone through the admin page, as the coordinator would."""
    c = app.test_client()
    login_as(c, migrated_db)
    # as behind the host nginx: ProxyFix must turn these into the public https URL
    page = c.post("/whatsapp/telephones", data={"name": "Tel coordinateur", "group": "Producteurs EMB"},
                  headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "emb.boblabs.eu"},
                  ).get_data(as_text=True)
    link = re.search(r'href="(embrelais://pair\?[^"]+)"', page)
    assert link, "pairing link missing"
    href = link.group(1).replace("&amp;", "&")
    assert "server=https%3A%2F%2Femb.boblabs.eu" in href and "groups=Producteurs+EMB" in href
    tok = re.search(r"token=(embr_[\w-]+)", href).group(1)
    stored = query(migrated_db, "SELECT token_hash FROM relay_devices")[0][0]
    assert tok not in stored, "only the hash may be stored"
    return tok


def auth(tok, version="1.0.0"):
    return {"Authorization": f"Bearer {tok}", "X-App-Version": version}


def msg(text, sender="Lucie Coteau", ms=None, chat="Producteurs EMB"):
    return {"chat": chat, "sender": sender, "text": text, "posted_at": ms or NOW_MS}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_ping_requires_a_valid_token(app, token):
    c = app.test_client()
    assert c.get("/api/relay/ping").status_code == 401
    assert c.get("/api/relay/ping", headers=auth("embr_wrong")).status_code == 401
    r = c.get("/api/relay/ping", headers=auth(token))
    assert r.status_code == 200 and r.get_json() == {"ok": True, "device": "Tel coordinateur"}


def test_ingest_and_dedup(app, token, migrated_db):
    c = app.test_client()
    batch = {"messages": [
        msg("betterave rouge, batavia rouge 2 colis, poireaux 5 colis", ms=NOW_MS - 60_000),
        msg("carottes 4 colis", sender="+33 6 12 34 56 78", ms=NOW_MS - 30_000),
    ]}
    r = c.post("/api/relay/messages", json=batch, headers=auth(token, "1.2.3"))
    assert r.status_code == 200 and r.get_json() == {"ok": True, "accepted": 2, "duplicates": 0}
    r = c.post("/api/relay/messages", json=batch, headers=auth(token, "1.2.3"))
    assert r.get_json() == {"ok": True, "accepted": 0, "duplicates": 2}
    assert query(migrated_db, "SELECT COUNT(*) FROM chat_messages")[0][0] == 2
    assert {r[0] for r in query(migrated_db, "SELECT sender_name FROM chat_senders")} == {
        "Lucie Coteau", "+33 6 12 34 56 78"}
    assert query(migrated_db, "SELECT last_app_version, last_seen_at IS NOT NULL FROM relay_devices")[0] == (
        "1.2.3", True)


@pytest.mark.parametrize("payload", [
    None, {"messages": []}, {"messages": "x"}, {"messages": [{"chat": "g", "sender": "s", "text": ""}]},
    {"messages": [{"chat": "g", "sender": "s", "text": "t", "posted_at": "hier"}]},
    {"messages": [msg("x")] * 201},
])
def test_ingest_rejects_bad_payloads(app, token, payload):
    c = app.test_client()
    kwargs = {"json": payload} if payload is not None else {"data": "not json", "content_type": "text/plain"}
    r = c.post("/api/relay/messages", headers=auth(token), **kwargs)
    assert r.status_code == 400 and "error" in r.get_json()


# ---------------------------------------------------------------------------
# Admin inbox
# ---------------------------------------------------------------------------

def test_inbox_maps_sender_to_farm(app, token, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    page = c.get("/whatsapp/").get_data(as_text=True)
    assert "À associer à une ferme" in page and "Lucie Coteau" in page

    sid = query(migrated_db, "SELECT id FROM chat_senders WHERE sender_name = 'Lucie Coteau'")[0][0]
    farm_id, farm_name = query(migrated_db, "SELECT id, farmname FROM fermes WHERE name = 'lucie'")[0]
    assert c.post(f"/whatsapp/expediteurs/{sid}", data={"ferme_id": str(farm_id)}).status_code == 302

    page = c.get("/whatsapp/").get_data(as_text=True)
    assert farm_name in page
    assert "Batavia rouge" in page and "2 colis" in page and "Poireaux" in page
    assert "à traiter" in page


def test_status_and_badge(app, token, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    before = c.get("/dashboard").get_data(as_text=True)
    assert re.search(r'class="nav-badge">2<', before)
    mid = query(migrated_db, "SELECT id FROM chat_messages WHERE sender_name = 'Lucie Coteau'")[0][0]
    c.post(f"/whatsapp/messages/{mid}/statut", data={"status": "done"})
    assert query(migrated_db, "SELECT status FROM chat_messages WHERE id = %s", (mid,))[0][0] == "done"
    assert re.search(r'class="nav-badge">1<', c.get("/dashboard").get_data(as_text=True))
    assert c.post(f"/whatsapp/messages/{mid}/statut", data={"status": "bogus"}).status_code == 400


def test_gaec_several_senders_one_farm(app, token, migrated_db):
    """Two associates of a GAEC post separately: one farm card, both lists, one click to clear."""
    c = app.test_client()
    login_as(c, migrated_db)
    farm_id, farm_name = query(migrated_db, "SELECT id, farmname FROM fermes WHERE name = 'lucie'")[0]
    r = c.post("/api/relay/messages", headers=auth(token), json={"messages": [
        msg("fraises 6 plateaux", sender="Paul Coteau", ms=NOW_MS - 20_000),
        msg("rhubarbe 3 bottes", sender="Lucie Coteau", ms=NOW_MS - 10_000),
    ]})
    assert r.get_json()["accepted"] == 2

    paul = query(migrated_db, "SELECT id FROM chat_senders WHERE sender_name = 'Paul Coteau'")[0][0]
    c.post(f"/whatsapp/expediteurs/{paul}", data={"ferme_id": str(farm_id)})
    members = {r[0] for r in query(migrated_db, "SELECT sender_name FROM chat_senders WHERE ferme_id = %s",
                                   (farm_id,))}
    assert members == {"Lucie Coteau", "Paul Coteau"}

    page = c.get("/whatsapp/").get_data(as_text=True)
    assert page.count(f"<h2>{farm_name}</h2>") == 1, "one card per farm, whoever wrote"
    assert "2 à traiter" in page
    for text in ("Fraises", "6 plateaux", "Rhubarbe", "3 bottes", "Paul Coteau", "Lucie Coteau"):
        assert text in page, text
    assert "Marquer les 2 traités" in page

    senders_page = c.get("/whatsapp/expediteurs").get_data(as_text=True)
    assert "Fermes et leurs membres" in senders_page and "2 membres" in senders_page

    c.post(f"/whatsapp/fermes/{farm_id}/traite")
    assert query(migrated_db, "SELECT COUNT(*) FROM chat_messages m JOIN chat_senders s USING (sender_name) "
                              "WHERE s.ferme_id = %s AND m.status = 'new'", (farm_id,))[0][0] == 0
    # the unmapped number's message is untouched
    assert query(migrated_db, "SELECT status FROM chat_messages WHERE sender_name = '+33 6 12 34 56 78'")[0][0] == "new"


def test_other_pages_render(app, token, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    for path in ("/whatsapp/messages", "/whatsapp/expediteurs", "/whatsapp/telephones", "/whatsapp/?jours=30"):
        assert c.get(path).status_code == 200, path


def test_producers_cannot_access(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db, "producteur")
    assert c.get("/whatsapp/").status_code == 403
    assert c.post("/whatsapp/telephones", data={"name": "x"}).status_code == 403


def test_revoked_token_is_refused(app, token, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    did = query(migrated_db, "SELECT id FROM relay_devices ORDER BY id LIMIT 1")[0][0]
    c.post(f"/whatsapp/telephones/{did}/revoquer")
    assert c.get("/api/relay/ping", headers=auth(token)).status_code == 401
    assert c.post("/api/relay/messages", json={"messages": [msg("x")]}, headers=auth(token)).status_code == 401


def test_module_off_in_prod_profile(make_app):
    c = make_app("cout_revient").test_client()
    assert c.get("/api/relay/ping").status_code == 404
    assert c.get("/whatsapp/").status_code == 404
