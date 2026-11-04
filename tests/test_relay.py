"""WhatsApp relay: secured API used by the Android app + admin inbox.

`Phone` reproduces exactly what the app does: an EC P-256 key pair, one-time
pairing, then ECDSA-signed requests (see eticmonts/relay_auth.py).
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest import query, run_sql
from eticmonts.relay_auth import canonical

pytestmark = pytest.mark.db

NOW_MS = int(time.time() * 1000)


def login_as(client, dbname, role="admin"):
    uid, name = query(dbname, "SELECT id, name FROM fermes WHERE role = %s ORDER BY id LIMIT 1", (role,))[0]
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = uid, name, role
    return uid


def create_device_code(client, name="Tel coordinateur", group="Producteurs EMB") -> str:
    """Create a relay phone through the admin page; return the one-time pairing code."""
    page = client.post("/whatsapp/telephones", data={"name": name, "group": group},
                       headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "emb.boblabs.eu"},
                       ).get_data(as_text=True)
    link = re.search(r'href="(embrelais://pair\?[^"]+)"', page)
    assert link, "pairing link missing"
    href = link.group(1).replace("&amp;", "&")
    assert "server=https%3A%2F%2Femb.boblabs.eu" in href
    return re.search(r"code=(embr_[\w-]+)", href).group(1)


class Phone:
    """What the Android app does: a key pair + signed requests."""

    def __init__(self, client, code, hardware="tee"):
        self.client = client
        self.key = ec.generate_private_key(ec.SECP256R1())
        pub = self.key.public_key().public_bytes(serialization.Encoding.DER,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo)
        self.register_response = client.post(
            "/api/relay/register", json={"public_key": base64.b64encode(pub).decode(), "key_hardware": hardware},
            headers={"Authorization": f"Bearer {code}", "X-App-Version": "1.1.0"})
        body = self.register_response.get_json() or {}
        self.device_id = body.get("device_id")

    def signed_headers(self, method, path, body=b"", ts=None, nonce=None, key=None):
        ts = str(ts if ts is not None else int(time.time() * 1000))
        nonce = nonce or secrets.token_hex(16)
        sig = (key or self.key).sign(canonical(method, path, ts, nonce, body), ec.ECDSA(hashes.SHA256()))
        return {"X-Relay-Device": str(self.device_id), "X-Relay-Timestamp": ts, "X-Relay-Nonce": nonce,
                "X-Relay-Signature": base64.b64encode(sig).decode(), "X-App-Version": "1.1.0"}

    def ping(self, **kw):
        return self.client.get("/api/relay/ping", headers=self.signed_headers("GET", "/api/relay/ping", **kw))

    def send(self, messages, body=None, **kw):
        raw = json.dumps({"messages": messages}).encode() if body is None else body
        return self.client.post("/api/relay/messages", data=raw, content_type="application/json",
                                headers=self.signed_headers("POST", "/api/relay/messages", raw, **kw))


def msg(text, sender="Lucie Coteau", ms=None, chat="Producteurs EMB"):
    return {"chat": chat, "sender": sender, "text": text, "posted_at": ms or NOW_MS}


@pytest.fixture(scope="module")
def app(make_app, migrated_db):
    os.environ.update({"RELAY_RATE_PER_MIN": "1000", "RELAY_DAILY_CAP": "100000"})
    a = make_app("cout_revient,whatsapp")
    run_sql(migrated_db, "TRUNCATE chat_messages, chat_senders, relay_nonces, relay_devices RESTART IDENTITY CASCADE")
    return a


@pytest.fixture(scope="module")
def phone(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    p = Phone(app.test_client(), create_device_code(c))
    assert p.register_response.status_code == 200, p.register_response.get_json()
    return p


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def test_pairing_code_is_single_use_and_hashed(app, phone, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    code = create_device_code(c, name="Deuxième")
    assert code not in str(query(migrated_db, "SELECT token_hash FROM relay_devices"))
    first = Phone(app.test_client(), code)
    assert first.register_response.status_code == 200
    again = Phone(app.test_client(), code)
    assert again.register_response.status_code == 401
    assert again.register_response.get_json()["code"] == "bad_code"


def test_pairing_code_expires(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    code = create_device_code(c, name="Expiré")
    run_sql(migrated_db, "UPDATE relay_devices SET pairing_expires_at = now() - interval '1 minute' "
                         "WHERE name = 'Expiré'")
    assert Phone(app.test_client(), code).register_response.status_code == 401


def test_register_rejects_non_p256_keys(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    code = create_device_code(c, name="Mauvaise clé")
    other = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    r = app.test_client().post("/api/relay/register", headers={"Authorization": f"Bearer {code}"},
                               json={"public_key": base64.b64encode(other).decode()})
    assert r.status_code == 400 and r.get_json()["code"] == "bad_key"


# ---------------------------------------------------------------------------
# Signed requests: only the paired phone gets in
# ---------------------------------------------------------------------------

def test_signed_ping(phone):
    r = phone.ping()
    assert r.status_code == 200 and r.get_json() == {"ok": True, "device": "Tel coordinateur"}


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer embr_anything"},                    # the old bearer scheme is gone
    {"X-Relay-Device": "1", "X-Relay-Timestamp": "1", "X-Relay-Nonce": "x", "X-Relay-Signature": "y"},
])
def test_unsigned_requests_are_refused(app, phone, headers):
    c = app.test_client()
    assert c.get("/api/relay/ping", headers=headers).get_json()["code"] == "unsigned"
    r = c.post("/api/relay/messages", json={"messages": [msg("x")]}, headers=headers)
    assert r.status_code == 401


def test_signature_from_another_key_is_refused(phone):
    intruder = ec.generate_private_key(ec.SECP256R1())
    r = phone.ping(key=intruder)
    assert r.status_code == 401 and r.get_json()["code"] == "bad_signature"


def test_tampered_body_is_refused(phone):
    signed = json.dumps({"messages": [msg("poireaux 5 colis")]}).encode()
    headers = phone.signed_headers("POST", "/api/relay/messages", signed)
    forged = json.dumps({"messages": [msg("poireaux 500 colis")]}).encode()
    r = phone.client.post("/api/relay/messages", data=forged, content_type="application/json", headers=headers)
    assert r.status_code == 401 and r.get_json()["code"] == "bad_signature"


def test_replay_is_refused(phone):
    nonce = secrets.token_hex(16)
    ts = int(time.time() * 1000)
    assert phone.ping(nonce=nonce, ts=ts).status_code == 200
    r = phone.ping(nonce=nonce, ts=ts)
    assert r.status_code == 401 and r.get_json()["code"] == "replay"


def test_stale_timestamp_is_refused_with_server_time(phone):
    r = phone.ping(ts=int(time.time() * 1000) - 10 * 60 * 1000)
    body = r.get_json()
    assert r.status_code == 401 and body["code"] == "clock" and abs(body["server_time"] - time.time() * 1000) < 60_000


def test_oversized_and_unbounded_bodies_are_refused_before_auth(app):
    c = app.test_client()
    r = c.post("/api/relay/messages", data=b"x" * (512 * 1024 + 1), content_type="application/json")
    assert r.status_code == 413
    r = c.post("/api/relay/messages", input_stream=__import__("io").BytesIO(b"{}"), content_type="application/json",
               headers={"Transfer-Encoding": "chunked"})
    assert r.status_code in (411, 401)


def test_ingest_and_dedup(phone, migrated_db):
    batch = [msg("betterave rouge, batavia rouge 2 colis, poireaux 5 colis", ms=NOW_MS - 60_000),
             msg("carottes 4 colis", sender="+33 6 12 34 56 78", ms=NOW_MS - 30_000)]
    r = phone.send(batch)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "accepted": 2, "duplicates": 0}
    assert phone.send(batch).get_json() == {"ok": True, "accepted": 0, "duplicates": 2}
    assert query(migrated_db, "SELECT COUNT(*) FROM chat_messages")[0][0] == 2
    assert {r[0] for r in query(migrated_db, "SELECT sender_name FROM chat_senders")} == {
        "Lucie Coteau", "+33 6 12 34 56 78"}
    row = query(migrated_db, "SELECT last_app_version, key_hardware FROM relay_devices WHERE id = %s",
                (phone.device_id,))[0]
    assert row == ("1.1.0", "tee")


@pytest.mark.parametrize("payload", [
    {"messages": []}, {"messages": "x"}, {"messages": [{"chat": "g", "sender": "s", "text": ""}]},
    {"messages": [{"chat": "g", "sender": "s", "text": "t", "posted_at": "hier"}]},
    {"messages": [msg("x")] * 201},
])
def test_ingest_rejects_bad_payloads(phone, payload):
    r = phone.send(None, body=json.dumps(payload).encode())
    assert r.status_code == 400 and "error" in r.get_json()


def test_rate_limit_per_phone(app, migrated_db, monkeypatch):
    c = app.test_client()
    login_as(c, migrated_db)
    p = Phone(app.test_client(), create_device_code(c, name="Bavard"))
    monkeypatch.setenv("RELAY_RATE_PER_MIN", "5")
    codes = [p.ping().status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    r = p.ping()
    assert r.headers.get("Retry-After") == "60" and r.get_json()["code"] == "rate_limited"


def test_daily_message_cap(app, migrated_db, monkeypatch):
    c = app.test_client()
    login_as(c, migrated_db)
    p = Phone(app.test_client(), create_device_code(c, name="Quota"))
    monkeypatch.setenv("RELAY_DAILY_CAP", "3")
    assert p.send([msg(f"m{i}", sender="Quota") for i in range(3)]).status_code == 200
    r = p.send([msg("un de trop", sender="Quota")])
    assert r.status_code == 429 and r.get_json()["code"] == "daily_cap"
    run_sql(migrated_db, "DELETE FROM chat_messages WHERE sender_name = 'Quota'")
    run_sql(migrated_db, "DELETE FROM chat_senders WHERE sender_name = 'Quota'")


# ---------------------------------------------------------------------------
# Admin inbox
# ---------------------------------------------------------------------------

def test_inbox_maps_sender_to_farm(app, phone, migrated_db):
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


def test_status_and_badge(app, phone, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    before = c.get("/dashboard").get_data(as_text=True)
    assert re.search(r'class="nav-badge">2<', before)
    mid = query(migrated_db, "SELECT id FROM chat_messages WHERE sender_name = 'Lucie Coteau'")[0][0]
    c.post(f"/whatsapp/messages/{mid}/statut", data={"status": "done"})
    assert query(migrated_db, "SELECT status FROM chat_messages WHERE id = %s", (mid,))[0][0] == "done"
    assert re.search(r'class="nav-badge">1<', c.get("/dashboard").get_data(as_text=True))
    assert c.post(f"/whatsapp/messages/{mid}/statut", data={"status": "bogus"}).status_code == 400


def test_gaec_several_senders_one_farm(app, phone, migrated_db):
    """Two associates of a GAEC post separately: one farm card, both lists, one click to clear."""
    c = app.test_client()
    login_as(c, migrated_db)
    farm_id, farm_name = query(migrated_db, "SELECT id, farmname FROM fermes WHERE name = 'lucie'")[0]
    r = phone.send([msg("fraises 6 plateaux", sender="Paul Coteau", ms=NOW_MS - 20_000),
                    msg("rhubarbe 3 bottes", sender="Lucie Coteau", ms=NOW_MS - 10_000)])
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
    assert query(migrated_db, "SELECT status FROM chat_messages WHERE sender_name = '+33 6 12 34 56 78'")[0][0] == "new"


def test_messages_from_several_groups_show_their_group(app, phone, migrated_db):
    """A WhatsApp community: one farm posts in two of its groups."""
    c = app.test_client()
    login_as(c, migrated_db)
    r = phone.send([msg("navets 2 colis", chat="Légumes · EMB", ms=NOW_MS - 5_000),
                    msg("pommes 4 cagettes", chat="Fruits · EMB", ms=NOW_MS - 4_000)])
    assert r.get_json()["accepted"] == 2
    page = c.get("/whatsapp/").get_data(as_text=True)
    assert "Légumes · EMB" in page and "Fruits · EMB" in page
    assert "Navets" in page and "4 cagettes" in page
    table = c.get("/whatsapp/messages").get_data(as_text=True)
    assert "<th>Groupe</th>" in table and "Fruits · EMB" in table


def test_other_pages_render(app, phone, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    for path in ("/whatsapp/messages", "/whatsapp/expediteurs", "/whatsapp/telephones", "/whatsapp/?jours=30"):
        assert c.get(path).status_code == 200, path
    assert "puce sécurisée (TEE)" in c.get("/whatsapp/telephones").get_data(as_text=True)


def test_producers_cannot_access(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db, "producteur")
    assert c.get("/whatsapp/").status_code == 403
    assert c.post("/whatsapp/telephones", data={"name": "x"}).status_code == 403
    assert c.post("/whatsapp/telephones/1/lien").status_code == 403


# ---------------------------------------------------------------------------
# Lifecycle: new pairing link, revocation
# ---------------------------------------------------------------------------

def test_new_pairing_link_retires_the_old_key(app, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    old = Phone(app.test_client(), create_device_code(c, name="Réinstallé"))
    assert old.ping().status_code == 200
    page = c.post(f"/whatsapp/telephones/{old.device_id}/lien").get_data(as_text=True)
    code = re.search(r"code=(embr_[\w-]+)", page).group(1)
    assert old.ping().get_json()["code"] == "unknown_device"
    new = Phone(app.test_client(), code)
    assert new.device_id == old.device_id and new.ping().status_code == 200


def test_revoked_phone_is_refused(app, phone, migrated_db):
    c = app.test_client()
    login_as(c, migrated_db)
    c.post(f"/whatsapp/telephones/{phone.device_id}/revoquer")
    assert phone.ping().status_code == 401
    assert phone.send([msg("x")]).status_code == 401


def test_module_off_in_prod_profile(make_app):
    c = make_app("cout_revient").test_client()
    assert c.get("/api/relay/ping").status_code == 404
    assert c.get("/whatsapp/").status_code == 404
