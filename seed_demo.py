#!/usr/bin/env python3
"""Seed demo data — 3 users with 5 years of dashboard data + catalog values.

Idempotent: re-running it will not duplicate data. Existing rows for the same
(user, year) are skipped.

Usage:
    docker exec eticmonts-app-flask-1 python3 seed_demo.py
"""
from __future__ import annotations

import json
import os

import bcrypt
import psycopg2

# ---------------------------------------------------------------------------
PASSWORD = "test1234"
YEARS = [2020, 2021, 2022, 2023, 2024]

USERS = [
    # (login, farmname, address, lat, lng)
    ("lucasfarm",   "Lucas Farm",     "Saint-Étienne (42)",     45.4397, 4.3872),
    ("troisfruits", "3 Fruits",       "Yssingeaux (43)",        45.1417, 4.1239),
    ("tinoufarmer", "Tinou Farmer",   "Le Puy-en-Velay (43)",   45.0432, 3.8855),
]

CATALOG: dict[str, list[str]] = {
    "paillage": [
        "BRF (bois raméal fragmenté)",
        "Paille de céréales",
        "Toile tissée biodégradable",
    ],
    "limitation_plastique": [
        "Réutilisation des bâches plusieurs saisons",
        "Achat d'outils en métal durable",
        "Compostage des déchets verts sur ferme",
    ],
    "emballage": [
        "Carton recyclé sans encre",
        "Sacs kraft réutilisables",
        "Aucun emballage (vrac)",
    ],
    "analyse_sol": [
        "Analyse complète tous les 3 ans",
        "Suivi annuel taux MO",
        "pH et structure semestriels",
    ],
    "formation_sol": [
        "Stage Sols vivants — Bertrand Foulon",
        "Formation Civam BIO 2023",
        "MOOC Sols vivants INRAE",
    ],
    "pratique_sol": [
        "Couverts permanents",
        "Travail superficiel uniquement",
        "Apport régulier de compost",
    ],
    "irrigation": [
        "Goutte-à-goutte régulé",
        "Aspersion contrôlée par sondes",
        "Système gravitaire ancien",
    ],
    "action_eau": [
        "Récupération eau de pluie 30 m³",
        "Sondes tensiométriques",
        "Mulching organique épais",
    ],
    "lutte_achat": [
        "Acariens prédateurs Typhlodromus",
        "Bandes fleuries semées",
        "Pièges à phéromones carpocapse",
    ],
    "lutte_favorisation": [
        "Maintien et plantation de haies",
        "Nichoirs à mésanges & rapaces",
        "Hôtels à insectes",
    ],
    "lutte_formation": [
        "Formation Adabio 2023",
        "Webinaire INRA biocontrôle",
        "Stage Solagro auxiliaires",
    ],
}

# Coefficients MAEC (constants over the 5 years)
COEF_BIODIV = {
    "coefhaie": 0.05, "coefarbrealign": 0.02, "coefarbreseul": 0.5,
    "coefbosquet": 0.001, "coefmare": 0.01, "coeffosse": 0.01,
    "coefbordure": 0.005, "coefjachere": 0.001, "coefjacheremel": 0.005,
    "coefmuret": 0.005, "coefprairie": 0.001,
}

# ---------------------------------------------------------------------------
def conn():
    return psycopg2.connect(
        database=os.environ.get("POSTGRES_DB", "eticmont"),
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        user=os.environ.get("POSTGRES_USER", "eticmont"),
        password=os.environ.get("POSTGRES_PASSWORD", "eticmont"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
    )


def gen_surface(idx: int, factor: float) -> dict:
    return {
        "surffr":    round((1.0 + 0.10 * idx) * factor, 4),
        "surfgf":    round((0.5 + 0.07 * idx) * factor, 4),
        "surfleg":   round((0.8 + 0.10 * idx) * factor, 4),
        "prairie":   round( 3.0                * factor, 4),
        "culture":   round((1.5 + 0.05 * idx) * factor, 4),
        "surfautre": round( 0.5                * factor, 4),
    }


def gen_biodiv(idx: int, factor: float) -> dict:
    """Steady progression in biodiversity efforts."""
    return {
        "haie":         round((180  + 20 * idx) * factor, 2),
        "arbrealign":   round(( 40  +  5 * idx) * factor, 2),
        "arbreseul":    round(( 12  +  2 * idx) * factor, 0),
        "bosquet":      round((250  + 30 * idx) * factor, 2),
        "mare":         round(( 50  +  5 * idx) * factor, 2),
        "fosse":        round((100  +  5 * idx) * factor, 2),
        "bordure":      round(( 80  +  8 * idx) * factor, 2),
        "jachere":      round((180  + 30 * idx) * factor, 2),
        "jacheremel":   round(( 40  + 10 * idx) * factor, 2),
        "muret":        round(( 90  +  5 * idx) * factor, 2),
    }


def gen_plastique(idx: int, factor: float) -> dict:
    """Progressive reduction of plastics over years."""
    return {
        "surftotplast":  round((1000 - 100 * idx) * factor, 2),
        "surftottoile":  round(( 500 -  50 * idx) * factor, 2),
        "embplastpourcent": max(20.0, 80.0 - 12.0 * idx),
        "paillagefr":  CATALOG["paillage"][idx % 3],
        "paillagegf":  CATALOG["paillage"][(idx + 1) % 3],
        "paillageleg": CATALOG["paillage"][(idx + 2) % 3],
        "limitation":  CATALOG["limitation_plastique"][idx % 3],
        "embplast":    CATALOG["emballage"][idx % 3],
        "embfr":       CATALOG["emballage"][idx % 3],
        "embgf":       CATALOG["emballage"][(idx + 1) % 3],
        "embleg":      CATALOG["emballage"][(idx + 2) % 3],
    }


def gen_soil(idx: int) -> dict:
    return {
        "analyse":     CATALOG["analyse_sol"][idx % 3],
        "connaissance": min(10, 5 + idx),
        "formation":   CATALOG["formation_sol"][idx % 3],
        "pratique":    CATALOG["pratique_sol"][idx % 3],
    }


def gen_water(idx: int, factor: float) -> dict:
    return {
        "matosirrigfr":  CATALOG["irrigation"][idx % 3],
        "matosirriggf":  CATALOG["irrigation"][(idx + 1) % 3],
        "matosirrigleg": CATALOG["irrigation"][(idx + 2) % 3],
        "consoeau":      max(2000, int((5000 - 250 * idx) * factor)),
        "actions":       CATALOG["action_eau"][idx % 3],
    }


def gen_lutte(idx: int) -> dict:
    return {
        "achat":        CATALOG["lutte_achat"][idx % 3],
        "favorisation": CATALOG["lutte_favorisation"][idx % 3],
        "formation":    CATALOG["lutte_formation"][idx % 3],
    }


def biodiv_score(prairie: float, b: dict) -> float:
    c = COEF_BIODIV
    return round(
        10000 * c["coefprairie"] * prairie
        + c["coefhaie"] * b["haie"]
        + c["coefarbrealign"] * b["arbrealign"]
        + c["coefarbreseul"] * b["arbreseul"]
        + c["coefbosquet"] * b["bosquet"]
        + c["coefmare"] * b["mare"]
        + c["coeffosse"] * b["fosse"]
        + c["coefbordure"] * b["bordure"]
        + c["coefjachere"] * b["jachere"]
        + c["coefjacheremel"] * b["jacheremel"]
        + c["coefmuret"] * b["muret"],
        4,
    )


# ---------------------------------------------------------------------------
def main() -> None:
    c = conn()
    cur = c.cursor()

    # --- products (catalogue typique d'une coop bio française) -------------
    print("→ Produits de démonstration")
    PRODUCTS = [
        # Fruits rouges
        ("Fraises bio",      "fruits rouges", "kg",    0.005, 8.0,  "🍓"),
        ("Framboises bio",   "fruits rouges", "kg",    0.004, 12.0, "🍇"),
        ("Mûres bio",        "fruits rouges", "kg",    0.005, 10.0, "🫐"),
        ("Myrtilles bio",    "fruits rouges", "kg",    0.001, 14.0, "🫐"),
        ("Cassis bio",       "fruits rouges", "kg",    0.001, 9.0,  "🫐"),
        ("Groseilles bio",   "fruits rouges", "kg",    0.001, 9.0,  "🍒"),
        # Gros fruits
        ("Pommes bio",       "fruits",        "kg",    0.18, 3.0,  "🍎"),
        ("Poires bio",       "fruits",        "kg",    0.18, 3.5,  "🍐"),
        ("Pêches bio",       "fruits",        "kg",    0.16, 4.5,  "🍑"),
        ("Abricots bio",     "fruits",        "kg",    0.05, 5.0,  "🍑"),
        ("Cerises bio",      "fruits",        "kg",    0.008, 8.0, "🍒"),
        ("Prunes bio",       "fruits",        "kg",    0.04, 4.5,  "🍑"),
        ("Raisin bio",       "fruits",        "kg",    0.5,  4.0,  "🍇"),
        # Légumes feuilles
        ("Salade verte bio", "légume-feuille","pièce", 0.3,  1.5,  "🥬"),
        ("Épinards bio",     "légume-feuille","kg",    0.3,  6.0,  "🥬"),
        ("Blettes bio",      "légume-feuille","kg",    0.5,  4.0,  "🥬"),
        ("Roquette bio",     "légume-feuille","kg",    0.05, 14.0, "🥬"),
        ("Mâche bio",        "légume-feuille","kg",    0.05, 18.0, "🥬"),
        # Choux
        ("Chou kale bio",    "chou",          "pièce", 0.6,  3.0,  "🥬"),
        ("Brocoli bio",      "chou",          "pièce", 0.5,  3.5,  "🥦"),
        ("Chou-fleur bio",   "chou",          "pièce", 1.0,  3.5,  "🥦"),
        ("Chou rouge bio",   "chou",          "pièce", 1.2,  3.0,  "🥬"),
        # Légumes-fruits
        ("Tomates bio",      "légume-fruit",  "kg",    0.18, 4.5,  "🍅"),
        ("Tomates cerises bio","légume-fruit","kg",    0.015, 8.0, "🍅"),
        ("Aubergines bio",   "légume-fruit",  "kg",    0.3,  4.5,  "🍆"),
        ("Courgettes bio",   "légume-fruit",  "kg",    0.3,  3.0,  "🥒"),
        ("Concombres bio",   "légume-fruit",  "pièce", 0.3,  1.5,  "🥒"),
        ("Poivrons bio",     "légume-fruit",  "kg",    0.2,  6.0,  "🫑"),
        ("Piments bio",      "légume-fruit",  "kg",    0.05, 14.0, "🌶️"),
        ("Maïs doux bio",    "légume-fruit",  "pièce", 0.4,  1.5,  "🌽"),
        ("Courge butternut", "légume-fruit",  "kg",    1.2,  3.0,  "🎃"),
        ("Potiron bio",      "légume-fruit",  "kg",    2.5,  2.5,  "🎃"),
        # Légumes-racines
        ("Carottes bio",     "légume-racine", "kg",    0.1,  2.5,  "🥕"),
        ("Betteraves bio",   "légume-racine", "kg",    0.3,  3.0,  "🥕"),
        ("Radis bio",        "légume-racine", "botte", 0.2,  2.0,  "🥕"),
        ("Navets bio",       "légume-racine", "kg",    0.2,  3.0,  "🥕"),
        ("Panais bio",       "légume-racine", "kg",    0.25, 4.0,  "🥕"),
        ("Topinambours bio", "légume-racine", "kg",    0.1,  4.5,  "🥕"),
        # Bulbes
        ("Oignons bio",      "bulbe",         "kg",    0.15, 3.0,  "🧅"),
        ("Échalotes bio",    "bulbe",         "kg",    0.05, 8.0,  "🧅"),
        ("Ail bio",          "bulbe",         "kg",    0.05, 12.0, "🧄"),
        ("Poireaux bio",     "bulbe",         "pièce", 0.3,  1.8,  "🧅"),
        # Tubercules
        ("Pommes de terre bio", "tubercule",  "kg",    0.15, 2.0,  "🥔"),
        ("Patates douces bio",  "tubercule",  "kg",    0.3,  4.0,  "🍠"),
        # Légumineuses
        ("Haricots verts bio", "légumineuse", "kg",    0.005, 7.0, "🫛"),
        ("Petits pois bio",    "légumineuse", "kg",    0.005, 8.0, "🫛"),
        ("Fèves bio",          "légumineuse", "kg",    0.005, 6.0, "🫘"),
        # Aromatiques
        ("Basilic bio",      "aromatique",    "botte", 0.05, 2.5,  "🌿"),
        ("Persil bio",       "aromatique",    "botte", 0.05, 2.0,  "🌿"),
        ("Menthe bio",       "aromatique",    "botte", 0.05, 2.0,  "🌿"),
        ("Thym bio",         "aromatique",    "botte", 0.05, 2.5,  "🌿"),
        ("Ciboulette bio",   "aromatique",    "botte", 0.05, 2.0,  "🌿"),
        # Champignons
        ("Pleurotes bio",    "champignon",    "kg",    0.05, 16.0, "🍄"),
        ("Shiitakes bio",    "champignon",    "kg",    0.05, 22.0, "🍄"),
    ]
    for name, cat, unit, weight, price, emoji in PRODUCTS:
        cur.execute(
            "INSERT INTO products (name, category, unit, unit_weight_kg, default_price, emoji) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET emoji = EXCLUDED.emoji, "
            "category = EXCLUDED.category",
            (name, cat, unit, weight, price, emoji),
        )
    c.commit()
    print(f"   ✓ {len(PRODUCTS)} produits avec emoji")

    # --- catalog ------------------------------------------------------------
    print("→ Catalogue partagé")
    for cat, vals in CATALOG.items():
        for v in vals:
            cur.execute(
                "INSERT INTO catalog_items (category, value, usage_count) "
                "VALUES (%s, %s, 0) ON CONFLICT (category, value) DO NOTHING",
                (cat, v),
            )
    c.commit()

    # --- coefbiodiv ---------------------------------------------------------
    print("→ Coefficients MAEC")
    for y in YEARS:
        cur.execute(
            "INSERT INTO coefbiodiv (year, coefhaie, coefarbrealign, coefarbreseul, "
            "coefbosquet, coefmare, coeffosse, coefbordure, coefjachere, "
            "coefjacheremel, coefmuret, coefprairie, description) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (year) DO NOTHING",
            (y, COEF_BIODIV["coefhaie"], COEF_BIODIV["coefarbrealign"],
             COEF_BIODIV["coefarbreseul"], COEF_BIODIV["coefbosquet"],
             COEF_BIODIV["coefmare"], COEF_BIODIV["coeffosse"],
             COEF_BIODIV["coefbordure"], COEF_BIODIV["coefjachere"],
             COEF_BIODIV["coefjacheremel"], COEF_BIODIV["coefmuret"],
             COEF_BIODIV["coefprairie"], "Coefficients de démonstration"),
        )
    c.commit()

    # --- users + 5 years ----------------------------------------------------
    pwhash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()

    for idx_user, (login, farmname, address, lat, lng) in enumerate(USERS):
        # multiplier so each ferme has a slightly different scale
        factor = 1.0 + 0.3 * idx_user

        cur.execute("SELECT id FROM fermes WHERE name = %s", (login,))
        row = cur.fetchone()
        if row:
            user_id = row[0]
            print(f"→ {login}: existe déjà (id={user_id})")
        else:
            cur.execute(
                "INSERT INTO fermes (name, userpass, farmname, adress, integration_year, "
                "role, lat, lng) "
                "VALUES (%s, %s, %s, %s, '2020', 'producteur', %s, %s) RETURNING id",
                (login, pwhash, farmname, address, lat, lng),
            )
            user_id = cur.fetchone()[0]
            print(f"→ {login}: créé (id={user_id}, mot de passe='{PASSWORD}')")
        c.commit()

        for i, year in enumerate(YEARS):
            cur.execute(
                "SELECT 1 FROM surface WHERE linked_id=%s AND year=%s", (user_id, year),
            )
            if cur.fetchone():
                continue

            s = gen_surface(i, factor)
            tot = round(sum(s.values()), 4)
            cur.execute(
                "INSERT INTO surface (linked_id, year, surftot, surffr, surfgf, surfleg, "
                "prairie, culture, surfautre) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, year, tot, s["surffr"], s["surfgf"], s["surfleg"],
                 s["prairie"], s["culture"], s["surfautre"]),
            )

            b = gen_biodiv(i, factor)
            score = biodiv_score(s["prairie"], b)
            cur.execute(
                "INSERT INTO biodiv (linked_id, year, haie, arbrealign, arbreseul, bosquet, "
                "mare, fosse, bordure, jachere, jacheremel, muret, description, biodivscore) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, year, b["haie"], b["arbrealign"], b["arbreseul"], b["bosquet"],
                 b["mare"], b["fosse"], b["bordure"], b["jachere"], b["jacheremel"],
                 b["muret"], f"Données démo {year}", score),
            )

            p = gen_plastique(i, factor)
            cur.execute(
                "INSERT INTO plastique (linked_id, year, surftotplast, surftottoile, "
                "paillagefr, paillagegf, paillageleg, limitation, embplast, "
                "embplastpourcent, embfr, embgf, embleg) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, year, p["surftotplast"], p["surftottoile"],
                 json.dumps(p["paillagefr"]), json.dumps(p["paillagegf"]),
                 json.dumps(p["paillageleg"]), json.dumps(p["limitation"]),
                 json.dumps(p["embplast"]), p["embplastpourcent"],
                 json.dumps(p["embfr"]), json.dumps(p["embgf"]),
                 json.dumps(p["embleg"])),
            )

            so = gen_soil(i)
            cur.execute(
                "INSERT INTO soil (linked_id, year, soilanalyse, connaissance, "
                "formation, pratique) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, year, json.dumps(so["analyse"]), so["connaissance"],
                 json.dumps(so["formation"]), json.dumps(so["pratique"])),
            )

            w = gen_water(i, factor)
            cur.execute(
                "INSERT INTO water (linked_id, year, matosirrigfr, matosirriggf, "
                "matosirrigleg, consoeau, actions) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (user_id, year, json.dumps(w["matosirrigfr"]),
                 json.dumps(w["matosirriggf"]), json.dumps(w["matosirrigleg"]),
                 w["consoeau"], json.dumps(w["actions"])),
            )

            lu = gen_lutte(i)
            cur.execute(
                "INSERT INTO lutte (linked_id, year, achat, favorisation, formation) "
                "VALUES (%s,%s,%s,%s,%s)",
                (user_id, year, json.dumps(lu["achat"]),
                 json.dumps(lu["favorisation"]), json.dumps(lu["formation"])),
            )
        c.commit()
        print(f"   ✓ 5 années de données pour {login}")

    cur.close()
    c.close()
    print("\nSeed terminé.")
    print(f"Connectez-vous avec n'importe quel login ci-dessus + mot de passe '{PASSWORD}'.")


if __name__ == "__main__":
    main()
